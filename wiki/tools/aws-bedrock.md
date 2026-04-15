---
title: AWS Bedrock
type: tool
tags: [aws, bedrock, ai, llm, rag, lambda, anthropic, claude, pinecone, typescript]
sources: [raw/article_pipeline_design_review.md, raw/chatbot_system_design_review.md]
created: 2026-04-15
updated: 2026-04-15
---

# AWS Bedrock

AWS Bedrock is the managed AI service used for all LLM features in the portfolio project: the [[ai-engineering/article-pipeline|article pipeline]] (3-agent `ConverseCommand` workflow) and the chatbot (managed Bedrock Agent with `InvokeAgentCommand`). Key building blocks: `ConverseCommand`, Knowledge Base + Pinecone, Application Inference Profiles, Extended Thinking, and Prompt Caching.

## `ConverseCommand` vs `InvokeAgentCommand`

The most important architectural decision in Bedrock usage:

| Property | `ConverseCommand` | `InvokeAgentCommand` |
|---|---|---|
| **What it calls** | Model directly (no agent runtime) | Managed Bedrock Agent (with action groups, KB, guardrails) |
| **Orchestration** | None — you build the pipeline | Bedrock Agent Runtime handles multi-turn, tool calls, KB retrieval |
| **Context passing** | Explicit (`messages[]` array) | Session memory managed by Bedrock |
| **KB retrieval** | Manual — call `RetrieveCommand` separately | Automatic — agent decides when and what to retrieve |
| **Transparency** | Full — all inputs/outputs in Lambda code | Partial — agent's KB queries are a black box |
| **Prompt control** | Full — `SystemContentBlock[]` rebuilt per invocation | Limited — system prompt set at agent deploy time |
| **When to use** | Complex pipelines, deterministic workflows, multi-step processing | Conversational agents, RAG chatbots, tool-use scenarios |

The [[ai-engineering/article-pipeline|article pipeline]] uses `ConverseCommand` because it needs explicit control over what context flows to each stage. The chatbot uses `InvokeAgentCommand` because it needs managed session continuity and automatic RAG.

## Extended Thinking API

Claude Extended Thinking is accessed via `additionalModelRequestFields`:

```typescript
const command = new ConverseCommand({
    modelId: config.modelId,
    system: config.systemPrompt,          // SystemContentBlock[] with cachePoint
    messages: [{ role: 'user', content: [{ text: userMessage }] }],
    inferenceConfig: { maxTokens: config.maxTokens },
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

Key behaviours:
- Reasoning happens in a hidden `<thinking>` block — not part of visible output
- `budget_tokens` is the **maximum** thinking budget, not a guaranteed allocation
- Thinking tokens are billed at the same rate as output tokens
- EMF tracking separates `AgentThinkingTokens` from `AgentOutputTokens` for cost attribution

See [[ai-engineering/inference-time-techniques]] for how the article pipeline uses adaptive thinking budgets.

## Knowledge Base (`RetrieveCommand`)

### KB Stack Configuration (`kb-stack.ts`)

| Property | Value |
|---|---|
| S3 prefix | `kb-docs/` (only this prefix indexed) |
| Embedding model | Amazon Titan Embeddings V2 (1,024 dims) |
| Chunking | `HIERARCHICAL_TITAN` — parent 1,500 tokens / child 300 tokens / overlap 60 |
| Vector store | Pinecone (free tier, 100K vector limit) |
| Fields | `text` (content), `metadata` (source URI) |

### Explicit `RetrieveCommand` (Article Pipeline)

```typescript
const command = new RetrieveCommand({
    knowledgeBaseId: KNOWLEDGE_BASE_ID,
    retrievalQuery: { text: query.substring(0, 1000) },    // explicit cap
    retrievalConfiguration: {
        vectorSearchConfiguration: { numberOfResults: 10 }, // explicit top-k
    },
});
```

Passages come back as typed `KbPassage[]` with `score` and `sourceUri` — both visible in the Lambda code and passed forward in the Step Functions payload.

### KB Update Matrix

| Change | Code Change Needed? |
|---|---|
| Add/rename/edit docs in `kb-docs/` | ❌ No — S3 upload + data sync only |
| Change `numberOfResults` (top-k) | ✅ `research-agent.ts` constant |
| Change embedding model | ⚠️ CDK + Pinecone index rebuild (dimension change) |
| Change chunking strategy | ⚠️ CDK only + full re-index |
| Change `kb-docs/` prefix | ⚠️ CDK only (`inclusionPrefixes`) |

## Application Inference Profiles

Application Inference Profiles wrap foundation models with cost-allocation tags and cross-region capacity pooling.

```typescript
// data-stack.ts
new bedrock.CfnApplicationInferenceProfile(this, 'WriterProfile', {
    inferenceProfileName: 'writer-profile',
    modelSource: { copyFrom: `arn:aws:bedrock:eu-west-1::foundation-model/anthropic.claude-sonnet-4-6-*` },
    tags: [
        { key: 'component', value: 'article-pipeline' },
        { key: 'project',   value: 'bedrock' },
        { key: 'environment', value: props.environment },
        { key: 'owner',     value: 'nelson-l' },
    ],
});
```

**Benefits:**
- AWS Cost Explorer can filter by `component: article-pipeline` vs `component: chatbot`
- EU cross-region inference profiles (`eu.anthropic.*` ARNs) pool capacity across EU regions — single-region `ThrottlingException` falls back to another EU region automatically
- Profile ARN replaces the raw model ID in `ConverseCommand` calls

## Prompt Caching

Bedrock charges **10% of standard input token price** for cached input tokens. The article pipeline exploits this on all 3 system prompts.

### Cache Strategy

Place `cachePoint: 'default'` after the **largest, most stable block** of static content:

```typescript
// blog-persona.ts — SystemContentBlock[] structure
const systemPrompt: SystemContentBlock[] = [
    { text: PERSONA_CONTEXT },        // ~400 tokens
    { text: WRITING_VOICE },          // ~550 tokens
    { text: CONTENT_ARCHITECTURE },   // ~350 tokens
    { text: NEXTJS_MDX_SCHEMA },      // ~700 tokens
    { text: SEO_CONTENT_STRATEGY },   // ~450 tokens
    { text: OUTPUT_AND_GUIDELINES },  // ~1,200 tokens
    { cachePoint: 'default' },        // ← ~3,650 tokens cached above
    // dynamic user content is NOT cached — correct
];
```

**Rule**: Never cache dynamic user content (draft text, KB passages, retry warnings). Only cache stable persona/schema definitions.

**Savings**: ~3,285 cached tokens × 90% discount per Writer invocation. On Claude Sonnet ($3/MTok input): ~$0.01 saved per article on the Writer system prompt alone.

## `runAgent()` — Shared LLM Utility

All 3 Lambda functions call a shared `runAgent()` utility in `bedrock-applications/shared/src/index.ts`:

```typescript
interface AgentConfig {
    modelId: string;
    systemPrompt: SystemContentBlock[];
    maxTokens: number;
    thinkingBudget: number;
    agentName: string;    // for EMF dimension
}

async function runAgent<T>(opts: {
    config: AgentConfig;
    userMessage: string;
    parseResponse: (text: string) => T;
    context: PipelineContext;
}): Promise<T>
```

The utility handles:
- `ConverseCommand` construction (with or without thinking budget)
- Response parsing + retry on malformed JSON
- EMF metric emission per invocation (`AgentInputTokens`, `AgentOutputTokens`, `AgentThinkingTokens`, `AgentLatency`, `AgentCostUsd`)
- Cumulative cost tracking in `context.cumulativeCostUsd` (passed forward through Step Functions payload)

## EMF Metrics — `BedrockMultiAgent` Namespace

| Metric | Source | Dimensions |
|---|---|---|
| `AgentInvocationCount` | `runAgent()` | `AgentName`, `Environment` |
| `AgentInputTokens` | `runAgent()` | `AgentName`, `Environment` |
| `AgentOutputTokens` | `runAgent()` | `AgentName`, `Environment` |
| `AgentThinkingTokens` | `runAgent()` | `AgentName`, `Environment` |
| `AgentLatency` | `runAgent()` | `AgentName`, `Environment` |
| `AgentCostUsd` | `runAgent()` | `AgentName`, `Environment` |
| `PipelineCompleted` | `qa-handler.ts` | `Environment`, `Slug`, `Version` |
| `PipelineCostUsd` | `qa-handler.ts` | `Environment`, `Slug`, `Version` |
| `PipelineQaScore` | `qa-handler.ts` | `Environment`, `Slug`, `Version` |
| `PipelinePassed` | `qa-handler.ts` | `Environment`, `Slug`, `Version` |

## Bedrock Guardrails

Guardrails apply at both input and output layers, integrated into the managed Bedrock Agent runtime (`InvokeAgentCommand`). Not available via `ConverseCommand`.

### Content Filters

```typescript
// agent-stack.ts
guardrail.addContentFilter({
    type: bedrock.ContentFilterType.PROMPT_ATTACK,
    inputStrength: bedrock.ContentFilterStrength.HIGH,
    outputStrength: bedrock.ContentFilterStrength.NONE,  // intentional — model not expected to output attack patterns
});
```

Standard content filters (SEXUAL, VIOLENCE, HATE, INSULTS, MISCONDUCT) all set to HIGH strength at both input and output.

### Topic Denial

```typescript
guardrail.addDenialTopic({
    name: 'OffTopicQueries',
    definition: 'Questions unrelated to the portfolio...',
    examples: ['...'],
    action: DenialAction.BLOCK,
});
```

Topic denial fires at the Bedrock Agent Runtime layer — before the model even sees the query. This is distinct from the Lambda-layer input sanitisation (which runs first) and the prompt's SCOPE BOUNDARY directive (which guides the model).

### Contextual Grounding Filter

```typescript
guardrail.addGroundingFilter({
    type: bedrock.GroundingFilterType.GROUNDING,
    threshold: 0.7,
});
guardrail.addGroundingFilter({
    type: bedrock.GroundingFilterType.RELEVANCE,
    threshold: 0.7,
});
```

Blocks responses that are not grounded in retrieved KB context. Serves as a managed inference-time substitute for Chain-of-Thought faithfulness enforcement. See [[ai-engineering/rag-techniques]] for the faithfulness vs. measurement distinction.

## `InvokeAgentCommand` — Managed Agent Runtime

The managed Bedrock Agent runtime handles KB retrieval, session memory, and Guardrails automatically. The Lambda only passes `inputText` + `sessionId`.

```typescript
const command = new InvokeAgentCommand({
    agentId: config.agentId,
    agentAliasId: config.agentAliasId,
    sessionId,
    inputText: prompt,
    // Optional: inject per-turn caller context
    promptSessionAttributes: {
        callerRole: 'recruiter' | 'engineer' | 'unknown',
    },
});
```

**`promptSessionAttributes`** (Gap A3 in [[ai-engineering/chatbot]]) — per-turn attributes that the agent instruction can reference for dynamic tone/depth adjustment. Not currently used in the implementation.

**`sessionAttributes`** — persist across an entire session (multi-turn). Used for durable user context.

## Related Pages

- [[ai-engineering/article-pipeline]] — 3-agent pipeline using `ConverseCommand`
- [[ai-engineering/chatbot]] — RAG conversational agent using `InvokeAgentCommand` + Guardrails
- [[ai-engineering/inference-time-techniques]] — Extended Thinking, adaptive compute, CoT
- [[ai-engineering/rag-techniques]] — RAG evaluation, hybrid retrieval, document parsing gaps
- [[aws-step-functions]] — orchestrates the Research → Writer → QA state machine
- [[comparisons/llm-wiki-vs-bedrock-pipeline]] — this pipeline vs the LLM Wiki approach
