---
title: RAG Techniques
type: concept
tags: [ai, rag, retrieval, bedrock, pinecone, embeddings, chunking, evaluation]
sources: [raw/chatbot_system_design_review.md]
created: 2026-04-15
updated: 2026-04-15
---

# RAG Techniques

Assessment of Retrieval-Augmented Generation (RAG) and adaptation techniques applied to the [[chatbot]] — a public-facing portfolio Q&A agent. Covers document parsing, indexing, retrieval, generation, and evaluation dimensions.

> ⚠️ **KB Migration Note:** This assessment was conducted against the *previous* KB — raw project documentation files uploaded directly to S3 (`kb-docs/` prefix, `##` heading convention). The gaps below are annotated where their severity changes after migration to [[../../index|this LLM Wiki]] as the KB source.

## Status Legend

| Symbol | Meaning |
|---|---|
| ✅ | Applied — demonstrably implemented |
| ⚠️ | Partial / Implicit — approximated but not fully formalised |
| ❌ | Absent but Relevant — would improve the system |
| 🚫 | Not Applicable — does not fit this use case or stack |

---

## Adaptation Techniques

### A. Fine-tuning

**Status: 🚫 Not applicable.**

Anthropic Claude models on Bedrock cannot be fine-tuned by customers. RAG + prompt engineering is the correct approach for a frequently-updated documentation corpus — fine-tuning would need to be re-run on every KB update. **No gap.**

### B. PEFT / LoRA

**Status: 🚫 Not applicable.** Same constraint as A. **No gap.**

### C. Zero-shot and Few-shot Prompting

**Status: ⚠️ Partial — zero-shot applied, few-shot absent.**

The agent instruction (`chatbot-persona.ts`) defines role, scope boundary, security directives, format, and tone — but provides no worked examples. The 100–200 word response format is aspirational rather than enforced.

**Gap A1** — Add 2–3 few-shot Q&A examples to the agent instruction:
1. A recruiter question (skills overview, ~150 words, ends with follow-up)
2. A technical question requiring KB grounding (cites specific component)
3. A scope boundary rejection (demonstrates the fallback string)

> **Migration impact**: No change — few-shot examples live in the agent instruction (CDK), not in KB content.

### D. Chain-of-Thought (CoT) Prompting

**Status: ❌ Absent — architectural constraint, not a configuration gap.**

`InvokeAgentCommand` does not support `additionalModelRequestFields.thinking` — Extended Thinking is only available via `ConverseCommand`. The managed Bedrock Agent runtime does not expose this.

**Gap A2** — If CoT reasoning is desired, the architecture must shift from `InvokeAgentCommand` to `ConverseCommand` + explicit `RetrieveCommand` (as the [[article-pipeline]] does). This is a significant architectural trade-off: gaining Extended Thinking means losing Bedrock Guardrails, managed session memory, and automatic RAG.

**Functional substitute**: The Guardrail contextual grounding filter (GROUNDING at 0.7) enforces faithfulness-to-KB at inference time. This is a managed substitute for CoT-driven faithfulness. **For the current use case, this is acceptable — no immediate gap.**

> **Migration impact**: No change — this is an API-level constraint independent of KB content.

### E. Role-specific and User-context Prompting

**Status: ✅ Role-specific applied / ❌ User-context absent.**

Role specification is well-implemented in the agent instruction (professional tone, technical audience, follow-up engagement pattern).

**Gap A3** — No user-context injection at invocation time. `InvokeAgentCommand` supports `promptSessionAttributes` that are available per turn:

```typescript
const command = new InvokeAgentCommand({
    agentId, agentAliasId, sessionId, inputText: prompt,
    promptSessionAttributes: {
        callerRole: 'recruiter' | 'engineer' | 'unknown',
    },
});
```

The agent instruction could then adapt tone and technical depth by role. A lightweight classifier (e.g., check for technical terms in the question) could populate `callerRole` automatically.

> **Migration impact**: No change — `promptSessionAttributes` is a Lambda-level feature.

---

## RAG Pipeline Techniques

### F. Document Parsing Strategies

**Status: ⚠️ Partial — rule-based only; no AI-based parsing.**

Bedrock KB uses the `HIERARCHICAL_TITAN` preset, which splits on token count with `##` Markdown heading boundaries. This is **rule-based parsing** — it has no semantic understanding of tables, code blocks, or nested lists.

**Gap A4 — YAML frontmatter and code blocks not pre-processed.**

For the old KB (raw project docs), problems include:
- YAML frontmatter tokens pollute child chunks (embeddings penalised for irrelevant key-value pairs)
- Code blocks embedded in prose chunks are indexed as undifferentiated text — "What CDK code did you write?" may return chunks that are 90% prose

Recommended pre-processing pipeline before S3 upload:
1. Strip YAML frontmatter
2. Extract code blocks into separate semantic units with a language tag
3. Add section-level metadata (`category: IaC`, `technology: CDK`) for future filtered retrieval

> ✳️ **Migration impact — partially resolved by LLM Wiki format:**
> - Wiki pages have YAML frontmatter → still needs stripping before ingestion
> - Wiki pages are authored to `##` structure by convention → chunking quality improves
> - Wiki pages contain Mermaid diagrams in fenced code blocks → should be treated as "architectural diagrams", not code
> - Wikilinks (`[[page-name]]`) are low-information tokens → consider stripping `[[` / `]]` syntax before ingestion
> - Net result: A4 severity **reduces from Medium to Low** post-migration; frontmatter stripping becomes more important

**Gap A5 — No document structure validation before S3 upload.**

No enforcement that ingested documents use `##` headings. Flat documents degrade chunk coherence silently.

> ✳️ **Migration impact — mostly resolved:**
> Wiki CLAUDE.md schema enforces `##` heading conventions. However, a validation script that checks frontmatter presence and at least one `##` heading before S3 upload would still add value.

### G. Indexing Strategy

**Status: ✅ Vector-based / ❌ Hybrid absent.**

Pure **dense vector indexing** via Titan Embeddings V2 (1,024 dims) into Pinecone. Searches via approximate nearest neighbour (ANN/HNSW).

**Gap A6 — No hybrid retrieval (vector + keyword/BM25).**

For a technical portfolio KB, exact term matches matter critically:
- `"ConverseCommand"` — specific AWS SDK method name with no semantic neighbours
- `"HIERARCHICAL_TITAN"` — exact Bedrock constant
- CDK construct names, Helm chart names, Kubernetes resource types, error codes

Pure vector search can fail to retrieve chunks containing these rare exact terms if the embedding space has no nearby neighbours.

Hybrid search (dense + sparse/BM25 with reciprocal rank fusion) significantly improves recall for exact technical terms. Bedrock KB does not natively support hybrid retrieval in the HIERARCHICAL preset — this would require switching to explicit `RetrieveCommand` + Pinecone hybrid search API.

> ✳️ **Migration impact — gap intensifies post-migration:**
> The LLM Wiki is richer in technical terminology (CDK construct names, Kubernetes manifests, AWS API names). The exact-term retrieval failure mode becomes *more* likely with denser technical vocabulary. **A6 severity increases from Medium to High** post-migration.

### H. Search Methods

**Status: ✅ ANN via Pinecone HNSW — correct choice for this scale.**

100K-vector portfolio KB: ANN recall is effectively equivalent to exact at this corpus size. **No gap.**

### I. Prompt Engineering for RAG

**Status: ⚠️ Partial — two prompt surfaces; only one well-engineered.**

| Surface | Location | Quality |
|---|---|---|
| Agent instruction | `chatbot-persona.ts` | ✅ Well-structured (role, scope, security, format, tone) |
| KB instruction | `configurations.ts → kbInstruction` | ⚠️ Thin — no retrieval guidance |

**Gap A7 — KB instruction lacks retrieval-aware guidance.**

Current KB instruction: "Use this knowledge base to answer questions about the portfolio project. When citing information, reference specific components or files when relevant."

Missing:
- How to handle conflicting retrieved passages
- How to signal confidence when KB has only partial information
- Explicit citation format (document name + section heading)
- Behaviour when retrieved chunks are noisy or only partially relevant

Recommended additions:
```
If retrieved passages are partially relevant, answer from what IS directly supported
and state: "Based on the available documentation..." for unsupported parts.

When citing sources, reference the document name and section (e.g., "According to
the CDK Monitoring README, §Architecture...").

If multiple passages contradict each other, use the most recent source and note
the discrepancy briefly.
```

> ✳️ **Migration impact — gap shifts in nature post-migration:**
> The LLM Wiki pages have rich section headings and cross-references. Citation format becomes more navigable (e.g., "According to concepts/observability-stack, §Tempo section..."). The KB instruction should be updated to reference wiki page types and wikilink format for citations. **A7 severity unchanged — still Medium.**

### J. RAFT (Retrieval Augmented Fine-Tuning)

**Status: 🚫 Not applicable.** Training-time technique; Anthropic models not fine-tunable on Bedrock. The Guardrail contextual grounding filter (GROUNDING at 0.7) is the correct inference-time substitute. **No gap.**

---

## RAG Evaluation

### K. Context Relevance, Faithfulness, Answer Correctness

**Status: ❌ Absent — the most significant systematic gap.**

The three canonical RAG evaluation dimensions are not measured:

| Dimension | Definition | Current State |
|---|---|---|
| **Context relevance** | Are retrieved chunks relevant to the question? | ❌ Not measured at runtime or offline |
| **Faithfulness** | Is the answer grounded in retrieved context? | ⚠️ Proxy: Guardrail GROUNDING at 0.7 (blocking, not measuring) |
| **Answer correctness** | Is the answer factually correct vs. ground truth? | ❌ No golden dataset, no scoring |

The Guardrail grounding filter **blocks** unfaithful responses but does not **measure** retrieval quality. If Pinecone consistently returns low-relevance chunks for a query class, there is no observable signal.

**Gap A8 — No RAG evaluation pipeline** (HIGH severity):

```typescript
// Offline cadence: weekly or on KB update
// 1. Maintain golden Q&A dataset (20–50 representative questions)
// 2. Run InvokeAgent against each question (dev environment)
// 3. Capture: { question, retrievedChunks, generatedAnswer }
// 4. Score via Bedrock Evaluation Jobs:
//    - Context relevance: cosine similarity (question vs. retrieved chunk)
//    - Faithfulness: Claude-as-judge (does answer contradict retrieved context?)
//    - Answer correctness: ROUGE-L / BERTScore against golden answers
// 5. Alert if any dimension drops below threshold
```

This closes a critical feedback loop: there is currently **no way to detect whether chatbot quality has degraded after a KB update**.

> ✳️ **Migration impact — gap becomes critical post-migration:**
> Migrating from old KB (raw docs) to LLM Wiki (restructured, cross-referenced pages) is a significant corpus change. Without a RAG evaluation pipeline, there is no way to verify the migration improves answer quality rather than degrading it. **A8 severity remains High; urgency increases with migration.**

### L. HIERARCHICAL Chunking Design

**Status: ✅ Applied with correct rationale.**

`HIERARCHICAL_TITAN` preset aligns well with Markdown `##` heading structure: each section becomes a parent chunk (1,500 tokens for context), paragraphs become child chunks (300 tokens for precision). At retrieval time, Bedrock returns child chunks with parent context appended.

**Remaining risk**: No validation that ingested documents conform to `##` structure. See Gap A4/A5.

> ✳️ **Migration impact — improves post-migration:**
> LLM Wiki pages follow `##` heading conventions by schema enforcement. Chunking quality should improve materially. Parent chunks will map to wiki sections (e.g., "## Sync Waves") and child chunks to subsection paragraphs.

---

## Gap Summary with Migration Impact

| # | Gap | Severity (old KB) | Severity (post-migration) | Effort |
|---|---|---|---|---|
| A1 | No few-shot Q&A examples | 🟡 Medium | 🟡 No change | Low |
| A2 | Extended Thinking unavailable via `InvokeAgentCommand` | 🟢 Low | 🟢 No change | High (arch) |
| A3 | No user-context `promptSessionAttributes` | 🟡 Medium | 🟡 No change | Low |
| A4 | YAML frontmatter + code blocks not pre-processed | 🟡 Medium | 🟢 Reduces (wiki structure helps) | Low |
| A5 | No `##` structure validation before upload | 🟢 Low | 🟢 Mostly resolved by wiki schema | Low |
| A6 | No hybrid keyword+vector retrieval | 🟡 Medium | 🔴 **Increases** (richer tech vocabulary) | Medium |
| A7 | KB instruction lacks retrieval guidance | 🟡 Medium | 🟡 No change (needs updating for wiki format) | Low |
| **A8** | **No RAG evaluation pipeline** | **🔴 High** | **🔴 Becomes critical** (migration verification) | **Medium** |

---

## Related Pages

- [[chatbot]] — full chatbot architecture; security, cost, and prompt testing gaps
- [[article-pipeline]] — deterministic workflow agent; how it uses `RetrieveCommand` explicitly
- [[aws-bedrock]] — Bedrock KB, Guardrails, Titan Embeddings, Pinecone integration
- [[comparisons/llm-wiki-vs-bedrock-pipeline]] — architectural decision: LLM Wiki vs Bedrock pipeline as KB source
