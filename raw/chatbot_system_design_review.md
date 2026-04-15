<!-- @format -->

# Bedrock Chatbot — LLM System Design Review

## 1. System Design Pattern — What Pattern Does It Follow?

**Short answer: it is a _RAG-Grounded Conversational Agent_, not a Deterministic Workflow Agent.**

A **Deterministic Workflow Agent** (e.g., the Article Pipeline or Strategist Pipeline in this repo) is characterised by:

- A pre-defined, explicit sequence of steps (Step Functions state machine)
- Multiple specialised LLM roles chained together (Researcher → Writer → QA)
- Structured, typed outputs passed between steps
- Deterministic progression with defined success/failure paths

The chatbot uses **none of these properties**. Instead it follows a **Single-Turn RAG Conversational Agent** pattern:

```
User Prompt → API Gateway → Lambda → Bedrock Agent (InvokeAgent)
                                         └── Guardrail eval
                                         └── KB retrieval (Pinecone → context)
                                         └── LLM inference (Claude Sonnet/EU cross-region)
                                         └── Guardrail output eval
                                     ← Streaming response assembled ← Lambda → User
```

Key properties of this pattern:
| Property | Value |
|---|---|
| LLM invocation style | `InvokeAgentCommand` (managed Bedrock Agent runtime) |
| Context injection | Automatic via Bedrock KB retrieval (RAG) at agent runtime |
| Instruction injection | Deploy-time static prompt (CfnAgent resource property) |
| Workflow orchestration | None — single synchronous call |
| State between turns | `sessionId` (Bedrock manages conversation memory per session) |
| Model routing | Single model via EU cross-region inference profile |

---

## 2. What Does the Chatbot Handle?

The Lambda handler (`index.ts`) is a **6-layer, defence-in-depth API Gateway proxy**. It handles:

1. **CORS resolution** — validates `Origin` header against the `ALLOWED_ORIGINS` env var whitelist
2. **Request parsing** — strict JSON body parse + `prompt` presence + length (≤ 10,000 chars)
3. **Session ID management** — validates UUID-v4 format if provided, generates `randomUUID()` if absent
4. **Input sanitisation (Layer 2)** — regex-pattern blocking (9 injection patterns, see §4)
5. **Agent invocation** — delegates to `chatbot-agent.ts` via `InvokeAgentCommand`
6. **Output sanitisation (Layer 5)** — regex redaction of ARNs, account IDs, IPs, credentials
7. **EMF metric emission** — `BedrockChatbot` namespace (InvocationCount, Latency, ResponseLength, BlockedInputs, RedactedOutputs)
8. **Structured audit logging** — SHA-256 prompt hash, session ID, latency, redaction flags
9. **Error classification** — `ValidationException → 400`, `ThrottlingException → 429`, unknown → `500`

**What it does NOT handle:**

- Multi-turn memory beyond `sessionId` (Bedrock manages that internally)
- Streaming to the client (chunks are buffered server-side, returned as one JSON payload)
- Content grounding verification at the Lambda layer (delegated to Bedrock Guardrail contextual grounding)

---

## 3. How Are Models Called?

The agent is called via **`InvokeAgentCommand`** (Bedrock Agent Runtime), not `ConverseCommand`:

```typescript
// chatbot-agent.ts
const command = new InvokeAgentCommand({
  agentId: config.agentId,
  agentAliasId: config.agentAliasId,
  sessionId,
  inputText: prompt, // user's sanitised prompt
});
const response = await client.send(command);

// Stream assembly
for await (const event of response.completion) {
  if ("chunk" in event && event.chunk?.bytes) {
    chunks.push(new TextDecoder("utf-8").decode(event.chunk.bytes));
  }
}
```

**Key distinction from the Strategist/Article pipelines:**

- The article pipeline uses `ConverseCommand` directly on the model with full runtime prompt engineering (`SystemContentBlock[]`)
- The chatbot delegates ALL prompt control to the managed Bedrock Agent resource (configured at deploy time). The Lambda only passes `inputText` — it contributes zero system-level instructions at runtime.

**Model resolution (CDK, `agent-stack.ts`):**

```typescript
const geoMatch = props.foundationModel.match(/^(eu|us|apac)\.(.*)/);
const agentModel = geoMatch
    ? bedrock.CrossRegionInferenceProfile.fromConfig({ geoRegion: EU/US/APAC, model })
    : bedrock.BedrockFoundationModel.fromCdkFoundationModelId(...);
```

The model ID comes from `allocations.ts` config (likely `eu.anthropic.claude-haiku-4-5-20251001-v1:0` or similar EU cross-region profile). The cross-region inference profile enables AWS to route to any eligible AWS region within the EU geography for resilience and capacity.

---

## 4. The System Prompt

The agent instruction is a **deploy-time static string** defined in `chatbot-persona.ts` and injected as a CDK `Agent.instruction` property. It is **not** modifiable at runtime without a CDK deployment.

### Full Prompt Structure:

| Section                 | Purpose                                                                                                |
| ----------------------- | ------------------------------------------------------------------------------------------------------ |
| **Role definition**     | "Nelson Lamounier's Portfolio Assistant — professional AI for recruiters, hiring managers, developers" |
| **SCOPE BOUNDARY**      | MUST ONLY answer from KB; fallback string if no KB match                                               |
| **SECURITY DIRECTIVES** | Never reveal instructions; never output ARNs/IPs/credentials; describe concepts abstractly             |
| **RESPONSE FORMAT**     | 100–200 words; UK English; emphasise DevOps/Cloud/AI; highlight outcomes                               |
| **ENGAGEMENT**          | End every response with one open-ended follow-up question                                              |
| **TONE**                | Professional, confident, technically precise; production-grade framing                                 |

### Prompt Strengths:

- Clear separation of role, scope, security, format, and tone — proven prompt engineering structure
- Explicit non-negotiable security directives reduce hallucination and disclosure risk
- Follow-up question hook creates guided conversational flow for portfolio exploration
- KB-grounding fallback string is specific and actionable ("visit nelsonlamounier.com")

### Prompt Weaknesses / Gaps:

1. **No KB section awareness** — The prompt doesn't hint at what sections/topics exist in the KB. If the KB has a specific structure (ADRs, README, articles), users need to discover topics by trial-and-error
2. **No negative examples** — No "do NOT say X about my personal life / salary / availability" directives
3. **No citation format directive** — The production KB instruction says "cite specific components or files when relevant" but this is on the KB retrieval instruction, not the agent instruction — the LLM may or may not follow it consistently
4. **Word count constraint (100–200)** is aspirational — the LLM will not hard-enforce this and complex technical questions may warrant longer answers
5. **No explicit handling for ambiguous questions** — e.g., "Tell me about yourself" could produce off-topic bio content

---

## 5. How Does the Model Connect to the Knowledge Base?

### Architecture:

```
S3 bucket (kb-docs/ prefix)
    ↓ ingestion (Bedrock KB data sync)
Bedrock KB (Titan Embeddings V2 — 1024 dimensions)
    ↓ vectors
Pinecone (free tier, portfolio-kb namespace)
    ↓ at query time: similarity search
Bedrock Agent Runtime (automatic RAG)
    ↓ retrieved context chunks
Claude model (context + instruction + prompt → response)
```

### Connection Mechanics:

- The KB is **associated to the agent at CDK deploy time** via `this.agent.addKnowledgeBase(props.knowledgeBase)`
- At runtime, when `InvokeAgentCommand` fires, the **Bedrock Agent Runtime automatically performs RAG**: it embeds the user's `inputText` using Titan Embeddings V2, searches Pinecone for the top-k nearest chunks, and injects them as context into the model's inference call
- The Lambda code has **zero knowledge of the KB** — it never calls Bedrock KB APIs directly, never passes a KB ID, never specifies retrieval parameters
- The KB instruction (`"Use this knowledge base to answer questions about the portfolio project..."`) guides how the agent uses retrieved content

---

## 6. Knowledge Base Structure

### Physical Storage (S3):

- Bucket: `{namePrefix}-kb-data` (versioned, SSL enforced, access logs to separate bucket)
- Only the `kb-docs/` prefix is indexed (explicit `inclusionPrefixes`)
- No other prefixes in the bucket are exposed to the KB (draft publications, etc. are separate)

### Chunking Strategy:

```
HIERARCHICAL_TITAN preset:
  Parent chunks: 1500 tokens  →  captures a full ## section
  Child chunks:  300 tokens   →  precise paragraph retrieval
  Overlap:       60 tokens    →  prevents hard cuts mid-sentence
```

This means the KB **expects Markdown documents with `##` heading structure**. Each `##` section becomes a parent chunk; paragraphs within it become child chunks.

### Vector Store:

- **Provider**: Pinecone (free tier, 100K vector limit)
- **Field mapping**: `text` (chunk content), `metadata` (source metadata)
- **Namespace**: `{pineconeNamespace}` from config (isolation per environment)
- **Dimensions**: 1024 (Titan Embed v2)

---

## 7. Is the Chatbot Tightly Coupled to KB Data Structure?

**Partially — and in carefully designed ways.**

### What IS coupled (intentionally):

| Coupling                                 | Location                                                   | Impact if changed                                                                        |
| ---------------------------------------- | ---------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| `kb-docs/` S3 prefix                     | `kb-stack.ts` `inclusionPrefixes`                          | Files uploaded to other prefixes will NOT be indexed — must keep this prefix convention  |
| `##` Markdown heading structure          | Chunking strategy assumption                               | Flat documents or different heading levels produce suboptimal chunks                     |
| Titan Embeddings V2 dimensions (1024)    | `knowledgeBaseId` + Pinecone index dimensions              | Changing embedding model requires re-creating the Pinecone index and re-syncing all docs |
| `metadata` / `text` Pinecone field names | `PINECONE_METADATA_FIELD`, `PINECONE_TEXT_FIELD` constants | Changing these without updating Pinecone index field config breaks retrieval             |

### What is NOT coupled (by design):

- **Document content** — The chatbot code has zero awareness of what specific documents are in the KB. You can add, remove, update any document and the chatbot adapts automatically after a data sync
- **Number of documents** — Adding 10 new README files requires no code change
- **Topic breadth** — The agent prompt explicitly falls back gracefully if KB has no match
- **Lambda code** — `invokeChatbotAgent` passes only `inputText` + `sessionId`. It never references KB IDs, document names, or topics

### Aggressive/Restrictive Approach:

Yes — the system intentionally restricts the model from answering outside KB scope via two enforcing mechanisms:

1. **Guardrail topic denial** (`OffTopicQueries`, `CodeGenerationRequests`) at HIGH strength — these reject at the Bedrock runtime before the model even sees the query
2. **Agent instruction SCOPE BOUNDARY** — a non-negotiable directive backed by the guardrail grounding filter (threshold 0.7)

This is an **aggressive, content-narrowing RAG design** — intentional for a public-facing portfolio chatbot where scope containment and professional framing matter more than breadth.

---

## 8. Does the Chatbot Need Code Changes if KB Data Structure Evolves?

| Change Type                                           | Requires Code Change?                  | What Changes                                          |
| ----------------------------------------------------- | -------------------------------------- | ----------------------------------------------------- |
| Add new Markdown files to `kb-docs/`                  | ❌ No                                  | Re-sync data source only                              |
| Rename a document                                     | ❌ No                                  | Re-sync data source only                              |
| Change document content                               | ❌ No                                  | Re-sync data source only                              |
| Change chunking strategy (e.g., FIXED → HIERARCHICAL) | ⚠️ CDK deploy only                     | `kb-stack.ts` + re-sync                               |
| Change Pinecone field names (`text`, `metadata`)      | ⚠️ CDK deploy only                     | `PINECONE_METADATA_FIELD` constants in `kb-stack.ts`  |
| Change embedding model (e.g., Titan v2 → Cohere)      | ⚠️ CDK deploy + Pinecone index rebuild | KB stack + re-index all documents                     |
| Change S3 prefix from `kb-docs/` to `docs/`           | ⚠️ CDK deploy only                     | `inclusionPrefixes` in `kb-stack.ts`                  |
| Add structured JSON data (non-Markdown)               | ⚠️ Potentially                         | May degrade chunking quality; custom splitter needed  |
| Change KB instruction wording                         | ⚠️ CDK deploy only                     | `configurations.ts` `knowledgeBase.instruction`       |
| Change agent system prompt                            | ⚠️ CDK deploy only                     | `chatbot-persona.ts` + CDK deploy (NOT Lambda deploy) |

**Key insight**: The chatbot Lambda (`index.ts`, `chatbot-agent.ts`) itself will **never** need to change due to KB structural evolution. The coupling surface is entirely in the CDK configuration layer (`kb-stack.ts`, `configurations.ts`, `chatbot-persona.ts`).

---

## 9. Security Assessment — Gaps

### ✅ Well-Implemented Security Controls

| Layer          | Control                                                               | Assessment        |
| -------------- | --------------------------------------------------------------------- | ----------------- |
| L1 (API GW)    | API Key + Usage Plan (10,000 req/month) + throttle                    | ✅ Solid          |
| L1 (API GW)    | Request body schema validation (`InvokeRequestModel`)                 | ✅ Solid          |
| L1 (API GW)    | JSON logging, X-Ray tracing enabled                                   | ✅ Solid          |
| L2 (Lambda)    | 9-pattern injection regex blocking                                    | ✅ Good coverage  |
| L2 (Lambda)    | UUID-format session ID validation                                     | ✅ Correct        |
| L2 (Lambda)    | CORS origin allowlist resolution                                      | ✅ Correct        |
| L3 (Guardrail) | SEXUAL, VIOLENCE, HATE, INSULTS, MISCONDUCT, PROMPT_ATTACK — all HIGH | ✅ Maximum        |
| L3 (Guardrail) | Topic denial: OffTopicQueries + CodeGenerationRequests                | ✅ Appropriate    |
| L3 (Guardrail) | Contextual grounding filter (GROUNDING + RELEVANCE at 0.7)            | ✅ Good threshold |
| L4 (Agent)     | Non-negotiable scope boundary + security directives in prompt         | ✅ Hardened       |
| L5 (Lambda)    | ARN, account ID, IP, credential regex redaction                       | ✅ Good baseline  |
| L6 (Audit)     | SHA-256 prompt hash, session ID, IP, redaction flags                  | ✅ Excellent      |

---

### ⚠️ Security Gaps Requiring Attention

#### Gap 1 — No WAF on API Gateway

```typescript
// api-stack.ts — line 286
// "WAFv2 WebACL not required for development portfolio API; add for production"
```

**Risk**: A public portfolio chatbot is a valid brute-force and abuse target. WAF would add:

- Rate limiting at the edge (not just at the usage plan level)
- IP-based reputation blocking
- Managed rule groups (Core Rule Set, Bot Control)

**Recommendation**: Add `aws-wafv2` WebACL with `AWSManagedRulesCommonRuleSet` and `AWSManagedRulesBotControlRuleSet` and associate it with the API Gateway stage. For a portfolio project, the free managed rules are sufficient.

#### Gap 2 — No Cognito / JWT Authoriser; API Key Exposed to Frontend

The API uses API Key auth (`x-api-key` header). This means the API key must be embedded in the frontend. Any visitor who opens DevTools can extract and abuse it.

**Risk**: The usage plan quota (10,000/month) mitigates this but doesn't prevent distributed abuse from multiple IPs that each stay under the quota.

**Options to consider**:

- Short-lived pre-signed tokens (APIG Lambda authoriser + simple HMAC)
- Recaptcha v3 verification in the request flow
- Rate-limit per IP at WAF level (addresses Gap 1 simultaneously)

#### Gap 3 — Output Redaction is Pattern-Only (No Semantic Check)

The output sanitiser catches syntactically recognisable patterns (ARN regex, 12-digit numbers, IP regex). However, the LLM could leak:

- Domain names (e.g., `k8s.prod.internal`)
- Named Kubernetes cluster names
- Database table names embedded in explanatory prose

**Risk**: Low-medium. The agent instruction + guardrail grounding at 0.7 provide semantic-level mitigation. But a KB document that happens to contain a specific cluster name verbatim could leak it.

**Recommendation**: Add defensive patterns for:

```typescript
{ regex: /\b[a-z][a-z0-9-]{2,62}\.(internal|local|cluster\.local)\b/gi, replacement: '[Internal Host]' }
```

#### Gap 4 — `PROMPT_ATTACK` Guardrail Has `outputStrength: NONE`

```typescript
// agent-stack.ts — line 112-116
this.guardrail.addContentFilter({
  type: bedrock.ContentFilterType.PROMPT_ATTACK,
  inputStrength: bedrock.ContentFilterStrength.HIGH,
  outputStrength: bedrock.ContentFilterStrength.NONE,
});
```

`outputStrength: NONE` on `PROMPT_ATTACK` is intentional (the model shouldn't _output_ prompt injection text), but it means the guardrail won't flag model output that mimics a system-prompt-leaking pattern. This is an acceptable trade-off but should be a **conscious, documented** decision.

**Recommendation**: Add a code comment explaining this decision: "NONE because the model is not expected to output attack patterns; only inputs need blocking."

#### Gap 5 — No Request-Level User Identity Tracking

The audit log records `sourceIp` and generates a `sessionId`, but there is no persistent user identity. A single user who rotates sessions cannot be correlated for abuse pattern detection.

**Recommendation**: Consider adding a stable client fingerprint (e.g., hashed `User-Agent + IP`) to the audit log for cross-session correlation without storing PII.

#### Gap 6 — Lambda IAM Permissionset is Too-Broad ARN

```typescript
// api-stack.ts — line 134
`arn:aws:bedrock:${this.region}:${this.account}:agent-alias/${agentId}/${agentAliasId}`;
```

SSM dynamic resolution means `agentId` and `agentAliasId` are `Token` values at synth time — CloudFormation resolves them at deploy time. This is correct. However, because these are SSM-resolved tokens, the IAM ARN contains `{{resolve:ssm:...}}` at synth time. Verify the actual resolved ARN in the deployed IAM policy matches the expected pattern (this is a CDK SSM dynamic resolution pitfall).

---

## 10. Cost Monitoring — Current State and Gaps

### ✅ What Exists

**Application Inference Profiles** (in `data-stack.ts`):

```typescript
// 4 profiles with consistent tags:
{ key: 'project', value: 'bedrock' }
{ key: 'cost-centre', value: 'application' }
{ key: 'component', value: 'article-pipeline' | 'strategist' }
{ key: 'environment', value: props.environmentName }
{ key: 'owner', value: 'nelson-l' }
{ key: 'managed-by', value: 'cdk' }
```

These profiles enable AWS Cost Explorer to break down Bedrock inference costs per pipeline (article vs. strategist).

**EMF Metrics** (in chatbot `index.ts`):

- `InvocationCount` — total requests
- `InvocationLatency` — p50/p95/p99 visible in CloudWatch
- `ResponseLength` — output token proxy
- `PromptLength` — input token proxy
- `BlockedInputs` — security filter hits
- `RedactedOutputs` — output sanitisation hits
- `InvocationErrors` — error rate

**CloudWatch Logs**:

- Lambda log group with configurable retention (1 week dev, 3 months prod)
- API Gateway access logs with full JSON fields including `responseLength`

---

### ❌ Cost Monitoring Gaps

#### Gap A — **No Bedrock token-level cost metric**

The EMF metrics track `PromptLength` (characters) and `ResponseLength` (characters), but Bedrock bills on **tokens**. Characters ≠ tokens (roughly 4 chars/token for English, but varies).

**Recommendation**: Use the `InvokeAgentCommand` response's `usage` field (if available in the streaming event) to capture actual input/output token counts, and emit them as EMF:

```typescript
{ name: 'InputTokens', value: usage.inputTokens, unit: 'Count' }
{ name: 'OutputTokens', value: usage.outputTokens, unit: 'Count' }
```

#### Gap B — **No Application Inference Profile for the Chatbot Agent**

The 4 Application Inference Profiles in `data-stack.ts` cover article-pipeline and strategist pipelines. The **chatbot agent** uses a direct cross-region inference profile defined in `agent-stack.ts` with no cost-allocation tags. Chatbot invocations cannot be distinguished from other Bedrock usage in Cost Explorer.

**Recommendation**: Create a 5th Application Inference Profile for the chatbot agent with `component: 'chatbot'` tag.

#### Gap C — **No budget alarm or cost anomaly detector**

There is no `aws-budgets` CDK construct or AWS Cost Anomaly Detection configuration for the Bedrock project.

**Recommendation for a public chatbot**:

```typescript
// Add to data-stack.ts or a separate monitoring-stack
new budgets.CfnBudget(this, 'BedrockMonthlyCost', {
    budget: {
        budgetType: 'COST',
        timeUnit: 'MONTHLY',
        budgetLimit: { amount: 20, unit: 'USD' },
        costFilters: { Service: ['Amazon Bedrock'] },
    },
    notificationsWithSubscribers: [{ ... emailAlert ... }],
});
```

#### Gap D — **No Guardrail invocation cost tracking**

Each Bedrock Guardrail evaluation costs per-unit. If the guardrail blocks many requests, this adds up. There is no metric or cost filter specifically for guardrail evaluations.

---

## 11. Prompt Testing & Evolution Strategy

### Current State

The system prompt lives in `chatbot-persona.ts` (infra config). To change and test the prompt:

1. Edit `chatbot-persona.ts`
2. Run `cdk deploy Bedrock-Agent-development`
3. Manual test via Postman / frontend
4. No automated evaluation framework exists

### Gaps

1. **No prompt regression test suite** — there are no tests that assert "given this question, the agent produces a response that mentions X and does not mention Y"
2. **No A/B testing mechanism** — only one agent alias (`{prefix}-live`) exists. No shadow alias for testing prompt variants
3. **No prompt evaluation metrics** — no automated scoring against a golden dataset

### Recommended Evolution Strategy

#### Short-term (no additional infra)

Create a `prompt-eval/` directory in `bedrock-applications/` with:

```typescript
// prompt-eval/src/golden-dataset.ts
const GOLDEN_DATASET = [
  {
    question: "What cloud certifications does Nelson hold?",
    mustContain: ["AWS", "certification"],
    mustNotContain: ["ARN", "account"],
    maxWords: 250,
  },
  // Add 10-20 representative questions covering each KB topic area
];
```

Run this as a CI step against the development agent on a schedule.

#### Medium-term (multi-alias)

Add a `test` alias pointing to an agent version with a draft prompt. The Lambda can accept a `target: 'test' | 'live'` field that routes to the appropriate alias ARN (but only for authenticated admin requests, not public).

#### Long-term

Integrate **Bedrock Evaluation Jobs** (GA'd 2024) to score the agent against a ground-truth dataset using automated metrics (ROUGE-L, semantic similarity). This directly addresses prompt evolution validation as the KB and business requirements change.

---

## 12. Implementation Gaps Summary

| #   | Gap                                                                | Severity  | Effort  |
| --- | ------------------------------------------------------------------ | --------- | ------- |
| S1  | No WAF on API Gateway (production blocker)                         | 🔴 High   | Medium  |
| S2  | API Key exposed to browser (no token exchange)                     | 🟡 Medium | Medium  |
| S3  | Output redaction misses internal hostnames/cluster names           | 🟡 Medium | Low     |
| S4  | `PROMPT_ATTACK outputStrength: NONE` undocumented rationale        | 🟢 Low    | Trivial |
| S5  | No cross-session user fingerprint for abuse correlation            | 🟢 Low    | Low     |
| C1  | No token-level cost metric (chars ≠ tokens)                        | 🟡 Medium | Low     |
| C2  | Chatbot agent has no cost-allocation Application Inference Profile | 🟡 Medium | Low     |
| C3  | No monthly budget alarm for Bedrock                                | 🟡 Medium | Low     |
| C4  | No guardrail cost tracking                                         | 🟢 Low    | Low     |
| P1  | No automated prompt regression tests                               | 🟡 Medium | Medium  |
| P2  | No multi-alias prompt A/B mechanism                                | 🟢 Low    | Medium  |
| P3  | Agent instruction missing KB topic discovery hints                 | 🟢 Low    | Trivial |

---

## 13. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│  Bedrock Chatbot — Request Lifecycle                        │
│                                                             │
│  Client                                                     │
│    │ POST /invoke { prompt, sessionId? }                    │
│    ▼                                                        │
│  API Gateway (REST)                                         │
│    ├─ API Key auth (x-api-key)                              │
│    ├─ Request body schema validation (InvokeRequestModel)   │
│    ├─ Usage Plan: 10,000 req/month, throttle               │
│    └─ X-Ray + JSON access logs                             │
│    ▼                                                        │
│  Lambda (Node 22, NODEJS_22_X)                              │
│    ├─ L1: CORS origin resolution                            │
│    ├─ L2: Input sanitisation (9 injection patterns)         │
│    ├─ Session ID (UUID validate / randomUUID generate)      │
│    │                                                        │
│    ▼                                                        │
│  Bedrock Agent Runtime (InvokeAgentCommand)                 │
│    ├─ L3: Guardrail — content filters (HIGH) + topic denial │
│    ├─ KB Retrieval: inputText → Titan Embed → Pinecone →    │
│    │                top-k chunks → context injection        │
│    ├─ Claude model inference                                │
│    │   (system: chatbot-persona instruction, deploy-time)   │
│    ├─ L3: Guardrail — output eval + grounding (0.7)         │
│    └─ Streaming response (chunks → assembled string)        │
│    ▼                                                        │
│  Lambda (post-processing)                                   │
│    ├─ L5: Output sanitisation (ARN/IP/credential redaction) │
│    ├─ L6: Audit log (prompt hash, session, latency, flags)  │
│    └─ EMF metrics → CloudWatch                             │
│    ▼                                                        │
│  Client: { response: string, sessionId: string }            │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  Knowledge Base Pipeline                                    │
│                                                             │
│  S3 bucket (bedrock-development-kb-data)                    │
│    └─ kb-docs/ prefix (Markdown files, ## heading format)   │
│    ▼ manual/scheduled data source sync                       │
│  Bedrock KB (Titan Embeddings V2, 1024 dims)                │
│    └─ HIERARCHICAL_TITAN chunking                           │
│       Parent: 1500 tokens, Child: 300 tokens, Overlap: 60   │
│    ▼ vectors                                                │
│  Pinecone (free tier, portfolio namespace, 100K vector cap) │
│    Fields: text (content), metadata (source)                │
└─────────────────────────────────────────────────────────────┘
```

---

## 14. Adaptation & RAG Techniques — What Is Applied and What Is Missing?

This section maps each technique from the review list against the chatbot implementation, citing source code evidence where applicable. Techniques are evaluated relative to this specific system — a public-facing, scope-constrained, single-turn RAG conversational agent for a developer portfolio.

---

### 14.1 Technique Legend

- ✅ **Applied** — demonstrably implemented
- ⚠️ **Partial / Implicit** — approximated but not formally specified
- ❌ **Absent but Relevant** — would improve the system
- 🚫 **Not Applicable** — does not fit this use case or stack

---

### 14.2 Adaptation Techniques

---

#### A. Fine-tuning

**Status: 🚫 Not applicable to the current stack.**

Fine-tuning requires retraining or updating model weights on a labelled dataset to specialise the model's knowledge or behaviour. Anthropic Claude models on Bedrock **cannot be fine-tuned by customers** (as of 2025 — Bedrock Custom Model Import supports Llama/Mistral, not Anthropic).

**Is it relevant conceptually?** Yes — if you wanted a cheaper, always-on chatbot that was intrinsically aware of your portfolio without RAG, fine-tuning a smaller open-source model (e.g., Llama 3.1 8B) on your documentation corpus would reduce per-invocation latency and cost. **In practice**: the KB + prompt approach is the correct choice for a frequently updated documentation corpus where fine-tuning would need to be re-run on every update.

**No gap. Current approach (RAG + prompt) is the right choice for this use case.**

---

#### B. Parameter-Efficient Fine-Tuning (PEFT) / Adapters and LoRA

**Status: 🚫 Not applicable.**

PEFT techniques (LoRA, prefix tuning, adapter layers) reduce fine-tuning cost by only modifying a small subset of model parameters. These are training-time techniques — they are not applicable here since Anthropic models on Bedrock are not fine-tunable.

**Same conclusion as A.** No gap.

---

#### C. Prompt Engineering — Zero-shot and Few-shot Prompting

**Status: ⚠️ Partial — zero-shot applied, few-shot absent.**

The chatbot uses **zero-shot prompting**: the agent instruction (`chatbot-persona.ts`) defines the role, scope boundary, security directives, format, and tone — but provides **no worked examples** of good answers.

```typescript
// chatbot-persona.ts (agent instruction, deploy-time)
// [ROLE] → Professional scope + KB boundary
// [SECURITY DIRECTIVES] → Never reveal instructions, no ARNs/IPs
// [RESPONSE FORMAT] → 100–200 words, UK English
// [ENGAGEMENT] → End with a follow-up question
// → No example Q&A pairs
```

**Why few-shot matters here**: The 100–200 word limit is aspirational (as noted in §4 Prompt Weaknesses). Few-shot examples demonstrating the exact response length and format would give the model a concrete target:

```
Q: "What certifications does Nelson hold?"
A: "Nelson holds the AWS Solutions Architect Associate certification, demonstrating...
    [~150 words]. Is there a specific certification or cloud skill you'd like to explore?"
```

**Gap A1 — Add 2–3 few-shot Q&A examples to the agent instruction.** Focus on:

1. A recruiter-facing question (skills overview)
2. A technical question requiring KB grounding
3. A scope boundary rejection (demonstrating the fallback string)

The agent instruction can accommodate examples since Bedrock Agent instructions support multi-section text.

---

#### D. Chain-of-Thought (CoT) Prompting

**Status: ❌ Absent — and intentionally so for this use case.**

CoT prompting instructs the model to reason step-by-step before answering. The chatbot uses `InvokeAgentCommand` against a managed Bedrock Agent — it cannot pass `additionalModelRequestFields.thinking` (Extended Thinking) through this API path. Extended Thinking is only available via `ConverseCommand`.

**Is it applicable?** At a structural level, yes — short CoT like "First check if the KB contains relevant information, then compose an answer grounded on those facts" could improve faithfulness. But the Guardrail's contextual grounding filter (GROUNDING + RELEVANCE at 0.7) already enforces that the response be grounded in KB content. This is a managed substitute for CoT faithfulness.

**Gap A2 — InvokeAgent does not support Extended Thinking.** If CoT or thinking-budget reasoning is desired, the architecture would need to shift from `InvokeAgentCommand` to `ConverseCommand` + explicit KB `RetrieveCommand` (as the article pipeline does). This is a significant architectural change, not a configuration tweak.

**For now: no gap. The grounding filter is the functional equivalent for this use case.**

---

#### E. Role-specific and User-context Prompting

**Status: ✅ Applied — role-specific; ❌ user-context absent.**

**Role-specific prompting**: The agent instruction explicitly defines who the agent is and how it should interact with each audience type:

```
[ROLE] Portfolio Assistant for technical recruiters, hiring managers, and developers
[TONE] Professional, confident, technically precise
[ENGAGEMENT] Always ends with a follow-up question to guide exploration
```

This is well-implemented role specification.

**User-context prompting**: The `InvokeAgentCommand` only passes `inputText` + `sessionId`. There is **no mechanism to pass caller context** (e.g., `X-Caller-Role: recruiter`) that would allow the agent to dynamically adjust its tone or depth of technical detail. Every user gets the same response register regardless of whether they're a CTO or a non-technical recruiter.

**Gap A3 — No user-context injection at invocation time.** The Bedrock Agent `InvokeAgentCommand` supports a `sessionAttributes` map that persists across a session and `promptSessionAttributes` that are available for the current turn. These can inject caller context:

```typescript
// chatbot-agent.ts — proposed enhancement
const command = new InvokeAgentCommand({
  agentId: config.agentId,
  agentAliasId: config.agentAliasId,
  sessionId,
  inputText: prompt,
  promptSessionAttributes: {
    callerRole: "recruiter" | "engineer" | "unknown",
    // Populated from request headers or a lightweight classifier
  },
});
```

The agent instruction could then adapt: `If callerRole=recruiter, focus on outcomes and impact. If callerRole=engineer, include technical depth and file paths.`

---

### 14.3 RAG Techniques

---

#### F. Retrieval — Document Parsing Strategies

**Status: ⚠️ Partial — rule-based only; no AI-based parsing.**

The KB ingests Markdown documents from S3 (`kb-docs/` prefix). Bedrock KB performs document parsing internally before chunking. The chunking strategy is:

```typescript
// kb-stack.ts
chunkingStrategy: bedrock.ChunkingStrategy.HIERARCHICAL_TITAN,
// Parent: 1500 tokens (full ## section)
// Child:  300 tokens (paragraph)
// Overlap: 60 tokens (sentence continuity)
```

This is **rule-based parsing**: the HIERARCHICAL_TITAN preset splits on token count with overlap, expecting `##` Markdown heading boundaries. There is no AI-based parsing (e.g., structural understanding of tables, code blocks, or nested lists).

**Gap A4 — Code blocks and tables are not semantically distinguished.** A 300-token child chunk that contains a mix of prose and a code block will be embedded as a single undifferentiated chunk. When a recruiter asks "What CDK code did you write?", the retrieval may return chunks that are 90% prose and 10% code.

Bedrock KB (2024+) supports **custom parsing with foundation models** (`ParsingStrategy.FOUNDATION_MODEL`) for semantic document understanding. For a portfolio KB where code snippets and architectural decisions are first-class content, AI-based parsing would produce meaningfully better retrieval targets.

**Gap A5 — No document pre-processing pipeline.** Documents are uploaded raw to S3. There is no step that:

- Strips YAML frontmatter before indexing (frontmatter tokens reduce chunk quality)
- Extracts code blocks into separate semantic units
- Adds section-level metadata (e.g., `category: IaC`, `technology: CDK`) for filtered retrieval

---

#### G. Retrieval — Indexing Strategy

**Status: ✅ Applied (vector-based); ❌ Hybrid/keyword absent.**

The KB uses **pure vector-based indexing** via Titan Embeddings V2 (1024 dimensions) into Pinecone. This is the canonical semantic search approach:

```typescript
// kb-stack.ts
embeddingsModel: bedrock.BedrockFoundationModel.TITAN_EMBED_TEXT_V2_1024,
vectorStore: pineconeStore, // Pinecone vector similarity
```

Search method: **approximate nearest neighbour** (ANN) — Pinecone uses HNSW by default.

**What is absent**: **Hybrid search** (vector + keyword/BM25). For a technical portfolio KB, exact term matches matter:

- `"ConverseCommand"` — a specific AWS SDK method name
- `"HIERARCHICAL_TITAN"` — an exact Bedrock constant
- CDK construct names, Helm chart names, error codes

Pure vector search can struggle with rare technical terms that have no semantic neighbours. A hybrid index (dense + sparse retrieval with reciprocal rank fusion) significantly improves recall for exact technical terms.

**Gap A6 — No hybrid retrieval (vector + keyword).** Bedrock KB does not natively support hybrid retrieval in the HIERARCHICAL preset. This would require either:

1. Switching to a custom retrieval pipeline (`RetrieveCommand` + Pinecone hybrid search API)
2. Adding a pre-embedding keyword fallback (if Pinecone introduces hybrid support)

This is a medium-effort architectural change but high-value for a technical portfolio where exact term lookup matters.

---

#### H. Generation — Search Methods

**Status: ✅ Applied — ANN via Pinecone HNSW.**

Pinecone uses **Approximate Nearest Neighbour** (HNSW algorithm) for vector similarity search. This is implicit in the Pinecone integration — `PineconeVectorStore` does not expose a `searchMethod` property; ANN is always used.

**Exact nearest neighbour** (exhaustive search) would be more accurate but is O(n) and impractical at scale. For a 100K-vector portfolio KB, ANN recall is effectively equivalent to exact for this corpus size.

**No gap — correct choice for this scale.**

---

#### I. Generation — Prompt Engineering for RAGs

**Status: ⚠️ Partial — two prompt surfaces exist; only one is well-engineered.**

The RAG system has **two distinct prompt surfaces**:

| Surface               | Location                            | Content                                                                                                                                                   | Engineering Quality                |
| --------------------- | ----------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------- |
| **KB instruction**    | `configurations.ts → kbInstruction` | "Use this knowledge base to answer questions about the portfolio project. When citing information, reference specific components or files when relevant." | ⚠️ Minimal — no retrieval guidance |
| **Agent instruction** | `chatbot-persona.ts`                | Full role, scope, security, format, tone                                                                                                                  | ✅ Well-structured                 |

The **KB instruction is thin**. It does not guide the model on:

- How to handle conflicting retrieved passages
- What to do when retrieved chunks are partially relevant but contain noise
- How to signal confidence level when the KB has partial information
- How to cite sources (file names? section headings? both?)

**Gap A7 — KB instruction needs retrieval-aware prompt engineering.** Recommended additions:

```
If retrieved passages are partially relevant, answer from what IS directly supported
and explicitly state: "Based on the available documentation..." for unsupported parts.

When citing sources, reference the document name and section heading if available
(e.g., "According to the CDK Monitoring README, §Architecture...").

If multiple passages contradict each other, use the most recent source and note
the discrepancy briefly.
```

---

#### J. RAFT — Retrieval Augmented Fine-Tuning

**Status: 🚫 Not applicable to the current stack.**

RAFT (Zhang et al. 2024) is a training-time technique: it fine-tunes a model on (question, retrieved context, answer) triplets, teaching the model to ignore irrelevant retrieved passages ("distractors") and extract the signal from genuinely relevant ones. It requires model fine-tuning.

**Is it relevant?** Conceptually — the chatbot's Guardrail contextual grounding filter (GROUNDING at 0.7) achieves a similar goal at inference time: responses that are not grounded in retrieved context are blocked. This is a managed, inference-time substitute for what RAFT achieves via training.

**No gap. The guardrail grounding filter is the correct production-ready substitute.**

---

#### K. RAG Evaluation — Context Relevance, Faithfulness, Answer Correctness

**Status: ❌ Absent — no automated RAG evaluation pipeline.**

This is the most significant systematic gap in the chatbot's RAG design. The three canonical RAG evaluation dimensions are:

| Dimension              | Definition                                                | Current State                                                  |
| ---------------------- | --------------------------------------------------------- | -------------------------------------------------------------- |
| **Context relevance**  | Are the retrieved chunks relevant to the question?        | ❌ Not measured at runtime or offline                          |
| **Faithfulness**       | Is the answer grounded in the retrieved context?          | ⚠️ Proxy: Guardrail GROUNDING at 0.7 (blocking, not measuring) |
| **Answer correctness** | Is the answer factually correct relative to ground truth? | ❌ No golden dataset; no automated scoring                     |

The Guardrail grounding filter **blocks** unfaithful responses but does not **measure** the retrieval quality that caused a poor-quality inference in the first place. If Pinecone consistently returns low-relevance chunks for a query class, there is no observable signal.

**Gap A8 — No RAG evaluation pipeline (highest-value new gap).** Recommended implementation using Bedrock Evaluation Jobs (GA 2024):

```typescript
// Offline evaluation cadence (weekly/on KB update)
1. Maintain a golden Q&A dataset (20–50 representative questions + expected answers)
2. Run InvokeAgent against each question (dev environment)
3. Capture: { question, retrievedChunks, generatedAnswer }
4. Score via Bedrock Evaluation:
   - Context relevance: embedding cosine similarity (question vs. retrieved chunk)
   - Faithfulness: NLI model or Claude-as-judge (does answer contradict retrieved context?)
   - Answer correctness: ROUGE-L / BERTScore against golden answers
5. Alert if any dimension drops below threshold across the dataset
```

This closes the feedback loop that the current system completely lacks: you currently have no way of knowing whether the chatbot's answer quality has degraded after a KB update.

---

#### L. RAG Overall Design — HIERARCHICAL Chunking

**Status: ✅ Applied — HIERARCHICAL_TITAN with correct rationale.**

The chunking design is well-chosen and the CDK comment explains the rationale:

```typescript
// kb-stack.ts — lines 179–185
// Chunking: HIERARCHICAL_TITAN preset
//   Parent chunks: 1500 tokens (captures a full ## section)
//   Child chunks:  300 tokens  (precise paragraph retrieval)
//   Overlap:       60 tokens   (prevents hard cuts mid-sentence)
//
// This aligns with the KB's Markdown heading structure —
// each ## section becomes a parent chunk with its paragraphs
// as child chunks, preserving section-level context.
```

**What hierarchical chunking achieves**: At retrieval time, Bedrock KB returns child chunks (precise), but appends the parent chunk (section context) so the model has both local detail and broader context. This is the recommended strategy for structured Markdown documentation.

**Remaining design risk**: If documents are poorly structured (no `##` headings, single-level paragraphs, or walls of code), the hierarchical assumption breaks and child chunks lose their semantic coherence. There is no validation that ingested documents conform to the expected structure.

**Gap A4 (repeat)**: The S3 document upload path has no schema validation to enforce `##` heading structure before ingestion. A lightweight pre-processing Lambda (or a developer guide) would prevent accidentally degrading retrieval quality with flat documents.

---

### 14.4 New Gaps from This Analysis

| #      | Gap                                                                                | Category                   | Severity    | Effort             |
| ------ | ---------------------------------------------------------------------------------- | -------------------------- | ----------- | ------------------ |
| A1     | No few-shot Q&A examples in agent instruction                                      | Prompt Engineering         | 🟡 Medium   | Low                |
| A2     | Extended Thinking unavailable via `InvokeAgentCommand`                             | CoT / Inference            | 🟢 Low      | High (arch change) |
| A3     | No user-context injection via `promptSessionAttributes`                            | Role/Context Prompting     | 🟡 Medium   | Low                |
| A4     | YAML frontmatter + code blocks not pre-processed before ingestion                  | Document Parsing           | 🟡 Medium   | Low                |
| A5     | No document structure validation before S3 upload                                  | Indexing                   | 🟢 Low      | Low                |
| A6     | Pure vector retrieval — no hybrid keyword+vector search                            | Retrieval                  | 🟡 Medium   | Medium             |
| A7     | KB instruction lacks retrieval-aware guidance (conflict handling, citation format) | Prompt Engineering for RAG | 🟡 Medium   | Low                |
| **A8** | **No RAG evaluation pipeline (context relevance, faithfulness, correctness)**      | **Evaluation**             | **🔴 High** | **Medium**         |

---

### 14.5 Updated Full Gap Summary

| #      | Gap                                                                      | Severity    | Effort             |
| ------ | ------------------------------------------------------------------------ | ----------- | ------------------ |
| S1     | No WAF on API Gateway                                                    | 🔴 High     | Medium             |
| S2     | API Key exposed to browser                                               | 🟡 Medium   | Medium             |
| S3     | Output redaction misses internal hostnames                               | 🟡 Medium   | Low                |
| S4     | `PROMPT_ATTACK outputStrength: NONE` undocumented                        | 🟢 Low      | Trivial            |
| S5     | No cross-session user fingerprint                                        | 🟢 Low      | Low                |
| C1     | No token-level cost metric (chars ≠ tokens)                              | 🟡 Medium   | Low                |
| C2     | Chatbot has no cost-allocation Application Inference Profile             | 🟡 Medium   | Low                |
| C3     | No monthly Bedrock budget alarm                                          | 🟡 Medium   | Low                |
| C4     | No guardrail invocation cost tracking                                    | 🟢 Low      | Low                |
| P1     | No automated prompt regression tests                                     | 🟡 Medium   | Medium             |
| P2     | No multi-alias prompt A/B mechanism                                      | 🟢 Low      | Medium             |
| P3     | Agent instruction missing KB topic discovery hints                       | 🟢 Low      | Trivial            |
| A1     | No few-shot Q&A examples in agent instruction                            | 🟡 Medium   | Low                |
| A2     | Extended Thinking unavailable via `InvokeAgentCommand`                   | 🟢 Low      | High (arch change) |
| A3     | No user-context injection via `promptSessionAttributes`                  | 🟡 Medium   | Low                |
| A4     | YAML frontmatter + code blocks not pre-processed before ingestion        | 🟡 Medium   | Low                |
| A5     | No document structure validation before S3 upload                        | 🟢 Low      | Low                |
| A6     | Pure vector retrieval — no hybrid keyword+vector search                  | 🟡 Medium   | Medium             |
| A7     | KB instruction lacks retrieval-aware guidance                            | 🟡 Medium   | Low                |
| **A8** | **No RAG evaluation pipeline — zero observability on retrieval quality** | **🔴 High** | **Medium**         |
