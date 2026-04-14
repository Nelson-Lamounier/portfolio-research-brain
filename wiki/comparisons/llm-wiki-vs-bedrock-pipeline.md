---
title: "LLM Wiki vs Bedrock Article Pipeline — System Design Review"
type: comparison
tags: [architecture, bedrock, knowledge-base, system-design, migration, vector-search, chatbot]
sources: [raw/step-function-runtime-logging.md]
created: 2026-04-14
updated: 2026-04-14
---

# LLM Wiki vs Bedrock Article Pipeline

Comparative review of two knowledge base architectures serving the same downstream uses (portfolio articles, chatbot Q&A, documentation). The LLM Wiki is a manually maintained, interlinked markdown wiki. The Bedrock pipeline is an automated, event-driven, serverless article generation system with vector-indexed flat documents.

## Systems Overview

### LLM Wiki (This Repository)

- **Maintenance model:** Human directs, LLM (Claude Code) executes — ingest, query, lint, generate
- **Knowledge representation:** Interlinked markdown with Obsidian wikilinks, organized by type (projects, concepts, tools, patterns, troubleshooting, commands, comparisons)
- **Storage:** Local filesystem (Obsidian vault), git-backed
- **Search:** `index.md` content catalog — LLM reads index first, then drills into relevant pages
- **Downstream delivery:** Manual "Generate" operation via conversation

### Bedrock Article Pipeline

- **Maintenance model:** CI-driven — `.kb-map.yml` drift detection, staleness audits, automated S3 sync
- **Knowledge representation:** Flat `.md` documents with `.metadata.json` sidecars, 33 docs across 8 domains
- **Storage:** S3 → Bedrock managed ingestion → Pinecone vector index
- **Search:** Semantic vector search via `RetrieveCommand` (10 passages, cosine similarity)
- **Downstream delivery:** 3-agent pipeline (Research → Writer → QA) via [[aws-step-functions]], chatbot via `InvokeAgentCommand`, admin dashboard, ISR revalidation

## Comparative Analysis

| Dimension | LLM Wiki | Bedrock Pipeline | Verdict |
|-----------|----------|------------------|---------|
| **Knowledge synthesis quality** | 1 source → 13 cross-referenced pages. Concepts, patterns, troubleshooting extracted and interlinked | Flat documents, no cross-document synthesis — retrieval reassembles fragments at query time | LLM Wiki |
| **Human navigability** | Obsidian graph view, wikilinks, browseable taxonomy | S3 prefixes + DynamoDB. Not designed for human browsing | LLM Wiki |
| **Search at scale** | `index.md` lookup — works at ~100s of pages, then breaks | Pinecone vector search — scales to thousands of documents | Bedrock |
| **Downstream integration** | None — Generate is manual, chatbot not connected | Full pipeline: article generation, chatbot, admin dashboard, ISR publish | Bedrock |
| **KB maintenance automation** | Manual — human tells Claude Code to ingest | CI-driven: `.kb-map.yml` drift detection, staleness audits, automated sync | Bedrock |
| **Quality control** | Manual lint operation, human reviews in Obsidian | Automated QA agent (5-dimension scoring), CI drift checks | Bedrock |
| **Cost of operation** | Claude Code session costs only. No infrastructure | Lambda + Step Functions + Bedrock invocations + Pinecone + S3 + DynamoDB | LLM Wiki |
| **Cross-referencing** | Aggressive wikilinks — every entity mention is a link. Connections are pre-built | No cross-document linking. Connections rediscovered via vector similarity each query | LLM Wiki |
| **Knowledge compounding** | Each ingest enriches existing pages. 10th source more valuable than 1st | Each document independent. 10th document doesn't improve the 1st | LLM Wiki |
| **Audit trail** | `log.md` + git history | DynamoDB VERSION# pattern, S3 version-scoped paths, EMF metrics | Bedrock |
| **Production readiness** | Local dev tool. No API, no auth, no multi-user | Full production stack: API Gateway, IAM, 6-layer security, CloudWatch, X-Ray | Bedrock |
| **Schema evolution** | Conversational — human and LLM co-evolve CLAUDE.md | Code changes to CDK constructs, Lambda handlers, metadata schemas | LLM Wiki |

## Core Insight: Complementary, Not Competing

The LLM Wiki produces the **best possible KB content** — synthesized, cross-referenced, factual. The Bedrock system is the **best possible delivery mechanism** — automated pipeline, vector search, chatbot, articles.

The current Bedrock KB ingests raw flat documents into Pinecone. The LLM Wiki produces synthesized, interlinked pages but has no downstream delivery pipeline. The wiki should be what gets vectorized.

## Why Wiki Pages as Vector Source is Superior

The current Bedrock KB vectors raw `knowledge-base/*.md` files. If wiki pages are vectorized instead:

| Benefit | Explanation |
|---------|-------------|
| **Better embeddings** | Wiki pages follow a consistent schema (frontmatter, wikilinks, factual style). Uniform formatting produces more comparable embeddings |
| **Implicit graph structure** | Wikilinks like `[[calico]]`, `[[aws-step-functions]]` are text in the markdown. The vector index inherits semantic connections because they're embedded in the page content |
| **Pre-synthesized chunks** | A wiki page about "Calico CNI" is a clean, focused chunk. A raw source doc mentions Calico in passing alongside 20 other topics |
| **One concept per page** | Wiki convention means each vectorized document has a single, clear semantic identity. Better retrieval precision |
| **Richer metadata** | Wiki frontmatter (`type`, `tags`, `sources`) maps directly to Bedrock metadata filtering, replacing `.metadata.json` sidecars natively |
| **Cross-project enrichment** | When a second project uses [[argocd]], the ArgoCD wiki page grows with cross-project context. The vector index gets richer without re-ingesting old sources |

### Example: Chatbot Query Comparison

Query: "How does the bootstrap pipeline handle disaster recovery?"

**Current (flat docs):** Bedrock retrieves chunks from `bootstrap-pipeline.md` mentioning DR. If the relevant detail is in `infrastructure-topology.md`, it may or may not be retrieved depending on embedding similarity.

**Proposed (wiki-backed):** The wiki page `self-hosted-kubernetes.md` explicitly documents DR restore as Step 2 with a wikilink to `[[k8s-bootstrap-pipeline]]`. The embeddings include the wikilink text, creating a semantic association. The chatbot retrieves focused DR content and associated project context together.

## Proposed Hybrid Architecture

```
Project Repositories
    │ Copy .md files
    ▼
This Repository (kowledge-base/)
    raw/                    wiki/
    (immutable sources)     (LLM-synthesized, interlinked)
    │                       │
    │  Ingest operation     │  CI: wiki/ → S3 sync
    └───────────────────────┘
                            ▼
                  S3 (kb-wiki-docs/ prefix)
                  .metadata.json auto-generated from YAML frontmatter
                            │
                            │  Bedrock managed ingestion
                            ▼
                  Pinecone Vector Index
                  (embeddings of synthesized wiki pages)
                    │                       │
                    │ RetrieveCommand        │ InvokeAgentCommand
                    ▼                       ▼
          Article Pipeline          Portfolio Chatbot
          Research → Writer → QA    6-layer security
          (Step Functions)          Grounded in wiki synthesis
                    │
                    ▼
          Admin Dashboard ──────▶ Public Portfolio Site
          (approve/reject)        ISR / CloudFront
```

## Migration Plan — Three Phases

### Phase 1: Wiki as KB Source (Low effort, immediate payoff)

- Add CI workflow (`sync-wiki-to-s3.yml`): `wiki/**/*.md` → S3 `kb-wiki-docs/` prefix
- Auto-generate `.metadata.json` sidecars from wiki YAML frontmatter during sync
- Repoint Bedrock Knowledge Base to the wiki S3 prefix
- Keep LLM Wiki maintenance via Claude Code (manual, as today)
- **Zero code changes** to article pipeline, chatbot, or admin dashboard — they call the same Bedrock APIs, the data source just improves

### Phase 2: Automate Wiki Maintenance with Bedrock (Medium effort, scalability)

- Build an "Ingest Agent" Lambda triggered when new files land in `raw/`
- Lambda invokes Bedrock (Sonnet) with CLAUDE.md as system prompt
- Agent reads raw source, reads existing wiki pages, generates/updates wiki pages
- Agent commits to git (preserves version history, enables PR review, keeps Obsidian viable)
- Add `.kb-map.yml`-style drift detection: code changes → trigger wiki review obligation
- Manual Claude Code sessions remain available for exploration, queries, lint

**Model selection for Ingest Agent:**

| Task | Model | Rationale |
|------|-------|-----------|
| Read source + generate wiki pages | Sonnet 4.6 | Strong synthesis, cross-referencing, wikilink awareness |
| Update index.md | Haiku 4.5 | Mechanical — append entries to a list |
| Scheduled lint (contradictions, orphans) | Sonnet 4.6 | Needs reasoning across multiple pages |

### Phase 3: Full Pipeline Integration (Higher effort, production-grade)

- Article pipeline "Generate" operation automated: select wiki pages → build draft → trigger pipeline
- Chatbot agent instructions updated to reference wiki page types (filter by `concept`, `troubleshooting`, `command`)
- Scheduled lint runs (Lambda on cron) — wiki self-heals
- EMF metrics for wiki operations: pages created/updated, ingest latency, staleness scores
- `.kb-map.yml` equivalent mapping `raw/` source paths to `wiki/` pages

## Long-Term Scalability

| Scale | LLM Wiki Alone | Proposed Hybrid | Bedrock-Only (No Wiki) |
|-------|----------------|-----------------|----------------------|
| **100 sources, ~300 wiki pages** | Works well. `index.md` sufficient | Works well. Vector search optional but available | Works, retrieval quality limited by raw doc quality |
| **500 sources, ~1,500 wiki pages** | `index.md` breaks. Need search tooling | Vector search handles natively. Wiki quality compounds | Flat docs at this scale have significant retrieval noise |
| **1,000+ sources** | Claude Code context window can't hold full index. Manual process doesn't scale | Automated Ingest Agent + vector search. Human shifts to curation | Scales mechanically but quality plateaus — no synthesis layer |
| **Multiple contributors** | Single-user (Obsidian + Claude Code) | Git-based wiki supports PRs, reviews. Ingest Agent creates commits | No contributor workflow |
| **Cross-project knowledge** | Wiki pages accumulate cross-project context | Same benefit, automated. Tool pages grow richer per project | Docs siloed per project. No cross-project enrichment |

## Recommendation

Start with Phase 1 — highest leverage, lowest effort. Add CI sync from `wiki/` to S3, repoint the Bedrock KB. The article pipeline and chatbot immediately get better grounding with zero downstream code changes. Evaluate empirically (compare chatbot answers and article quality before/after) before investing in Phase 2 automation.

Phase 2 becomes valuable once 10+ projects are ingested and manual Claude Code sessions become a bottleneck. The CLAUDE.md schema is already the perfect system prompt for the Ingest Agent.

Phase 3 is the long-term destination but not urgent — the article pipeline and chatbot already work, they just get better data from Phases 1 and 2.

## Related Pages

- [[k8s-bootstrap-pipeline]] — first project ingested into this wiki
- [[aws-step-functions]] — orchestration engine used by both SM-A/SM-B and the article pipeline
- [[shift-left-validation]] — testing philosophy applicable to wiki maintenance automation
- [[event-driven-orchestration]] — pattern shared between bootstrap pipeline and proposed wiki sync
