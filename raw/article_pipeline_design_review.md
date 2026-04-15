# Article Pipeline — LLM System Design Review

## 1. Pattern Classification — What Does It Follow?

**The article pipeline IS a true Deterministic Workflow Agent.** This is the key architectural difference from the chatbot.

| Property | Chatbot | Article Pipeline |
|---|---|---|
| Invocation model | `InvokeAgentCommand` (managed runtime) | `ConverseCommand` (direct model API) |
| Workflow orchestration | None — single round-trip | Step Functions state machine |
| Agent count | 1 (managed Bedrock Agent) | 3 specialised Lambdas (Research → Writer → QA) |
| Context passing | Bedrock session memory | Explicit JSON payload through Step Functions |
| State machine | None | `StandardStateMachine` with `Catch → Fail` branches |
| Model switching | Single model per deployment | 3 models, each tuned for task (Haiku for Research, Sonnet for Writer+QA) |
| KB retrieval | Automatic (Bedrock Agent Runtime) | Explicit `RetrieveCommand` call in Research Lambda |
| Prompt injection | Deploy-time static (CDK property) | Runtime dynamic (`SystemContentBlock[]` array, rebuilt per invocation) |

```
S3 (drafts/*.md)
    → S3 Event Notification → Trigger Lambda
        → DynamoDB: write VERSION#v{n} status="processing"
        → Step Functions: StartExecution
            → Research Lambda (Haiku 4.5)
                ├─ S3: read raw draft
                ├─ Bedrock KB: RetrieveCommand → top-k KbPassages
                ├─ Local complexity analysis (deterministic signals)
                └─ ConverseCommand (structured JSON research brief)
            → Writer Lambda (Sonnet 4.6)
                ├─ Receives research brief via Step Functions payload
                ├─ Adaptive thinking budget (2K–16K tokens, complexity-driven)
                └─ ConverseCommand (full MDX article + metadata + shotList)
            → QA Lambda (Sonnet 4.6)
                ├─ Cross-validates article against researcher's technical facts
                ├─ Scores 5 quality dimensions (Technical/SEO/MDX/Metadata/Content)
                ├─ Writes MDX → s3://bucket/review/v{n}/{slug}.mdx
                ├─ Writes VERSION#v{n} record → DynamoDB + updates METADATA
                └─ Emits pipeline-level EMF metrics (BedrockMultiAgent namespace)
            → If any Lambda throws: Catch → DynamoUpdateItem (status="failed") → Fail state

Admin Dashboard
    → Publish Lambda (invoked directly, not via Step Functions)
        ├─ Copies review/v{n}/slug.mdx → content/v{n}/slug.mdx
        ├─ Updates DynamoDB: status="published"
        └─ Optionally: ISR revalidation ping to Next.js frontend
```

---

## 2. What Does the Pipeline Handle?

The pipeline is a **content transformation and quality pipeline**, handling:

### Trigger Lambda
- S3 event notification parsing (decodes URL-encoded keys)
- Slug extraction from S3 key (`drafts/{slug}.md` → `{slug}`)
- DynamoDB version resolution: queries `VERSION#` sort keys to auto-increment `v{n}`
- Immutable initial VERSION record write (`status="processing"`) so the admin dashboard shows live pipeline state
- Step Functions `StartExecution` with a typed `PipelineContext` payload

### Research Lambda
- S3 draft reading (UTF-8 decode)
- **Mode detection**: `draft.length ≤ 500 chars` → `kb-augmented` (prompt-driven), else → `legacy-transform` (draft conversion)
- KB retrieval via `RetrieveCommand` with `numberOfResults: 10`, query capped at 1,000 chars
- **Local complexity analysis** (fully deterministic — no LLM used):
  - Signals: char count, code block count, code ratio, IaC fence count (yaml/hcl/terraform), heading count
  - Tiers: `LOW` (≤1 signal), `MID` (1 moderate signal), `HIGH` (≥2 signals)
  - Tier maps to writer thinking budget: `LOW=2,048`, `MID=8,192`, `HIGH=16,000` tokens
- Author direction extraction (filters headings/metadata lines to isolate instructional text)
- Previous version lookup from DynamoDB + S3 (caps at 3,000 chars for context efficiency)
- LLM call: structured JSON research brief (outline, facts, SEO keywords, suggested references)

### Writer Lambda
- Receives full `ResearchResult` from Step Functions payload (no S3 reads)
- Builds a **runtime-composed user message** from multiple context sections:
  - Retry warning (if `retryAttempt > 0`)
  - Author's creative direction (enforced override)
  - Previous version content (versioning context)
  - KB passages (real infrastructure documentation)
  - Proposed outline (from Research Agent)
  - Verified technical facts (from Research Agent)
  - SEO research brief (primary/secondary keywords + suggested references)
  - Source draft (full markdown)
- Dynamic thinking budget: `min(complexity.budgetTokens, DEFAULT_THINKING_BUDGET)` — complexity-driven
- LLM call: full MDX article + frontmatter + metadata + shotList + suggestedReferences

### QA Lambda
- Receives `WriterResult` from Step Functions payload
- Validates Writer output against 5 weighted dimensions (Technical 35%, SEO 20%, MDX 15%, Metadata 15%, Content 15%)
- Cross-references against Research Agent's `technicalFacts` array
- Overrides Writer's `technicalConfidence` score with its independent `confidenceOverride`
- Determines `articleStatus`: `review` (score ≥ 80) or `flagged` (score < 80)
- Writes MDX to `review/v{n}/{slug}.mdx` (NOT to published — that requires admin approval)
- Writes `VERSION#v{n}` DynamoDB record + upserts `METADATA` record
- Emits pipeline-level EMF metrics

### Publish Lambda (admin-invoked, outside Step Functions)
- Validates article exists in DynamoDB with expected status
- Copies `review/v{n}/slug.mdx` → `content/v{n}/slug.mdx` (or `published/`)
- Updates DynamoDB status to `published`
- Optionally triggers ISR revalidation on the Next.js frontend

---

## 3. Model Calls — Mechanics

All three agents use **`ConverseCommand`** (not `InvokeAgentCommand`). This is a direct model API call, NOT a managed Bedrock Agent.

```typescript
// Shared runAgent() in bedrock-applications/shared/src/index.ts
const command = new ConverseCommand({
    modelId: config.modelId,            // Application Inference Profile ARN or model ID
    system: config.systemPrompt,        // SystemContentBlock[] with cachePoint
    messages: [{ role: 'user', content: [{ text: userMessage }] }],
    inferenceConfig: {
        maxTokens: config.maxTokens,
    },
    ...(config.thinkingBudget > 0
        ? {
              additionalModelRequestFields: {
                  thinking: {
                      type: 'enabled',
                      budget_tokens: config.thinkingBudget,
                  },
              },
          }
        : {}),
});
```

### Model Assignment (per CDK config)

| Agent | Model | Max Tokens | Thinking Budget |
|---|---|---|---|
| Research | `eu.anthropic.claude-haiku-4-5-*` | 8,192 | 4,096 (fixed) |
| Writer | `eu.anthropic.claude-sonnet-4-6-*` | 32,768 | 2,048–16,000 (adaptive) |
| QA | `eu.anthropic.claude-sonnet-4-6-*` | 16,384 | 8,192 (fixed) |

**Key design choices:**
- Haiku for Research: cost-efficient for extraction/analysis (no creative generation needed)
- Sonnet for Writer: highest-quality model for creative, high-stakes generation
- Sonnet for QA (Phase 2 upgrade from Haiku): deeper technical reasoning needed to validate code snippets and CDK patterns
- All use **Application Inference Profile ARNs** for FinOps cost allocation tags (component: `article-pipeline`)
- All use **EU cross-region inference profiles** for capacity resilience

---

## 4. The System Prompts — Full Anatomy

### 4.1 Research Persona (`research-persona.ts`)

**Size**: ~156 lines, 2 `SystemContentBlock` text blocks + 1 `cachePoint`

**Structure** (cached):
1. Role: "Technical Research Analyst for a DevOps/Cloud Engineering portfolio blog"
2. Research mandate: 5 tasks (topic ID, fact extraction, complexity classification, outline, tags/title)
3. SEO research directive: primary keyword (3–5 words), 2–4 secondary keywords, 3–5 authoritative references
4. Mode detection: KB-Augmented (≤500 chars) vs Legacy Transform (>500 chars)
5. Complexity classification: HIGH/MID/LOW with specific signals
6. Standard article section template (7 sections with word budgets)

**Output schema** (not cached — second block):
- Strict JSON: `mode`, `suggestedTitle`, `suggestedTags`, `complexity`, `outline[]`, `technicalFacts[]`, `seoResearch{}`
- Tag vocabulary: 50+ controlled terms (CDK, Lambda, Calico, Crossplane, etc.)

**Strengths**:
- Complexity analysis is validated client-side (local `analyseComplexity()` function runs FIRST; LLM complexity is overridden by deterministic result)
- SEO reference hallucination guard: "MUST be well-known, stable URLs — do NOT guess or fabricate URLs"
- Explicit tag vocabulary prevents uncontrolled keyword proliferation

**Gaps**:
- No explicit instruction for what to do when KB returns 0 passages (just proceeds with research)
- `seoResearch` is a gracefully optional field (`parseSeoResearch` returns `undefined` on failure) — no fallback quality signal

---

### 4.2 Blog Persona / Writer (`blog-persona.ts`)

**Size**: 816 lines, 41,949 bytes — the largest and most complex prompt in the system

**Structure with prompt caching**:

```
SystemContentBlock[] = [
    { text: PERSONA_CONTEXT },        // ~400 tokens
    { text: WRITING_VOICE },          // ~550 tokens  
    { text: CONTENT_ARCHITECTURE },   // ~350 tokens
    { text: NEXTJS_MDX_SCHEMA },      // ~700 tokens
    { text: SEO_CONTENT_STRATEGY },   // ~450 tokens
    { text: OUTPUT_AND_GUIDELINES },  // ~1,200 tokens
    { cachePoint: 'default' },        // ← CACHE BOUNDARY (~3,650 tokens above)
]
```

**All 6 sections cached → ~90% cost reduction on system prompt portion**

**Key sections**:

| Section | Purpose | Notable Detail |
|---|---|---|
| `PERSONA_CONTEXT` | Brand mission, role, target audience (3 buyer types), competitive positioning | Explicit 2×2 positioning grid: "Nelson = real infra + trade-offs" quadrant |
| `WRITING_VOICE` | 6 writing rules, anti-AI detection patterns, terminology list | Coefficient of variation > 0.4 sentence length rule, prohibited opener patterns |
| `CONTENT_ARCHITECTURE` | Word budgets per section, scannability rules, 3 length variants | 1,500–2,500 word target; "Where This Applies" called "#1 section recruiters look for" |
| `NEXTJS_MDX_SCHEMA` | Exact frontmatter spec, `<Callout>`, `<MermaidChart>`, `<ImageRequest>`, `<VideoRequest>` | Registered component contract — "Using any unregistered component will break the page" |
| `SEO_CONTENT_STRATEGY` | Keyword density targets (0.5–1.0%), chatbot mention directive, TOC rules, external link policy | "Include only ≤4 external links per article — quality over quantity" |
| `OUTPUT_AND_GUIDELINES` | Full JSON output schema, Adaptive Thinking instructions, constraints, KB-Augmented mode | Shot List self-validation step, `technicalConfidence` scoring rules |

**Adaptive Thinking instructions** inside the prompt tell the model HOW to use its thinking budget:
1. Identify the "drift problem" (the 2 AM moment)
2. Perform FinOps analysis (calculate cost savings with actual math)
3. Syntax verification of all CLI strings and code
4. Structural scan (plan section variety BEFORE writing)

---

### 4.3 QA Persona (`qa-persona.ts`)

**Size**: 167 lines, 2 `SystemContentBlock` text blocks + 1 `cachePoint`

**Structure** (cached):
5 quality dimensions with explicit weights:
1. Technical Accuracy (35%): AWS CLI accuracy, CDK construct validity, K8s manifests, hardcoded secrets check
2. SEO Compliance (20%): meta description length, heading hierarchy, slug format, keyword density (0.5–1.0%), chatbot mention presence
3. MDX Structure (15%): frontmatter validity, Mermaid syntax, `shotList` ↔ inline tag consistency
4. Metadata Quality (15%): reading time accuracy (±1 min), AI summary quality, confidence score calibration
5. Content Quality (15%): British English, narrative flow, no placeholders, author voice consistency

**Output schema** (not cached — second block):
- `overallScore` (weighted average), `recommendation` (publish/revise/reject), 5 dimension objects with `issues[]`, `confidenceOverride`

**Critical QA invariant**: The QA agent REPLACES the Writer's `technicalConfidence` with its own `confidenceOverride`. This creates an independent validation layer that prevents the Writer from self-inflating its confidence.

---

## 5. Knowledge Base — Structure and Integration

### Physical KB Structure

The article pipeline uses the **same Bedrock KB** as the chatbot (from `kb-stack.ts`):

```
S3 bucket/kb-docs/           ← ONLY this prefix is indexed
  ├── infrastructure/         ← CDK stacks, network configs
  ├── kubernetes/             ← K8s manifests, bootstrap scripts
  ├── ci-cd/                  ← GitHub Actions workflows
  └── articles/               ← Existing published MDX (optional)
```

KB settings:
- Model: Titan Embeddings V2 (1024 dims)
- Chunking: HIERARCHICAL_TITAN — parent 1,500 tokens / child 300 tokens / overlap 60
- Vector store: Pinecone (free tier, 100K vector limit)
- Fields: `text` (content), `metadata` (source URI)

### How the Pipeline Connects to the KB

Unlike the chatbot (which delegates RAG to the Bedrock Agent Runtime automatically), **the Research Lambda calls the KB explicitly**:

```typescript
// research-agent.ts
const command = new RetrieveCommand({
    knowledgeBaseId: KNOWLEDGE_BASE_ID,
    retrievalQuery: { text: query.substring(0, 1000) },    // ← explicit cap
    retrievalConfiguration: {
        vectorSearchConfiguration: { numberOfResults: 10 }, // ← explicit top-k
    },
});
```

Key differences from the chatbot's KB usage:

| Dimension | Chatbot (InvokeAgent) | Article Pipeline (Retrieve) |
|---|---|---|
| Who calls the KB? | Bedrock Agent Runtime (automatic) | Research Lambda (explicit) |
| KB passages visible in code? | No (black box) | Yes — typed `KbPassage[]` |
| Passages passed to Writer? | N/A (agent-internal) | Explicitly passed in Step Functions payload |
| Query control | Full (Bedrock decides query) | Manual (draft content, capped at 1,000 chars) |
| Score visibility | No | Yes — `passage.score` logged and shown in prompts |
| Passage attribution | No (hidden) | Yes — `sourceUri` shown to Writer and Reader can trace |

---

## 6. Is the Pipeline Tightly Coupled to KB Data Structure?

**Less tightly coupled than the chatbot, but the KB purpose is different here.**

For the chatbot, the KB IS the primary source of truth. For the article pipeline, the KB is **supplementary context** — the raw draft is always the primary source.

### What IS coupled:

| Coupling | Location | Impact if changed |
|---|---|---|
| `kb-docs/` S3 prefix | `kb-stack.ts` `inclusionPrefixes` | Files outside this prefix are never indexed; Research Agent retrieves nothing |
| Titan Embeddings V2 dimensions (1024) | Pinecone index configuration | Changing embedding model requires full re-index — Research Agent would silently get wrong vectors |
| `numberOfResults: 10` | `research-agent.ts` hard-coded | Changing KB vector count requires code change |
| Query length cap (1,000 chars) | `research-agent.ts` hard-coded | A longer KB query might improve relevance but requires code change |
| `KNOWLEDGE_BASE_ID` env var | CDK `pipeline-stack.ts` (conditional injection) | If not set, KB retrieval is silently skipped — no error, just empty passages |

### What is NOT coupled (by design):

- **Document content**: The Research Agent processes whatever passages come back — adding new infrastructure docs requires only an S3 upload + data sync
- **Topic coverage**: The pipeline handles any technical topic. There are no hardcoded topic references in the Research prompt
- **KB quality fallback**: If KB returns 0 passages, the pipeline continues — it falls back to analysing the draft directly (mode: `legacy-transform`)
- **Writer prompt**: The `buildContextSection` in `writer-agent.ts` conditionally includes KB passages only if `kbPassages.length > 0` — zero-passage runs skip the section entirely

### Aggressive/Restrictive KB Approach?

**No** — the article pipeline takes a **pragmatic, additive** approach to KB content. Unlike the chatbot (which MUST answer from the KB and has a Guardrail to enforce scope), the article pipeline uses KB context as **enrichment**:
- If KB content is available and relevant → Writer includes it with attribution
- If KB has nothing → Writer generates from the draft alone
- The KB is never a hard gate; it is always optional enrichment

---

## 7. Does the Pipeline Need Code Changes if KB Data Structure Evolves?

| Change | Code Change Needed? | Scope |
|---|---|---|
| Add new Markdown docs to `kb-docs/` | ❌ No | S3 upload + data sync only |
| Rename a document | ❌ No | Data sync only |
| Change document content / headings | ❌ No | Data sync only |
| Change `numberOfResults` (top-k) | ✅ Yes | `research-agent.ts` constant |
| Change query length cap (1,000 chars) | ✅ Yes | `research-agent.ts` constant |
| Change KB chunking strategy | ⚠️ CDK only | `kb-stack.ts` + full re-index |
| Change embedding model | ⚠️ CDK + Pinecone rebuild | `kb-stack.ts` + Pinecone index dimensions + re-index |
| Change Pinecone field names | ⚠️ CDK only | `PINECONE_METADATA_FIELD` / `PINECONE_TEXT_FIELD` constants |
| Change S3 prefix from `kb-docs/` to `docs/` | ⚠️ CDK only | `kb-stack.ts` `inclusionPrefixes` |
| Add non-Markdown content (JSON, YAML) | ⚠️ Potentially | Chunk quality may degrade; custom parser may be needed |
| Change `KNOWLEDGE_BASE_ID` (same schema) | ⚠️ CDK only | Env var in `pipeline-stack.ts` |

**Bottom line**: Data structure evolution (content changes, new docs) requires ZERO code changes. Schema/infrastructure evolution requires CDK changes only — never the Lambda application code.

---

## 8. Security Assessment — Gaps

### ✅ Well-Implemented Controls

| Area | Control | Assessment |
|---|---|---|
| IAM | Research Lambda: `bedrock:Retrieve` scoped to KB ARN only | ✅ Least privilege |
| IAM | Writer Lambda: `bedrock:InvokeModel` only (no S3, no DDB) | ✅ Write-isolated |
| IAM | QA Lambda: S3 write scoped to `review/*` prefix only | ✅ Prefix-scoped |
| IAM | Publish Lambda: broad (full bucket + DDB) but admin-only | ✅ Acceptable (admin context) |
| IAM | Step Functions → DDB: `grantWriteData` (not `grantFullAccess`) | ✅ Correct |
| DLQ | SQS DLQ for pipeline failures (14-day retention) | ✅ Good |
| S3 | Drafts bucket: server-side encryption, versioning, SSL enforced | ✅ Solid |
| Environment | All model IDs, ARNs, table names via env vars — no hardcoding | ✅ Correct |
| XRay | Tracing enabled on all 5 Lambdas | ✅ Good |
| Prompt caching | `cachePoint` only on stable static sections — dynamic user content not cached | ✅ Correct strategy |

---

### ⚠️ Security Gaps Requiring Attention

#### Gap S1 — No Input Sanitisation Before Model Invocation
The article pipeline **has no equivalent of the chatbot's `sanitiseInput()` layer**. The raw draft content from S3 is passed directly to the model:

```typescript
// research-agent.ts — no sanitisation before LLM call
const draftContent = await readDraftFromS3(ctx.bucket, ctx.sourceKey);
const userMessage = buildResearchMessage(draftContent, kbPassages, mode);
const result = await runAgent({ config, userMessage, ... });
```

**Risk**: A malicious author could craft a draft with prompt injection patterns targeting the Research or Writer agent. Since the pipeline is admin-controlled (S3 upload requires AWS credentials), this is a **low-risk but non-zero gap**.

**Recommendation**: Add a lightweight input sanitiser before `buildResearchMessage()`:
- Strip any `<system>`, `</system>`, `[INST]`, `Human:`, `Assistant:` injection patterns
- Validate draft size (refuse >500KB)
- Log a `PromptInjectionAttempt` EMF metric if patterns are detected

#### Gap S2 — `KNOWLEDGE_BASE_ID` Optional Silences Failures
```typescript
const KNOWLEDGE_BASE_ID = process.env.KNOWLEDGE_BASE_ID ?? '';
// If empty:
if (!KNOWLEDGE_BASE_ID) {
    console.log('[research] KB retrieval skipped — no KNOWLEDGE_BASE_ID configured');
    return [];
}
```
**Risk**: If the CDK env var is accidentally omitted (e.g., KB stack not deployed), the pipeline runs silently without KB context. No alert, no metric, no noise. For `kb-augmented` mode (short drafts), this produces a context-free article from a prompt alone.

**Recommendation**: Emit an EMF metric `KbRetrievalSkipped` when `KNOWLEDGE_BASE_ID` is empty. Consider making it a hard `throw` in non-development environments.

#### Gap S3 — No Output Sanitisation Post-Model
Unlike the chatbot (which has `sanitiseOutput()` for ARNs, IPs, account IDs), **no equivalent exists in the article pipeline**. The Writer's MDX `content` is passed directly to S3 and DynamoDB.

**Risk**: The Writer model (given KB passages containing infrastructure docs) could include real AWS ARNs, account IDs, or private cluster details verbatim in the published article.

**Recommendation**: Run `sanitiseOutput()` (or a adapted version) on `writer.data.content` before writing to S3:
```typescript
// In qa-handler.ts, step 4:
const sanitisedContent = sanitiseOutput(event.writer.data.content);
await writeToReviewPrefix(ASSETS_BUCKET, slug, version, sanitisedContent);
```

#### Gap S4 — No Rate Limit on Trigger Lambda
The S3 event notifications fire per-object. Uploading 50 drafts simultaneously starts 50 concurrent Step Functions executions. With Bedrock per-invocation throttling and 3 model calls per execution, 50 concurrent runs = 150 concurrent Bedrock API calls.

**Risk**: Bedrock `ThrottlingException`s cascade, causing Step Functions executions to fail at the Research or Writer stage and write `status="failed"` to DynamoDB.

**Recommendation**: Add SQS as a buffer between S3 notifications and the Trigger Lambda (with a sensible concurrency limit on the Lambda), or use Step Functions rate controls. Alternatively, add retry logic with exponential back-off in `runAgent()`.

#### Gap S5 — Writer Slug Divergence Only Warns
```typescript
// qa-handler.ts
if (writerSlug && writerSlug !== event.context.slug) {
    console.warn(`[qa-handler] ⚠️ SLUG DIVERGENCE DETECTED — ...`);
}
```
The slug used for DynamoDB keys is correctly taken from `context.slug` (authoritative). However, the divergence is only logged — no metric, no QA score penalty.

**Recommendation**: Emit an `SlugDivergence` EMF metric and add it as an `mdxStructure` quality issue with `severity: "warning"` so the QA dashboard surfaces it.

#### Gap S6 — `bedrock:InvokeModel` Uses Wildcard Foundation Model
```typescript
researchFn.addToRolePolicy(new iam.PolicyStatement({
    actions: ['bedrock:InvokeModel'],
    resources: [
        props.researchProfileArn,              // ← scoped correctly
        'arn:aws:bedrock:*::foundation-model/*', // ← any model in any region
    ],
}));
```
The wildcard `foundation-model/*` ARN means the Research Lambda can technically invoke **any** Bedrock model, not just Haiku. This is a CDK-Nag IAM5 suppression target.

**Recommendation**: Scope to only the specific model ID in use:
```typescript
`arn:aws:bedrock:eu-west-1::foundation-model/anthropic.claude-haiku-*`
```

---

## 9. Cost Monitoring — Current State and Gaps

### ✅ What Exists

#### Application Inference Profiles (in `data-stack.ts`)
4 profiles with cost-allocation tags covering both article-pipeline and strategist:
```
tags: { component: 'article-pipeline', project: 'bedrock', environment: '...', owner: 'nelson-l' }
```

#### Per-Agent EMF Metrics (in `runAgent()` shared utility)
Each agent emits to `BedrockMultiAgent` namespace:
- `AgentInvocationCount`, `AgentInputTokens`, `AgentOutputTokens`, `AgentThinkingTokens`
- `AgentLatency`, `AgentCostUsd`, `AgentModelId`
- Dimensions: `AgentName` (research/writer/qa) + `Environment`

#### Pipeline-Level EMF (in `qa-handler.ts`)
Emitted once per completed pipeline:
- `PipelineCompleted`, `PipelineCostUsd`, `PipelineQaScore`
- `PipelineRetryCount`, `PipelinePassed`
- Dimensions: `Environment` + `Slug` + `Version`

#### Prompt Caching — Cost Savings
The blog persona has a `cachePoint` after ~3,650 tokens of static content. Bedrock charges **10%** of standard input token price for cached reads:
- Each article invocation saves ~3,650 × 90% = ~3,285 cached tokens at reduced price
- For Sonnet (≈$3/MTok input), that's ~$0.01 saved per article on the writer system prompt alone
- Over 100 articles: ~$1 saved purely from caching

Research and QA personas also have `cachePoint` markers for their static sections.

---

### ❌ Cost Monitoring Gaps

#### Gap C1 — No Token-Level Cost Verification
`cumulativeCostUsd` is computed by `runAgent()` using a local lookup table of model costs. If AWS changes pricing and the lookup table is not updated, `PipelineCostUsd` metrics are silently wrong.

**Recommendation**: The `ConverseCommand` response includes `usage.inputTokens`, `usage.outputTokens`. The local cost calculation should be validated monthly against actual Cost Explorer values from the Application Inference Profile tags.

#### Gap C2 — `PipelineCostUsd` Doesn't Account for Prompt Cache Savings
The local cost calculation likely charges full input token price, not the discounted 10% cached rate. Actual cost will be lower than reported.

**Recommendation**: Track `cachedInputTokens` (available in Bedrock response `usage`) and apply the 10% rate to them separately in the cost calculation.

#### Gap C3 — No Budget Alarm
Same gap as the chatbot — no `aws-budgets` construct. A misconfigured retry loop (e.g., all articles fail QA and DLQ fills) could generate unexpected Bedrock costs.

**Recommendation**:
```typescript
new budgets.CfnBudget(this, 'BedrockPipelineBudget', {
    budget: {
        budgetType: 'COST',
        timeUnit: 'MONTHLY',
        budgetLimit: { amount: 50, unit: 'USD' },
        costFilters: { Service: ['Amazon Bedrock'] },
    },
    ...
});
```

#### Gap C4 — No Failed Pipeline Cost Tracking
When the state machine hits `MarkArticleFailed → Fail`, the `PipelineCostUsd` up to that point is not recorded (the EMF is only emitted in `qa-handler.ts`). A failure in the Writer stage after the Research stage has already consumed Haiku tokens goes uncounted.

**Recommendation**: The `MarkArticleFailed` DynamoDB state in Step Functions should also emit an EMF metric with partial cost data from the `context.cumulativeCostUsd` payload field.

---

## 10. Prompt Testing & Evolution Strategy

### Current State

All three prompts are TypeScript `const` values compiled into the Lambda bundle. Changes require:
1. Edit `{research|blog|qa}-persona.ts`
2. `npm run build` in `bedrock-applications/article-pipeline/`
3. CDK deploy updates the Lambda function code
4. No automated evaluation framework exists — manual testing only

### What Makes This Pipeline Easier to Evolve Than the Chatbot

Unlike the chatbot (where the prompt is a `CfnAgent` property requiring an agent version bump), the article pipeline prompts are **Lambda code** — a Lambda code-only update (no CDK infrastructure change) suffices if only the prompt changes.

Also, the pipeline has a **built-in evaluation mechanism**: the QA Agent. Every article run produces:
- 5 dimension scores
- An `overallScore`
- A `recommendation`
- Specific `issues[]` with location and fix

This means prompt quality changes are measurable automatically — you can compare `PipelineQaScore` metrics before/after a prompt change.

### Gaps

1. **No golden dataset** — there is no set of reference articles to regression-test prompt changes against
2. **No A/B prompt mechanism** — there is no way to test two Writer prompt variants simultaneously
3. **QA agent evaluates its own sibling's output** — the QA persona was designed by the same engineer as the Writer persona. There is no truly independent QA criterion definition

### Recommended Evolution Strategy

#### Short-term: Instrument for Prompt Evaluation

The QA JSON output with 5 dimension scores already exists in DynamoDB. Build a query:
```sql
-- DynamoDB GSI1 query: STATUS#review articles, last 30 days
-- Aggregate dimension scores by month → detect prompt regression
```
Track `avg(qaScore)`, `avg(technicalAccuracy.score)` over time. A prompt change that reduces `avg(technicalAccuracy)` regressed the Writer.

#### Medium-term: Draft-Level A/B Mechanism

Add a `promptVariant` field to the `PipelineContext`. The CDK `pipeline-stack.ts` would inject a second "B" Writer Lambda with an alternative prompt. The Trigger Handler routes 50% of new slugs to variant B by checking a feature flag in SSM.

```typescript
// trigger-handler.ts
const variant = (Math.random() < 0.5) ? 'A' : 'B';
const stateMachineArn = variant === 'B' ? STATE_MACHINE_B_ARN : STATE_MACHINE_ARN;
```

#### Long-term: Bedrock Evaluation Jobs

Use **Bedrock Model Evaluation** (GA 2024) to run the Writer model against a curated set of reference articles with automated ROUGE-L and semantic similarity scores. This produces a quantitative prompt evaluation without human review.

---

## 11. Implementation Gaps Summary

| # | Gap | Severity | Effort |
|---|---|---|---|
| S1 | No input sanitisation before model invocation (prompt injection) | 🟡 Medium | Low |
| S2 | `KNOWLEDGE_BASE_ID` optional — silent failure in kb-augmented mode | 🟡 Medium | Low |
| S3 | No output sanitisation — ARNs/IPs could appear in published articles | 🟡 Medium | Low |
| S4 | No rate limit on Trigger Lambda — mass upload floods Bedrock API | 🟡 Medium | Medium |
| S5 | Slug divergence not surfaced as QA metric | 🟢 Low | Trivial |
| S6 | `bedrock:InvokeModel` allows any foundation model (wildcard ARN) | 🟢 Low | Low |
| C1 | Cost lookup table not tied to live pricing — silent drift | 🟡 Medium | Low |
| C2 | Prompt cache savings not subtracted from `PipelineCostUsd` | 🟢 Low | Low |
| C3 | No monthly budget alarm for Bedrock service | 🟡 Medium | Low |
| C4 | Failed pipeline partial cost not recorded by EMF | 🟢 Low | Low |
| P1 | No golden dataset for prompt regression testing | 🟡 Medium | Medium |
| P2 | No A/B mechanism for prompt variant testing | 🟢 Low | Medium |
| P3 | QA pass threshold (80) is a hard-coded constant — no environment override | 🟢 Low | Trivial |

---

## 12. Pipeline Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│  Article Pipeline — Full Lifecycle                                   │
│                                                                      │
│  Author                                                              │
│    │ uploads draft.md → s3://bucket/drafts/{slug}.md                │
│    ▼                                                                 │
│  S3 Event Notification (OBJECT_CREATED, prefix=drafts/, suffix=.md) │
│    ▼                                                                 │
│  Trigger Lambda                                                      │
│    ├─ Extract slug from key                                          │
│    ├─ DynamoDB: resolveNextVersion() → v{n}                          │
│    ├─ DynamoDB: PutItem VERSION#v{n} status="processing"             │
│    └─ Step Functions: StartExecution                                 │
│         │                                                            │
│         ▼                                                            │
│  ┌──── Step Functions: article-pipeline ────────────────────────┐   │
│  │                                                               │   │
│  │  Research Lambda (Haiku 4.5, 8K tokens, 4K thinking)         │   │
│  │    ├─ S3: readDraftFromS3()                                   │   │
│  │    ├─ Mode detect (≤500 chars → kb-augmented)                │   │
│  │    ├─ Bedrock KB: RetrieveCommand (top-10 passages)           │   │
│  │    ├─ analyseComplexity() → deterministic tier                │   │
│  │    └─ ConverseCommand → JSON research brief                   │   │
│  │         │                                                     │   │
│  │         ▼ (Step Functions payload: ResearchResult)            │   │
│  │  Writer Lambda (Sonnet 4.6, 32K tokens, 2K–16K thinking)     │   │
│  │    ├─ buildWriterMessage() (context + KB + outline + facts)   │   │
│  │    ├─ Adaptive thinking budget (complexity.tier → tokens)     │   │
│  │    └─ ConverseCommand → JSON MDX + metadata + shotList        │   │
│  │         │                                                     │   │
│  │         ▼ (Step Functions payload: WriterResult)              │   │
│  │  QA Lambda (Sonnet 4.6, 16K tokens, 8K thinking)             │   │
│  │    ├─ buildQaMessage() (article + metadata + technicalFacts)  │   │
│  │    ├─ ConverseCommand → 5-dimension score + recommendation    │   │
│  │    ├─ Determine status: ≥80 → "review", <80 → "flagged"      │   │
│  │    ├─ S3: writeToReviewPrefix() → review/v{n}/{slug}.mdx      │   │
│  │    ├─ DynamoDB: PutItem VERSION#v{n} (full record)            │   │
│  │    ├─ DynamoDB: UpdateItem METADATA (consumer-facing fields)  │   │
│  │    └─ EMF: PipelineCompleted, PipelineCostUsd, PipelineQaScore│   │
│  │                                                               │   │
│  │  ← On any Lambda throw:                                       │   │
│  │    Catch(States.ALL) → DynamoUpdateItem status="failed" → Fail│   │
│  └───────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  Admin Dashboard                                                     │
│    │ approves article                                                │
│    ▼                                                                 │
│  Publish Lambda (direct invoke, not Step Functions)                  │
│    ├─ S3: copy review/v{n}/slug.mdx → content/v{n}/slug.mdx         │
│    ├─ DynamoDB: UpdateItem status="published"                        │
│    └─ (optional) ISR revalidation ping → Next.js frontend           │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│  DynamoDB Data Model (Single-Table)                                  │
│                                                                      │
│  pk                    sk                Status    Description       │
│  ─────────────────     ─────────────── ─────────── ──────────────── │
│  ARTICLE#{slug}        METADATA         published  Consumer fields  │
│  ARTICLE#{slug}        VERSION#v1        review    Full pipeline out│
│  ARTICLE#{slug}        VERSION#v2        flagged   QA failed        │
│  ARTICLE#{slug}        VERSION#v3        processing Pipeline running │
│                                                                      │
│  GSI1: gsi1pk=STATUS#{status}, gsi1sk={date}#{slug}#{v}            │
│  → Allows dashboard queries: "all review articles this week"        │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 13. Reasoning & Inference-time Techniques — What Is Applied and What Is Missing?

This section maps each technique from the list below against the actual pipeline implementation, citing specific source code evidence where applicable.

---

### 13.1 Technique Inventory

#### Legend
- ✅ **Applied** — the technique is demonstrably implemented in the codebase
- ⚠️ **Partial / Implicit** — the technique is approximated by the implementation but not fully formalised
- ❌ **Absent but Relevant** — the technique would improve this system and is not implemented
- 🚫 **Not Applicable** — the technique does not fit this use case and should not be added

---

### 13.2 Inference-time Techniques

---

#### 1. Reasoning / Thinking LLMs — Extended Thinking with Budget Tokens

**Status: ✅ Applied — and the most significant inference-time design choice in the system.**

All three agents use Claude's Extended Thinking API via `additionalModelRequestFields.thinking.budget_tokens`. This is explicitly set per-agent with different budgets:

```typescript
// shared/src/index.ts → runAgent()
...(config.thinkingBudget > 0
    ? {
          additionalModelRequestFields: {
              thinking: {
                  type: 'enabled',
                  budget_tokens: config.thinkingBudget,
              },
          },
      }
    : {})
```

| Agent | Thinking Budget | Budget Rationale |
|---|---|---|
| Research (Haiku 4.5) | 4,096 tokens (fixed) | Extraction task — moderate depth needed |
| Writer (Sonnet 4.6) | 2,048–16,000 tokens (adaptive) | Creative + technical — budget scales with content complexity |
| QA (Sonnet 4.6) | 8,192 tokens (fixed) | Technical validation needs deep reasoning |

EMF metrics track thinking token consumption as a separate dimension (`AgentThinkingTokens`) for cost attribution.

**Design quality**: The thinking budget is not static — it is **adaptive for the Writer** based on the `analyseComplexity()` signal (see §13.2.2). This is a thoughtful implementation of inference-time compute allocation.

---

#### 2. Inference-time Scaling — Adaptive Compute Allocation

**Status: ✅ Applied — this is explicit and code-driven.**

The pipeline implements inference-time compute scaling via the `analyseComplexity()` function in `research-agent.ts`. This is a **deterministic pre-model signal** that scales the Writer's thinking budget:

```typescript
// research-agent.ts
const TIER_BUDGETS: Record<ComplexityTier, number> = {
    LOW: 2_048,   // Light content → minimal thinking
    MID: 8_192,   // Moderate → standard thinking
    HIGH: 16_000, // Dense technical → maximum thinking
};
```

The classification uses 5 observable signals (character count, code ratio, code block count, IaC fences, heading count) and requires ≥2 concurrent signals to reach HIGH tier. **This is a rule-based inference-time scaling policy.**

**Gap R1**: The scaling is currently **binary** per tier (LOW=2K, MID=8K, HIGH=16K) with no continuous allocation. A linear scaling model like `budget = base + (signals_triggered × 2048)` would allow finer-grained compute allocation without requiring a tier redesign.

**Gap R2**: The `analyseComplexity()` function runs on the **raw draft**, not on the Research Agent's output brief. After the Research Agent returns a structured brief with `technicalFacts[]` and `outline[]`, the Writer could re-evaluate complexity based on these richer signals (e.g., `technicalFacts.length > 20 → upgrade to HIGH`). This second-pass complexity refinement is not implemented.

---

#### 3. Chain-of-Thought (CoT) Prompting

**Status: ⚠️ Partial — applied implicitly via structured thinking instructions, not via explicit CoT prefix in the user message.**

The `blog-persona.ts` Reasoning Instructions section tells the model exactly what to reason about before writing, in ordered steps:

```
## Reasoning Instructions (Adaptive Thinking)
Before generating the final JSON, use your <thinking> tokens to:

1. THE DRIFT PROBLEM: Identify the specific drift, failure, or pain point...
2. FINOPS ANALYSIS: Calculate any cost optimizations mentioned...
3. SYNTAX VERIFICATION: Verify ALL command-line strings, config keys, and code snippets...
4. STRUCTURAL SCAN: Before writing, plan your section order...
```

This is **structured CoT via system prompt** — the model is instructed to follow a specific chain of reasoning steps before producing output. The key difference from classic CoT is that this reasoning happens inside the `<thinking>` block (visible only in the Bedrock response, not in the article output) rather than as a reasoning prefix in the visible response.

**What is missing**: None of the three agents uses explicit **few-shot CoT** — example reasoning traces demonstrating high-quality thinking are not provided in any prompt. Adding 1–2 exemplar thinking traces to the QA persona (e.g., "here is how a good QA review traces a technical fact to its article claim") would significantly improve QA consistency.

**Gap R3**: Add 1–2 short exemplar `<thinking>` traces per agent as few-shot reasoning examples inside the system prompt. For the QA agent specifically, an exemplar trace that shows how to cross-reference `technicalFacts[]` against article content would improve the reliability of the `technicalAccuracy` dimension score.

---

#### 4. Self-Consistency (Multiple Sampling → Vote)

**Status: ❌ Absent.**

Self-consistency calls the same model N times with temperature > 0 and takes the majority answer. The pipeline calls each agent **exactly once** per run. There is no sampling or voting mechanism.

**Is it relevant?** Yes — but only for the QA score, not the article content. The QA agent produces a single score on a single run. That score directly gates whether the article is `review` or `flagged`. A single QA score can be sensitive to prompt phrasing and model temperature.

**Gap R4 — QA Score Self-Consistency**: Run the QA agent 2–3 times and average the `overallScore` (and dimension scores). This reduces variance in gating decisions without changing the architecture. The `PipelineContext` already tracks `cumulativeCostUsd`, so the additional QA cost (2× QA tokens) can be tracked.

```typescript
// qa-handler.ts — proposed self-consistency pattern
const qaRuns = await Promise.all([
    executeQaAgent(ctx, writerResult, technicalFacts, mode),
    executeQaAgent(ctx, writerResult, technicalFacts, mode),
]);
const averagedScore = (qaRuns[0].data.overallScore + qaRuns[1].data.overallScore) / 2;
```

**Effort**: Low. **Value**: High — QA score variance is the primary risk with a hard-coded `QA_PASS_THRESHOLD = 80`.

---

#### 5. Sequential Revision (Iterative Refinement Loop)

**Status: ⚠️ Partial — implemented via retry, NOT via in-pipeline revision loops.**

The pipeline has a `retryAttempt` counter in `PipelineContext` and the Writer prompt includes a retry warning block:

```typescript
// writer-agent.ts → buildContextSection()
...(retryAttempt > 0
    ? [
          `> ⚠️ This is retry attempt ${retryAttempt}. The previous version did not pass QA.`,
          `> Pay extra attention to technical accuracy and code correctness.`
      ]
    : [])
```

However, this retry is **triggered by a full pipeline re-execution** (a new S3 `PutObject` of the draft), not by an in-pipeline self-correction loop. There is no Step Functions state that loops:

```
Writer → QA → if score < threshold → Writer (with QA feedback) → QA
```

Instead, the current flow is:
```
Writer → QA → if score < threshold → status="flagged" → human re-submits draft
```

**What is missing**: The QA agent's `issues[]` array contains specific, actionable feedback (issue location, severity, suggested fix). This structured feedback is **never fed back to the Writer**. It is only stored in DynamoDB for the admin dashboard. This is a significant missed opportunity for in-pipeline self-refinement.

**Gap R5 — In-pipeline Revision Loop**: Add a Step Functions `Choice` state after the QA Lambda:
- If `overallScore >= QA_PASS_THRESHOLD` → continue to S3 write + DynamoDB
- If `overallScore < QA_PASS_THRESHOLD && retryAttempt < MAX_RETRIES (2)` → loop back to Writer with QA `issues[]` injected into the user message
- If `overallScore < QA_PASS_THRESHOLD && retryAttempt >= MAX_RETRIES` → `status="flagged"` (current behaviour)

This is the highest-value reasoning improvement available to the pipeline. It converts QA from a pure evaluation gate into an active revision signal.

```typescript
// Step Functions state machine — revised flow
const retryWriter = new tasks.LambdaInvoke(this, 'RetryWriter', {
    lambdaFunction: writerFn,
    // Pass QA issues as additional context for the retry
});
```

---

#### 6. Tree of Thoughts (ToT)

**Status: 🚫 Not applicable.**

Tree of Thoughts requires exploring multiple generation branches simultaneously and pruning non-promising paths via a verifier. This requires either multiple parallel model calls at each decision node or a backtracking mechanism.

For article generation, the output space is a single document. There is no branching decision tree where separate narrative paths need to be evaluated and pruned. The structured outline produced by the Research Agent partially substitutes for this (section-level planning before writing), but the Writer Agent executes that plan linearly, not as a search.

**Closest analogue in the pipeline**: The `STRUCTURAL SCAN` thinking instruction tells the Writer to plan section variety in thinking space before writing. This is single-path reasoning-before-execution, not genuine ToT.

**Should it be added?** Only if you wanted to generate N structurally different article variants and let the QA agent select the best. The added cost (N × Writer tokens per article) is not justified for a solo developer publishing cadence.

---

#### 7. Search Against a Verifier

**Status: ✅ Applied — the QA Agent IS the verifier.**

The pipeline architecture maps directly onto the "search against a verifier" paradigm:

| Component | Role |
|---|---|
| Writer Agent | Generator (produces candidate solutions) |
| QA Agent | Verifier (scores solutions against 5 rubrics) |
| `QA_PASS_THRESHOLD = 80` | Acceptance criterion |
| `retryAttempt` counter | Search budget (number of candidates allowed) |

The Research Agent's `technicalFacts[]` array serves as a **ground-truth reference** that the QA verifier checks the Writer's claims against:

```typescript
// qa-agent.ts → buildQaMessage()
`## Technical Facts from Research Agent`,
`Cross-reference the article content against these verified facts:`,
...technicalFacts.map(f => `- ${f}`),
```

**What is missing**: The verifier signal is not fed back to the generator. Refer to Gap R5 for the revision loop.

**Gap R6 — Verifier Score as Reward Signal**: Store QA dimension scores in DynamoDB (already done) and use them over time to identify Which prompting patterns in the Writer lead to systematic QA failures. For example, if `technicalAccuracy` scores consistently drop on `category="IaC"` articles, the blog-persona.ts prompt needs a targeted IaC-specific instruction block. This is a lightweight form of reward modelling without requiring training.

---

### 13.3 Training-time Techniques

The following techniques are **training-time** methods — they require modifying the model's weights or behaviour through supervised fine-tuning or reinforcement learning, not prompt engineering or pipeline design.

---

#### 8. SFT on Reasoning Data (e.g., STaR — Self-Taught Reasoner)

**Status: ❌ Absent — not applicable to the current stack.**

STaR (Zeiler et al. 2022) and similar approaches involve generating chain-of-thought reasoning traces, filtering for those that lead to correct answers, and fine-tuning the base model on the collected traces.

**Is it relevant?** Theoretically yes — if you had 100+ published articles with QA scores, you could use the high-scoring ones as fine-tuning data for a smaller, faster model. **In practice**: The pipeline runs on managed Anthropic models via Bedrock. Fine-tuning Anthropic models is not available on Bedrock (at the time of writing — Bedrock Custom Model Import is limited to Llama, Mistral, etc.). This technique cannot be applied without changing the model provider.

**What is relevant**: The **data collected by the pipeline** (QA scores + Writer outputs + Research briefs) constitutes a training dataset if you ever wanted to fine-tune an open-source model (e.g., Llama 3.1 70B) as a cheaper Writer agent. The current DynamoDB schema already stores everything needed for this future option. No gap to add.

---

#### 9. Reinforcement Learning with a Verifier / Reward Modelling (ORM, PRM)

**Status: ❌ Absent — not applicable to the current stack, but the data infrastructure partially exists.**

- **Outcome Reward Model (ORM)**: A model trained to predict the binary pass/fail outcome (equivalent to `overallScore >= 80`). Not applicable — the QA agent itself performs this role at inference time.
- **Process Reward Model (PRM)**: A model trained to score intermediate reasoning steps, not just the final output. Not applicable — Bedrock Extended Thinking outputs are model-internal; you cannot directly supervise intermediate thinking steps.
- **RL with a Verifier**: Training the Writer model itself to maximise QA scores via policy gradient methods. Not applicable — Anthropic models cannot be fine-tuned via Bedrock.

**What IS applicable**: The QA agent already acts as a **proxy reward model** at inference time. The `overallScore` and 5 dimension scores are a structured reward signal. Using these scores for offline analysis (prompt A produces higher technical accuracy than prompt B across 50 articles) is a viable lightweight substitute for reward modelling. See Gap R6.

---

#### 10. Self-Refinement

**Status: ⚠️ Partial — structurally designed for it, but loop is not closed.**

Self-refinement (Madaan et al. 2023) involves a model critiquing its own output and producing a revised version. The pipeline has the structural components:

| Self-Refinement Component | Pipeline Equivalent |
|---|---|
| Initial generation | Writer Agent (first run) |
| Critique | QA Agent (`issues[]`, dimension scores) |
| Feedback injection | `retryAttempt` warning in Writer prompt |
| Revised generation | Writer Agent (next pipeline run) |

**The gap**: The critique (QA `issues[]`) is never **programmatically injected** into the Writer's input message on a retry. The Writer only receives a vague `"previous version did not pass QA"` warning. It does not receive specific criticism like:

```
## QA Feedback from Previous Run
- technicalAccuracy: [error] CDK L2 construct name `aws_lambda.Function` 
  is Python SDK syntax — TypeScript uses `lambda_.Function`. (location: Prerequisites)
- seoCompliance: [warning] meta description is 168 chars — exceeds 160 char limit.
```

This is exactly Gap R5 (in-pipeline revision loop). Self-refinement is the canonical framing for why R5 is high-value.

---

#### 11. Internalising Search (e.g., Meta-CoT)

**Status: 🚫 Not directly applicable.**

Meta-CoT and internalised search (Xiang et al. 2025) refer to training models to perform multi-step search inside their latent space without producing explicit intermediate text. This is an active research area and not something that can be engineered at the application layer.

**Closest approximation in the pipeline**: Extended Thinking serves a similar purpose — the model reasons in a hidden `<thinking>` block that is not part of the visible output. The `thinking` token budget functionally resembles "internalised search budget". This is already applied (see §13.2.1).

---

### 13.4 New Gaps from This Analysis

| # | Gap | Category | Severity | Effort |
|---|---|---|---|---|
| R1 | Discrete tier budgets — no continuous inference-time scaling | Inference Scaling | 🟢 Low | Low |
| R2 | Complexity re-evaluated on raw draft, not on Research Agent output | Inference Scaling | 🟡 Medium | Low |
| R3 | No few-shot CoT examples in system prompts (especially QA agent) | CoT Prompting | 🟡 Medium | Low |
| R4 | QA score not self-consistent — single sample gates publish/flag | Self-consistency | 🟡 Medium | Low |
| R5 | QA `issues[]` not fed back to Writer for in-pipeline revision | Self-Refinement / Sequential Revision | 🔴 High | Medium |
| R6 | QA scores not used as longitudinal reward signal for prompt evolution | Reward Modelling (proxy) | 🟡 Medium | Medium |

---

### 13.5 Updated Full Gap Summary

| # | Gap | Severity | Effort |
|---|---|---|---|
| S1 | No input sanitisation before model invocation | 🟡 Medium | Low |
| S2 | `KNOWLEDGE_BASE_ID` optional — silent degradation | 🟡 Medium | Low |
| S3 | No output sanitisation — ARNs/IPs in published articles | 🟡 Medium | Low |
| S4 | No rate limit on Trigger Lambda | 🟡 Medium | Medium |
| S5 | Slug divergence not surfaced as QA metric | 🟢 Low | Trivial |
| S6 | `bedrock:InvokeModel` wildcard foundation model ARN | 🟢 Low | Low |
| C1 | Cost lookup table not tied to live pricing | 🟡 Medium | Low |
| C2 | Prompt cache savings not netted from `PipelineCostUsd` | 🟢 Low | Low |
| C3 | No monthly Bedrock budget alarm | 🟡 Medium | Low |
| C4 | Failed pipeline partial cost not recorded | 🟢 Low | Low |
| P1 | No golden dataset for prompt regression testing | 🟡 Medium | Medium |
| P2 | No A/B prompt variant mechanism | 🟢 Low | Medium |
| P3 | `QA_PASS_THRESHOLD` is a hard-coded constant | 🟢 Low | Trivial |
| R1 | Discrete tier budgets — no continuous inference scaling | 🟢 Low | Low |
| R2 | Complexity not re-evaluated after Research Agent output | 🟡 Medium | Low |
| R3 | No few-shot CoT exemplars in system prompts | 🟡 Medium | Low |
| R4 | QA score unsampled — single pass gates publish/flag | 🟡 Medium | Low |
| **R5** | **QA `issues[]` not injected into Writer retry — no revision loop** | **🔴 High** | **Medium** |
| R6 | QA scores not used as longitudinal reward signal | 🟡 Medium | Medium |
