# TypeScript Code Review — Job Strategist Pipeline

## Files Reviewed

| File | Role |
|------|------|
| `agents/research-agent.ts` | Pipeline intelligence — KB retrieval, gap analysis |
| `handlers/research-handler.ts` | Lambda entry point → delegates to research agent |
| `handlers/strategist-handler.ts` | Stage 2 — runs strategist agent, S3 offload |
| `handlers/resume-builder-handler.ts` | Stage 3 — builds tailored resume |
| `handlers/coach-loader-handler.ts` | Coaching pipeline entry — loads DDB analysis |
| `handlers/coach-handler.ts` | Coaching pipeline terminal — runs coach agent, persists |

---

## 1. Class vs. Function — The Right Structure?

### Verdict: ✅ Functions are the correct choice here

Apply the decision criteria systematically:

| Question | `research-agent.ts` | Handlers |
|---|---|---|
| Does it maintain state between calls? | **NO** — `cachedWikiMcpAuth` is module-level mutable state, not instance state | **NO** — each Lambda invocation is independent |
| Multiple functions operating on the same data shape? | Yes, but they form a pipeline, not an OO object | No — each handler is a single-purpose function |
| Standalone transformation, no shared state? | Mostly yes | Yes — pure request/response |
| Inheritance or polymorphism? | No | No |

**All six files are correctly implemented as functions.** These are Lambda handlers and service-layer helpers — stateless, single-purpose, invoked once per request. A class would add instantiation overhead and lifecycle complexity that AWS Lambda does not need.

### ⚠️ One Nuance — `cachedWikiMcpAuth` in `research-agent.ts`

```typescript
// Lines 153–154
let cachedWikiMcpAuth = '';
```

This is a **module-level mutable variable** acting as a lazy singleton cache. It is technically "state between calls" but only within the same Lambda execution context (warm start). This is an intentional AWS Lambda caching pattern and is fine — **but it should be documented more clearly as a Lambda-context cache**, not a general in-memory cache.

> [!TIP]
> Consider renaming to `_lambdaContextWikiMcpAuthCache` or moving the comment up next to the `let` declaration to make the warm-start intent unmistakable.

---

## 2. Arrow Function Patterns

### Standard Pattern Used

All handlers use the **named const arrow function** pattern:

```typescript
export const handler = async (
    event: SomeInput,
): Promise<SomeOutput> => {
    // ...
};
```

All agent functions use the **named `function` declaration** pattern:

```typescript
export async function executeResearchAgent(
    ctx: StrategistPipelineContext,
): Promise<AgentResult<StrategistResearchResult>> {
    // ...
}
```

### Is This the Right Pattern?

| Style | Where Used | Appropriate? |
|---|---|---|
| `export const handler = async (...) => {}` | All 5 handlers | ✅ Yes — Lambda handlers are conventionally named const exports |
| `export async function executeXxx(...)` | `research-agent.ts` | ✅ Yes — named function declarations hoist and are easier to mock in tests |
| Private `async function querySingleKb(...)` | `research-agent.ts` | ✅ Yes — module-private helpers |
| Private `function buildResearchMessage(...)` | `research-agent.ts` | ✅ Yes — pure transformation, synchronous |

**Consistency judgement:** All five handlers use the arrow const pattern; all agent "business logic" functions use the `function` keyword. This is a reasonable and consistent split.

> [!NOTE]
> The only inconsistency worth noting: `deduplicatePassages()` (sync) uses `function`, while `resolveWikiMcpAuth()` and `getWikiMcpConstraints()` (async) also use `function`. This is perfectly fine and consistent — just worth confirming it's deliberate.

---

## 3. Data Types & Structures — Full Walkthrough

### 3.1 The Core Generic Wrapper: `AgentResult<T>`

Every agent wraps its output in this generic:

```typescript
// From shared/src/types.ts (inferred from usage)
interface AgentResult<T> {
    data: T;                          // The typed agent payload
    tokenUsage: {
        inputTokens: number;
        outputTokens: number;
        thinkingTokens: number;
    };
    durationMs: number;
    agentName: string;
    modelId: string;
    costUsd: number;
}
```

This is the **single most important type** in the pipeline. Everything flows as `AgentResult<SomeSpecificResult>`.

---

### 3.2 `research-agent.ts` — Detailed Type Map

#### Internal helper functions

| Function | Params | Returns | Pure? |
|---|---|---|---|
| `querySingleKb(query)` | `string` | `Promise<string[]>` | No — calls AWS SDK |
| `deduplicatePassages(passages)` | `string[]` | `string` | Yes |
| `resolveWikiMcpAuth()` | _(none)_ | `Promise<string>` | No — SSM + module cache |
| `getWikiMcpConstraints()` | _(none)_ | `Promise<string>` | No — HTTP fetch |
| `buildResearchMessage(jd, kb, resume)` | `string, string, StructuredResumeData \| null` | `string` | Yes |

#### Exported function

```
executeResearchAgent(ctx: StrategistPipelineContext)
  → Promise<AgentResult<StrategistResearchResult>>
```

**Input — `StrategistPipelineContext`:**
```typescript
{
    pipelineId: string;          // Correlation ID
    operation: 'analyse' | 'coach';
    applicationSlug: string;     // e.g. "acme-senior-devops-2026-03"
    jobDescription: string;      // Raw JD text (sanitised inside agent)
    targetCompany: string;
    targetRole: string;
    resumeId: string;
    resumeData: StructuredResumeData | null;
    interviewStage: InterviewStage;   // union of 11 literal strings
    bucket: string;
    environment: string;
    cumulativeTokens: { input: number; output: number; thinking: number };
    cumulativeCostUsd: number;
    startedAt: string;           // ISO timestamp
    includeCoverLetter?: boolean;
}
```

**Output — `AgentResult<StrategistResearchResult>` where `data` is:**
```typescript
{
    targetRole: string;
    targetCompany: string;
    seniority: string;
    domain: string;
    hardRequirements: JobRequirement[];     // { skill, context, disqualifying? }
    softRequirements: JobRequirement[];
    implicitRequirements: string[];
    technologyInventory: TechnologyInventory;   // { languages[], frameworks[], ... }
    experienceSignals: ExperienceSignals;       // { yearsExpected, domainExperience, ... }
    verifiedMatches: VerifiedMatch[];     // { skill, sourceCitation, depth, recency }
    partialMatches: PartialMatch[];       // { skill, gapDescription, framingSuggestion, ... }
    gaps: SkillGap[];                     // { skill, gapType, impactSeverity, ... }
    overallFitRating: FitRating;          // 'STRONG FIT' | 'REASONABLE FIT' | 'STRETCH' | 'REACH'
    fitSummary: string;
    resumeData: StructuredResumeData | null;   // Passed through
    kbContext: string;                    // Raw KB passages for downstream use
    resumeConstraints: string;            // wiki-mcp or Pinecone constraint text
}
```

---

### 3.3 `research-handler.ts` — Type Map

The thinnest file. Its only job is to be the Lambda entrypoint.

```
handler(event: StrategistResearchHandlerInput)
  → Promise<StrategistWriterHandlerInput>
```

| Type | Structure |
|---|---|
| **Input** `StrategistResearchHandlerInput` | `{ context: StrategistPipelineContext }` |
| **Output** `StrategistWriterHandlerInput` | `{ context: StrategistPipelineContext, research: AgentResult<StrategistResearchResult> }` |

> [!NOTE]
> No transformation of the context — it passes through unchanged. This is the right design — the handler is purely an orchestration glue layer.

---

### 3.4 `strategist-handler.ts` — Type Map

```
handler(event: StrategistWriterHandlerInput)
  → Promise<StrategistAnalysisPersistInput>
```

| Type | Structure |
|---|---|
| **Input** `StrategistWriterHandlerInput` | `{ context, research: AgentResult<StrategistResearchResult> }` |
| **Output** `StrategistAnalysisPersistInput` | `{ context (trimmed), research (trimmed), analysis: AgentResult<StrategistAnalysisResult> }` |

**Key transformation — payload trimming:**

The handler produces a deliberately **mutated spread** object — not the same type as the input or the raw agent output:

```typescript
const trimmedContext = { ...event.context, jobDescription: '[trimmed]' };
const trimmedResearch = {
    ...event.research,
    data: {
        ...event.research.data,
        kbContext: '[trimmed]',
        resumeConstraints: '[trimmed]',
        verifiedMatches: [],
        partialMatches: [],
        gaps: [],
        resumeData: null,
    },
};
const trimmedAnalysis = {
    ...analysis,
    data: { ...analysis.data, analysisXml: `s3://${ASSETS_BUCKET}/${xmlS3Key}` },
};
```

> [!WARNING]
> **Type safety gap:** `trimmedResearch.data` is structurally compatible with `AgentResult<StrategistResearchResult>` at the TypeScript level (it satisfies the shape), but it overwrites `analysisXml` with an S3 reference string where the type expects the XML content string. Downstream code (Analysis Persist Handler) must know to treat `analysisXml` as an S3 key, not content. This implicit "the string is a pointer, not the data" contract is not captured in the type system.
>
> **Recommendation:** Introduce a discriminated union or a dedicated `StrategistAnalysisPersistInput` type where `analysisXml` is typed as `{ s3Key: string } | string` — making the pointer-vs-content contract explicit.

**`analysis.data` shape — `StrategistAnalysisResult`:**
```typescript
{
    analysisXml: string;          // After trimming: 's3://bucket/key' (pointer, not XML!)
    metadata: {
        candidateName: string;
        targetRole: string;
        targetCompany: string;
        analysisDate: string;
        overallFitRating: FitRating;
        applicationRecommendation: ApplicationRecommendation;
    };
    coverLetter: string | null;
    resumeSuggestions: ResumeSuggestions;  // { additions[], reframes[], eslCorrections[] }
    resumeAdditions: number;     // @deprecated
    resumeReframes: number;      // @deprecated
    eslCorrections: number;      // @deprecated
}
```

---

### 3.5 `resume-builder-handler.ts` — Type Map

```
handler(event: ResumeBuilderHandlerInput)
  → Promise<ResumeBuilderHandlerOutput>
```

| Type | Structure |
|---|---|
| **Input** `ResumeBuilderHandlerInput` | `{ context, research: AgentResult<StrategistResearchResult>, analysis: AgentResult<StrategistAnalysisResult> }` |
| **Output** `ResumeBuilderHandlerOutput` | `{ context (resumeData nulled), research, analysis, tailoredResume: AgentResult<TailoredResumeResult> \| null }` |

**Two early-return paths** (both return `tailoredResume: null`):
1. `!context.resumeData` — no resume data available → skip
2. `totalSuggestions === 0` — no suggestions → skip

**`TailoredResumeResult` shape:**
```typescript
{
    tailoredResume: StructuredResumeData;   // Full rebuilt resume (same shape as input)
    changesSummary: string;
    additionsApplied: number;
    reframesApplied: number;
    eslCorrectionsApplied: number;
}
```

> [!NOTE]
> The `trimmedContext` pattern here (setting `resumeData: null`) mirrors `strategist-handler.ts`. This is consistent payload-trimming discipline. However, the return type `ResumeBuilderHandlerOutput` declares `context: StrategistPipelineContext` which has `resumeData: StructuredResumeData | null` — so nulling it out is type-safe.

---

### 3.6 `coach-loader-handler.ts` — Type Map

```
handler(event: StrategistCoachLoaderInput)
  → Promise<StrategistCoachHandlerInput>
```

| Type | Structure |
|---|---|
| **Input** `StrategistCoachLoaderInput` | `{ context: StrategistPipelineContext }` |
| **Output** `StrategistCoachHandlerInput` | `{ context, analysis: AgentResult<StrategistAnalysisResult> }` |

**Key operation:** Reconstructs `AgentResult<StrategistAnalysisResult>` from a DynamoDB record. The Zod schema validates the raw DDB item before the `as` cast is replaced by structured access.

Reconstructed `AgentResult`:
```typescript
{
    data: {
        analysisXml: record.analysisXml,
        metadata: record.metadata,
        coverLetter: record.coverLetter,
        resumeSuggestions: record.resumeSuggestions,
        resumeAdditions: record.resumeAdditions,
        resumeReframes: record.resumeReframes,
        eslCorrections: record.eslCorrections,
    },
    tokenUsage: { inputTokens: 0, outputTokens: 0, thinkingTokens: 0 },
    durationMs: 0,
    agentName: 'strategist-writer',
    modelId: 'loaded-from-ddb',
    costUsd: 0,
}
```

> [!IMPORTANT]
> The sentinel values `{ inputTokens: 0, outputTokens: 0 }`, `durationMs: 0`, `costUsd: 0` are correct since this is a `loaded-from-ddb` reconstruction. But `agentName: 'strategist-writer'` is a **misleading hardcode** — the record was originally produced by the strategist agent, but any code inspecting `agentName` downstream gets 'strategist-writer' regardless. Consider using a const or an enum value here.

---

### 3.7 `coach-handler.ts` — Type Map

```
handler(event: StrategistCoachHandlerInput)
  → Promise<StrategistCoachPipelineOutput>
```

| Type | Structure |
|---|---|
| **Input** `StrategistCoachHandlerInput` | `{ context: StrategistPipelineContext, analysis: AgentResult<StrategistAnalysisResult> }` |
| **Output** `StrategistCoachPipelineOutput` | `{ context, coaching: AgentResult<InterviewCoachResult>, applicationStatus: ApplicationStatus }` |

**`InterviewCoachResult` shape:**
```typescript
{
    stage: InterviewStage;
    stageDescription: string;
    technicalQuestions: InterviewQuestion[];    // { question, answerFramework, sourceProject, difficulty, keyPoints[] }
    behaviouralQuestions: InterviewQuestion[];
    difficultQuestions: DifficultQuestion[];    // { question, answerFramework, bridgeStrategy }
    technicalPrepChecklist: TechnicalPrepItem[];  // { topic, priority, rationale, suggestedResources[] }
    questionsToAsk: QuestionToAsk[];            // { question, rationale }
    coachingNotes: string;
}
```

---

## 4. Pipeline Data Flow Diagram

```
Step Functions State Machine — Analysis Pipeline
────────────────────────────────────────────────

[Trigger Lambda]
  Input:  { jobDescription, resumeId, applicationSlug, ... }
  Action: Fetches StructuredResumeData from DDB → builds StrategistPipelineContext
  Output: StrategistResearchHandlerInput = { context }
      │
      ▼
[research-handler] calls executeResearchAgent(context)
  Input:  StrategistResearchHandlerInput = { context }
  Output: StrategistWriterHandlerInput   = { context, research: AgentResult<StrategistResearchResult> }
      │
      ▼
[strategist-handler] calls executeStrategistAgent(context, research.data)
  Input:  StrategistWriterHandlerInput
  Output: StrategistAnalysisPersistInput = { context(trimmed), research(trimmed), analysis(xml→S3) }
      │
      ▼
[resume-builder-handler] calls executeResumeBuilderAgent(...)
  Input:  ResumeBuilderHandlerInput = { context, research, analysis }
  Output: ResumeBuilderHandlerOutput = { context(resumeData=null), research, analysis, tailoredResume|null }
      │
      ▼
[analysis-persist-handler] (not reviewed — final DDB write stage)

Step Functions State Machine — Coaching Pipeline
─────────────────────────────────────────────────

[coach-loader-handler]
  Input:  StrategistCoachLoaderInput = { context }
  Loads:  ANALYSIS# record from DynamoDB
  Output: StrategistCoachHandlerInput = { context, analysis: AgentResult<StrategistAnalysisResult> }
      │
      ▼
[coach-handler] calls executeCoachAgent(context, analysis.data)
  Input:  StrategistCoachHandlerInput
  Writes: METADATA update + INTERVIEW#<stage> record to DynamoDB
  Output: StrategistCoachPipelineOutput = { context, coaching, applicationStatus: 'interviewing' }
```

---

## 5. Specific Issues & Recommendations

### 5.1 ❌ Deprecated Fields Kept in `StrategistAnalysisResult`

```typescript
/** @deprecated Use `resumeSuggestions.additions.length` */
readonly resumeAdditions: number;
readonly resumeReframes: number;
readonly eslCorrections: number;
```

These are stored in DynamoDB and carried through the pipeline. As long as consumers exist, this is technically fine — but the `@deprecated` tag has no enforcement. Consider adding a lint rule (`no-restricted-syntax`) or removing them in a v2 schema migration.

---

### 5.2 ⚠️ `agentName: 'strategist-writer'` Hardcode in `coach-loader-handler.ts`

```typescript
agentName: 'strategist-writer',  // Line 119
modelId: 'loaded-from-ddb',
```

`agentName` should reflect the agent that produced the analysis, but it is hardcoded. Storing the `agentName` in the DynamoDB record when the analysis is written would allow the loader to read it back accurately.

---

### 5.3 ⚠️ `trimmedResearch.data.analysisXml` — Implicit Pointer Type

Already noted in section 3.4. The string `'s3://bucket/key'` is semantically different from the XML content it replaces, but both have type `string`. This is the most significant hidden type contract in the codebase. Should be:

```typescript
// Option A — discriminated union in StrategistAnalysisResult
analysisXml: string | { s3Ref: string };

// Option B — separate type for trimmed/offloaded state
interface StrategistAnalysisPersistInput {
    analysis: AgentResult<StrategistAnalysisResultOffloaded>;
}
interface StrategistAnalysisResultOffloaded extends Omit<StrategistAnalysisResult, 'analysisXml'> {
    analysisXml: string;  // Always an S3 reference in this type
    analysisXmlS3Key: string;  // Explicit key field
}
```

---

### 5.4 ✅ Arrow Function Consistency

All handlers correctly use:
```typescript
export const handler = async (event: T): Promise<U> => { ... };
```

This is the AWS Lambda canonical pattern and allows cold-start environment validation to run before the handler is registered (the `const env = Schema.parse(process.env)` lines at module level execute at cold start, which is the intended behaviour).

---

### 5.5 ✅ Zod env validation at module level — correct pattern

```typescript
// coach-handler.ts, resume-builder-handler.ts, strategist-handler.ts
const env = AgentHandlerEnvSchema.parse(process.env);
```

Module-level Zod parse = fail-fast at Lambda cold start. If env vars are missing, the function throws before any invocation reaches the handler. This is the correct Lambda pattern.

---

### 5.6 ✅ `StructuredResumeData` is correctly `readonly` throughout

All resume sub-interfaces (`ResumeProfile`, `ResumeExperience`, etc.) use `readonly` on every field. This prevents accidental mutation of the resume object as it flows through the pipeline.

---

### 5.7 ⚠️ Missing `@throws` JSDoc on handlers

`coach-loader-handler.ts` documents its throw in the JSDoc (`@throws Error if no analysis exists`) — this is the only handler that does. The other four handlers also throw (on missing `pipelineId`), but the `@throws` tag is absent. Since these are AWS Lambda handlers (not library functions), this is low priority but inconsistent.

---

## 6. Summary Scorecard

| Concern | Rating | Notes |
|---|---|---|
| Class vs. function decision | ✅ Correct | Pure functions everywhere — no shared mutable state (except intended Lambda warm-start cache) |
| Arrow function pattern | ✅ Standard | Handlers = `const arrow`, agents = `function` declaration — consistent split |
| Type safety | ✅ Strong | `AgentResult<T>` generic is well used; no `any`; Zod on env + DDB records |
| TSDoc / JSDoc | ✅ Good | Comprehensive on all public functions and shared types |
| Payload trimming | ✅ Intentional | Well-commented; S3 offload for 256KB limit is sound |
| Hidden type contracts | ⚠️ Gap | `analysisXml` as S3 pointer is not type-safe |
| Deprecated field cleanup | ⚠️ Open | 3 `@deprecated` fields still flowing through pipeline |
| `agentName` sentinel | ⚠️ Minor | `'strategist-writer'` hardcode in coach-loader is inaccurate |
| State isolation | ✅ Correct | Module-level cache is intentional Lambda warm-start pattern, not accidental state |
