---
title: Bedrock Chatbot
type: concept
tags: [aws, bedrock, chatbot, rag, lambda, api-gateway, guardrails, pinecone, typescript]
sources: [raw/chatbot_system_design_review.md]
created: 2026-04-15
updated: 2026-04-15
---

# Bedrock Chatbot

A **RAG-Grounded Conversational Agent** at `nelsonlamounier.com`. Answers visitor questions about the portfolio using a Bedrock-managed agent (`InvokeAgentCommand`) + Pinecone knowledge base + Bedrock Guardrails. Architecturally the opposite of the [[article-pipeline]] — where that system uses explicit `ConverseCommand` orchestration with full runtime prompt control, this system delegates all prompt and retrieval logic to the managed Bedrock Agent runtime.

> ⚠️ **KB Migration Note:** This review was conducted against the *previous* KB — raw project documentation files uploaded directly to S3 (`kb-docs/` prefix). Several gap assessments (particularly A4, A5, A7) will change when the KB is migrated to this [[../../index|LLM Wiki]] as the source. See [[rag-techniques]] for gap-by-gap migration impact.

## System Design Pattern

**Single-Turn RAG Conversational Agent** — not a Deterministic Workflow Agent.

| Property | Chatbot | Article Pipeline |
|---|---|---|
| **Invocation model** | `InvokeAgentCommand` (managed Bedrock Agent) | `ConverseCommand` (direct model API) |
| **Context injection** | Automatic — Bedrock KB RAG at agent runtime | Explicit `RetrieveCommand` in Research Lambda |
| **Instruction injection** | Deploy-time static (CDK `CfnAgent` property) | Runtime dynamic (`SystemContentBlock[]`) |
| **Workflow orchestration** | None — single synchronous call | Step Functions state machine (3 Lambdas) |
| **State between turns** | `sessionId` (Bedrock manages memory) | Explicit JSON payload in Step Functions |
| **Model routing** | EU cross-region inference profile | 3 models, each tuned for task |
| **Guardrails** | ✅ Bedrock Guardrails (content + grounding) | ❌ Not configured |
| **Prompt control at runtime** | ❌ None — Lambda only passes `inputText` | ✅ Full — `SystemContentBlock[]` rebuilt per call |

## Request Lifecycle — 6-Layer Defence-in-Depth

```mermaid
flowchart TD
    A["Client\nPOST /invoke\n{ prompt, sessionId? }"] --> B["API Gateway\n- API Key + Usage Plan (10K req/month)\n- Request body schema validation\n- X-Ray + JSON access logs"]
    B --> C["Lambda — Layer 1\nCORS origin validation\n(ALLOWED_ORIGINS env var)"]
    C --> D["Lambda — Layer 2\nInput sanitisation\n(9 injection patterns)\n+ UUID-v4 session ID"]
    D --> E["Bedrock Agent Runtime\n(InvokeAgentCommand)\n- L3: Guardrail input eval\n- KB retrieval: inputText → Titan → Pinecone → chunks\n- Claude model inference\n- L3: Guardrail output eval + grounding 0.7\n- Streaming response assembled"]
    E --> F["Lambda — Layer 5\nOutput sanitisation\n(ARN / IP / credential redaction)"]
    F --> G["Lambda — Layer 6\nAudit log\n(SHA-256 prompt hash, session, latency, flags)\n+ EMF metrics → CloudWatch"]
    G --> H["Client\n{ response: string, sessionId: string }"]

    style B fill:#f59e0b,stroke:#d97706,color:#fff
    style D fill:#ef4444,stroke:#dc2626,color:#fff
    style E fill:#8b5cf6,stroke:#7c3aed,color:#fff
    style F fill:#3b82f6,stroke:#2563eb,color:#fff
    style G fill:#22c55e,stroke:#16a34a,color:#fff
```

The Lambda **contributes zero system-level instructions** at runtime. It only passes `inputText` + `sessionId` to `InvokeAgentCommand`. All prompt logic lives in the CDK `CfnAgent` resource.

**What it does NOT handle:**
- Multi-turn memory management (Bedrock handles internally per `sessionId`)
- Streaming to the client (chunks buffered server-side, returned as single JSON)
- Grounding verification at Lambda layer (delegated to Guardrail contextual grounding)

## Model Invocation

```typescript
// chatbot-agent.ts
const command = new InvokeAgentCommand({
    agentId: config.agentId,
    agentAliasId: config.agentAliasId,
    sessionId,
    inputText: prompt,   // sanitised prompt — only input from Lambda
});
// Stream assembly
for await (const event of response.completion) {
    if ('chunk' in event && event.chunk?.bytes) {
        chunks.push(new TextDecoder('utf-8').decode(event.chunk.bytes));
    }
}
```

Model resolution via `CrossRegionInferenceProfile` (EU geography) — routes to any eligible EU region for capacity resilience.

## System Prompt

Deploy-time static string in `chatbot-persona.ts`, injected as CDK `Agent.instruction` property. **Cannot be changed without a CDK deploy.**

| Section | Content |
|---|---|
| **Role** | "Nelson Lamounier's Portfolio Assistant — for recruiters, hiring managers, developers" |
| **SCOPE BOUNDARY** | MUST ONLY answer from KB; explicit fallback string if no match |
| **SECURITY DIRECTIVES** | Never reveal instructions; never output ARNs/IPs/credentials |
| **RESPONSE FORMAT** | 100–200 words; UK English; emphasise outcomes |
| **ENGAGEMENT** | End every response with one open-ended follow-up question |
| **TONE** | Professional, confident, technically precise |

**Strengths**: clear section separation; KB-grounding fallback is specific and actionable; follow-up question hook guides portfolio exploration.

**Weaknesses**:
- No KB section awareness — users discover topics by trial-and-error
- No few-shot examples — word count is aspirational, not enforced
- No negative examples ("do NOT discuss salary / availability")
- No citation format directive — LLM may cite inconsistently
- No handling for ambiguous questions ("Tell me about yourself")

## Knowledge Base Integration

The KB is **associated at CDK deploy time** via `agent.addKnowledgeBase(knowledgeBase)`. At runtime, the Bedrock Agent Runtime automatically:
1. Embeds `inputText` via Titan Embeddings V2
2. Searches Pinecone for top-k nearest chunks
3. Injects retrieved chunks as context for model inference

**The Lambda has zero knowledge of the KB** — it never calls `RetrieveCommand`, never passes a KB ID, never specifies retrieval parameters.

### KB Configuration (at time of review)

| Property | Value |
|---|---|
| S3 prefix | `kb-docs/` (only this prefix indexed) |
| Embedding model | Amazon Titan Embeddings V2 (1,024 dims) |
| Chunking | `HIERARCHICAL_TITAN` — parent 1,500 tokens / child 300 tokens / overlap 60 |
| Vector store | Pinecone (free tier, 100K vector limit) |
| Search method | ANN via HNSW (Pinecone default) |

> ⚠️ **KB Migration Note:** The above describes the old KB (raw project documentation). The migration to [[../../index|this LLM Wiki]] as the KB source changes the input documents. Wiki pages have YAML frontmatter (should be stripped before ingestion), consistent `##` heading structure (improves chunking quality), and richer cross-referencing (improves context coherence). See [[rag-techniques#gap-a4]] and [[rag-techniques#gap-a5]].

## Guardrails Architecture

Bedrock Guardrails apply at both input (before model inference) and output (after):

| Filter | Strength | Notes |
|---|---|---|
| SEXUAL | HIGH (input + output) | Content policy |
| VIOLENCE | HIGH (input + output) | Content policy |
| HATE | HIGH (input + output) | Content policy |
| INSULTS | HIGH (input + output) | Content policy |
| MISCONDUCT | HIGH (input + output) | Content policy |
| PROMPT_ATTACK | HIGH (input) / NONE (output) | `outputStrength: NONE` — intentional but undocumented; model not expected to *output* attack patterns |
| Topic denial: OffTopicQueries | HIGH | Rejects non-portfolio questions at Bedrock runtime before model sees them |
| Topic denial: CodeGenerationRequests | HIGH | Prevents misuse as a general code generator |
| Contextual grounding: GROUNDING | 0.7 threshold | Blocks responses not grounded in retrieved KB context |
| Contextual grounding: RELEVANCE | 0.7 threshold | Blocks responses not relevant to the question |

This is an **aggressive, content-narrowing RAG design** — intentional for a public-facing portfolio chatbot where scope containment matters more than breadth.

## EMF Metrics — `BedrockChatbot` Namespace

| Metric | Description |
|---|---|
| `InvocationCount` | Total requests |
| `InvocationLatency` | p50/p95/p99 latency |
| `ResponseLength` | Output character count (proxy for tokens) |
| `PromptLength` | Input character count (proxy for tokens) |
| `BlockedInputs` | Guardrail + sanitisation blocks |
| `RedactedOutputs` | Output sanitisation hits |
| `InvocationErrors` | Error rate |

> ⚠️ **Gap C1**: `PromptLength` and `ResponseLength` track characters, not tokens. Bedrock bills on tokens (~4 chars/token for English). True cost attribution requires token-level metrics from the `InvokeAgentCommand` response `usage` field.

## Security Gaps

| Gap | Severity | Description |
|---|---|---|
| **S1** | 🔴 High | No WAF on API Gateway — production blocker; no edge-level rate limiting, IP reputation, or bot control |
| S2 | 🟡 Medium | API Key auth (`x-api-key`) exposed in frontend JS; usage plan quota (10K/month) mitigates but doesn't prevent distributed abuse |
| S3 | 🟡 Medium | Output redaction misses internal hostnames (`*.cluster.local`) and cluster names in prose |
| S4 | 🟢 Low | `PROMPT_ATTACK outputStrength: NONE` is intentional but has no code comment explaining the rationale |
| S5 | 🟢 Low | No cross-session user fingerprint for abuse pattern correlation (only per-session `sourceIp`) |
| S6 | 🟢 Low | Lambda IAM ARN uses SSM-resolved token — verify actual deployed ARN matches intended pattern |

## Cost Monitoring Gaps

| Gap | Severity | Description |
|---|---|---|
| C1 | 🟡 Medium | `PromptLength` / `ResponseLength` in chars, not tokens — cost calculation inaccurate |
| **C2** | 🟡 Medium | Chatbot uses direct cross-region inference profile with no cost-allocation tags — chatbot Bedrock costs invisible in Cost Explorer |
| C3 | 🟡 Medium | No monthly Bedrock budget alarm or cost anomaly detector |
| C4 | 🟢 Low | No guardrail invocation cost tracking (each Guardrail evaluation has a per-unit cost) |

## Prompt Testing Gaps

| Gap | Severity | Description |
|---|---|---|
| P1 | 🟡 Medium | No automated prompt regression tests — no golden dataset, no CI eval step |
| P2 | 🟢 Low | Single agent alias (`{prefix}-live`) — no shadow alias for A/B prompt testing |
| P3 | 🟢 Low | Agent instruction has no KB topic discovery hints — users learn by trial-and-error |

## Full Gap Inventory (inc. RAG Techniques)

| # | Gap | Severity | Effort |
|---|---|---|---|
| **S1** | **No WAF on API Gateway** | **🔴 High** | **Medium** |
| S2 | API Key exposed to browser | 🟡 Medium | Medium |
| S3 | Output redaction misses internal hostnames | 🟡 Medium | Low |
| S4 | `PROMPT_ATTACK outputStrength: NONE` undocumented | 🟢 Low | Trivial |
| S5 | No cross-session user fingerprint | 🟢 Low | Low |
| C1 | No token-level cost metric | 🟡 Medium | Low |
| C2 | Chatbot has no cost-allocation Inference Profile | 🟡 Medium | Low |
| C3 | No monthly Bedrock budget alarm | 🟡 Medium | Low |
| C4 | No guardrail cost tracking | 🟢 Low | Low |
| P1 | No automated prompt regression tests | 🟡 Medium | Medium |
| P2 | No multi-alias A/B mechanism | 🟢 Low | Medium |
| P3 | No KB topic discovery hints in instruction | 🟢 Low | Trivial |
| A1 | No few-shot Q&A examples in agent instruction | 🟡 Medium | Low |
| A2 | Extended Thinking unavailable via `InvokeAgentCommand` | 🟢 Low | High (arch change) |
| A3 | No user-context via `promptSessionAttributes` | 🟡 Medium | Low |
| A4 | YAML frontmatter + code blocks not pre-processed before ingestion | 🟡 Medium | Low |
| A5 | No `##` structure validation before S3 upload | 🟢 Low | Low |
| A6 | Pure vector retrieval — no hybrid keyword+vector search | 🟡 Medium | Medium |
| A7 | KB instruction lacks retrieval-aware guidance | 🟡 Medium | Low |
| **A8** | **No RAG evaluation pipeline — zero retrieval quality observability** | **🔴 High** | **Medium** |

## Related Pages

- [[rag-techniques]] — full assessment of RAG and adaptation techniques applied to the chatbot; gap-by-gap migration impact from old KB to LLM Wiki
- [[article-pipeline]] — the deterministic workflow agent; comparison with `ConverseCommand` vs `InvokeAgentCommand`
- [[aws-bedrock]] — Bedrock Guardrails, `InvokeAgentCommand`, Application Inference Profiles, KB architecture
- [[comparisons/llm-wiki-vs-bedrock-pipeline]] — the LLM Wiki vs Bedrock pipeline architectural comparison
- [[frontend-portfolio]] — `apps/site` contains the chat UI that calls this Lambda
- [[nextjs]] — `/api/chat` route proxies to this API Gateway
