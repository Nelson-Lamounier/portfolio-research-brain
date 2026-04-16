---
title: Wiki Log
type: log
---

# Knowledge Base Log

## [2026-04-15] ingest | Self-Healing Agent LLM Design Review
- Source: `raw/self_healing_design_review.md`
- Pattern: Reactive Autonomous Agent — third distinct LLM pattern (vs Deterministic Workflow / Managed RAG); LLM-driven tool-use loop with no state machine; model chooses tool sequence and stopping condition
- Key findings:
  - `ConverseCommand` + `tool_use` loop (same low-level API as article pipeline, not InvokeAgent); MAX_ITERATIONS=10 hard stop; no Extended Thinking (Gap SH-R1)
  - 6 MCP tools via AgentCore Gateway: 4 read-only (diagnose_alarm, check_node_health, analyse_cluster_health, get_node_diagnostic_json) + 1 WRITE (remediate_node_bootstrap → Step Functions StartExecution) + 1 inconsistency (ebs_detach: in fallback tools but no Gateway Lambda, Gap SH-S3)
  - Dynamic tool discovery at invocation time via MCP `tools/list` — new Gateway tools require no Lambda code change
  - Cognito M2M authentication: `client_credentials` flow, JWT cached + refreshed 60s before expiry
  - S3 episodic memory: `sessions/{alarm}/{timestamp}.json`, previous session injected into prompt (prevents remediation loops); truncated to 2000 chars
  - Hybrid prompt design: LLM autonomous by default; for known bootstrap alarm patterns, runtime injects near-deterministic DIAGNOSE→CLASSIFY→REMEDIATE→VERIFY workflow (strong design choice)
  - Conversation history accretes unboundedly — input tokens grow each iteration (Gap SH-C2)
  - No KB — uses live infrastructure APIs as information source (correct design for operational agent)
  - Security gaps: 4 HIGH: SH-S1 (system prompt in plaintext env var), SH-S2 (SSM SendCommand wildcard), SH-S5 (prompt injection via EventBridge payload), SH-S6 (no SQS rate limiting — alarm storms)
  - SH-R4 (HIGH): post-remediation check_node_health verification is advisory only — model can end_turn after remediate_node_bootstrap without verifying
  - SH-R5 (HIGH, most operationally critical): no outcome tracking — no way to know if agent actually fixed anything; CloudWatch `ALARM→OK` correlation with DynamoDB session records would close gap
  - 15 total gaps: SH-S1-S7, SH-C1-C3, SH-R1-R5; 5 HIGH severity
- Existing page corrections: `wiki/concepts/self-healing-agent.md` had only 4 tools listed (missing get_node_diagnostic_json and remediate_node_bootstrap — the critical write tool); no session memory, no Cognito M2M, no design rationale — all updated
- Pages created (1):
  - `wiki/ai-engineering/self-healing-agent.md` — full LLM design: 3-pattern comparison table, architecture Mermaid, model invocation, 6 tools (corrected inventory), dynamic discovery, Cognito M2M auth, agentic loop pseudocode, hybrid prompt architecture, bootstrap guidance block, S3 session memory, all 15 gaps with full security/cost/reasoning breakdown, reasoning technique assessment (Extended Thinking ❌, CoT ⚠️, Self-Refinement ⚠️, Search+Verifier ⚠️, Reward Modelling ❌)
- Pages updated (2):
  - `wiki/concepts/self-healing-agent.md` — corrected tool list (now 5+1 with write flag), updated Mermaid diagram, added S3 episodic memory section, added design rationale section, added ai-engineering cross-reference, updated sources/date
  - `index.md` — added ai-engineering/self-healing-agent entry; updated concepts/self-healing-agent description

## [2026-04-15] ingest | Bedrock Chatbot System Design Review
- Source: `raw/chatbot_system_design_review.md`
- **Context note**: Review conducted against KB *prior to LLM Wiki migration* — old KB = raw project docs in S3 `kb-docs/` prefix. Gap assessments annotated with post-migration impact in `rag-techniques.md`.
- Key findings:
  - Pattern: RAG-Grounded Conversational Agent — `InvokeAgentCommand` (managed Bedrock Agent), NOT `ConverseCommand`; Lambda passes only `inputText` + `sessionId`; all prompt/RAG/guardrail logic is CDK config
  - 6-layer defence-in-depth: CORS → input sanitisation (9 patterns) → InvokeAgentCommand → output sanitisation (ARN/IP/credential redaction) → audit log (SHA-256 prompt hash)
  - System prompt: deploy-time static in `chatbot-persona.ts` (CDK property); cannot change without CDK deploy; no few-shot examples; 100-200 word limit aspirational
  - Guardrails: content filters all HIGH; topic denial (OffTopicQueries + CodeGenerationRequests); contextual grounding GROUNDING+RELEVANCE at 0.7; PROMPT_ATTACK outputStrength: NONE (intentional, undocumented)
  - Gap S1 (HIGH): No WAF on API Gateway — production blocker
  - Gap C2: Chatbot uses direct cross-region inference profile with no cost-allocation tags — chatbot Bedrock costs invisible in Cost Explorer
  - Gap A8 (HIGH): No RAG evaluation pipeline — zero observability on context relevance, faithfulness, or answer correctness; becomes critical during KB migration
  - Gap A6: Pure vector retrieval — no hybrid keyword+BM25; severity *increases* post-migration as LLM Wiki has richer technical vocabulary (exact term failure mode worsens)
  - Gap A4: YAML frontmatter + code blocks not pre-processed before ingestion; wiki frontmatter still needs stripping; Mermaid blocks need special handling; wikilinks are low-information tokens
  - InvokeAgentCommand limitation: Extended Thinking unavailable via managed agent API (Gap A2) — getting CoT would require architectural shift to ConverseCommand + explicit RetrieveCommand
  - 20 total gaps: S (security), C (cost), P (prompt testing), A (adaptation/RAG techniques)
- Pages created (2):
  - `wiki/ai-engineering/chatbot.md` — full chatbot architecture: RAG pattern classification table vs article pipeline, 6-layer request lifecycle Mermaid, InvokeAgentCommand invocation, system prompt anatomy, KB integration (automatic RAG black box), Guardrails architecture table, EMF metrics, all 20 gaps (S/C/P/A)
  - `wiki/ai-engineering/rag-techniques.md` — 12-technique RAG inventory (A–L): fine-tuning 🚫, PEFT 🚫, zero/few-shot ⚠️, CoT ❌, role/user-context ✅/❌, document parsing ⚠️ (A4/A5), indexing ✅/❌ (A6), ANN ✅, prompt-for-RAG ⚠️ (A7), RAFT 🚫, RAG evaluation ❌ (A8 HIGH), hierarchical chunking ✅; migration impact column per gap
- Pages updated (1):
  - `wiki/tools/aws-bedrock.md` — added Bedrock Guardrails section (content filters, topic denial, grounding filter code), InvokeAgentCommand section (promptSessionAttributes, sessionAttributes); updated sources, related pages
  - `index.md` — added chatbot and rag-techniques to AI Engineering section; updated aws-bedrock description

## [2026-04-15] ingest | Article Pipeline AI Engineering Review
- Source: `raw/article_pipeline_design_review.md`
- New wiki domain created: `wiki/ai-engineering/` — LLM system design, inference-time techniques, prompt engineering, RAG patterns
- CLAUDE.md updated: domain expanded to include "AI Engineering"; `ai-engineering/` added to wiki directory structure
- Key findings:
  - Pattern: Deterministic Workflow Agent — `ConverseCommand` (direct model API) not `InvokeAgentCommand` (managed runtime); 3 specialised Lambdas (Research → Writer → QA) via Step Functions
  - Model assignment: Haiku 4.5 for Research (extraction, cost-efficient), Sonnet 4.6 for Writer (32K tokens, 2K–16K adaptive thinking) and QA (16K tokens, 8K fixed thinking)
  - Adaptive compute: `analyseComplexity()` deterministic pre-model signal (5 signals → 3 tiers → thinking budget); scales Writer budget LOW=2K/MID=8K/HIGH=16K
  - Prompt caching: blog-persona.ts 816-line prompt, `cachePoint` after 3,650 tokens of static content → ~90% system prompt cost reduction per invocation
  - KB integration: explicit `RetrieveCommand` (top-10 passages, 1K query cap) vs chatbot's automatic RAG; passages typed as `KbPassage[]` with score+sourceUri
  - DynamoDB single-table: `ARTICLE#{slug}` PK, `VERSION#v{n}` / `METADATA` SK, `STATUS#{status}` GSI1
  - Application Inference Profiles: FinOps cost allocation tags; EU cross-region for capacity resilience
  - QA rubric: 5 dimensions — Technical Accuracy 35%, SEO 20%, MDX Structure 15%, Metadata Quality 15%, Content Quality 15%; `overallScore ≥ 80` → review, else → flagged
  - 19 total gaps across 4 categories: S (security), C (cost), P (prompt testing), R (reasoning techniques)
  - Gap R5 (HIGH): QA `issues[]` never fed back to Writer on retry — structured feedback stored in DynamoDB but not injected into Writer retry user message; in-pipeline self-refinement loop missing
  - 11 inference-time techniques assessed: Extended Thinking ✅, Adaptive Compute ✅, CoT ⚠️, Self-Consistency ❌, Sequential Revision ⚠️, Search+Verifier ✅, ToT 🚫, SFT/RL 🚫
- Pages created (3):
  - `wiki/ai-engineering/article-pipeline.md` — full pipeline architecture: Mermaid flow diagram, model assignment, 5 Lambda roles, system prompt anatomy, KB integration table, DynamoDB design, cost monitoring (EMF + Application Inference Profiles), security gaps S1–S6, full 19-gap inventory, prompt evolution strategy
  - `wiki/ai-engineering/inference-time-techniques.md` — 11-technique inventory with status symbols; Extended Thinking + adaptive compute deep-dive; CoT partial implementation; Self-Consistency gap R4; Sequential Revision gap R5 Mermaid revision loop diagram; Search+Verifier mapping; training-time techniques (not applicable)
  - `wiki/tools/aws-bedrock.md` — ConverseCommand vs InvokeAgentCommand table; Extended Thinking API code; KB RetrieveCommand + update matrix; Application Inference Profiles CDK; prompt caching strategy (cachePoint placement rule); runAgent() shared utility; EMF metrics catalogue
- Pages updated (2):
  - `CLAUDE.md` — domain updated to include AI Engineering; `ai-engineering/` added to wiki directory schema
  - `index.md` — new "AI Engineering" section with 2 entries; aws-bedrock tool entry added

## [2026-04-15] ingest | Frontend Monorepo System Design Review
- Source: `raw/system_design_review.md`
- Frontend-portfolio monorepo: Yarn 4 workspaces, `apps/site` (Next.js 15) + `apps/start-admin` (TanStack Start)
- Key findings:
  - `apps/site`: Next.js 15 App Router, `output: 'standalone'`, 7 API routes, `/api/metrics` (prom-client + SSM Bearer auth + 5min cache), `/api/chat` (Bedrock proxy), `/log-proxy` (Faro RUM rewrite — avoids CORS); DynamoDB single-table + S3 for MDX; OTel instrumentation.ts hook → OTLP/gRPC → Alloy → Tempo; 4-stage AL2023 Docker (UID 1001); security gap: **no CSP**
  - `apps/start-admin`: TanStack Start (Vinxi/Vite), `createServerFn` type-safe RPC, 12 server modules, Cognito PKCE OAuth (PKCE verifier in httpOnly cookie, JWT in __session 24h httpOnly), `requireAuth()` on all routes, full CSP via `getUserSessionFn`, Vitest testing (3 test files); 4-stage Docker (Vite SSR dist/)
  - Comparative analysis: 20-dimension table; key asymmetry = site has OTel+Prometheus, admin has CSP; start-admin = TanStack Start (not Next.js as previously documented in bff-pattern)
  - 7 known gaps: no CSP on site, no OTel on admin, no rate limit on /api/chat, /api/revalidate unauthenticated, awsEcsDetector on K8s, unsafe-inline in admin CSP, cold Prometheus cache on restart
  - Corrected `bff-pattern.md`: was incorrectly labelling start-admin as "Next.js admin dashboard" — updated to TanStack Start with `createServerFn` BFF primitive section
- Pages created (3):
  - `wiki/projects/frontend-portfolio.md` — Yarn 4 monorepo overview, side-by-side comparison table, Docker strategy, supporting infrastructure table, 7 known gaps, best practices
  - `wiki/tools/nextjs.md` — Next.js 15 App Router: 7 API routes, prom-client metrics endpoint, /log-proxy rewrite, DynamoDB+S3 data layer, caching architecture Mermaid, OTel instrumentation.ts, Docker 4-stage, MDX pipeline, security gaps
  - `wiki/tools/tanstack-start.md` — TanStack Start: createServerFn RPC pattern, 12 server modules, Cognito PKCE sequence diagram, requireAuth() guard, CSP implementation, Vitest testing, Docker 4-stage, Tailwind v4 Vite plugin
- Pages updated (4):
  - `wiki/concepts/observability-stack.md` — added Application-Level Metrics (prom-client) section; updated Alloy Faro section with /log-proxy rewrite pattern; updated sources/date
  - `wiki/patterns/bff-pattern.md` — corrected start-admin from "Next.js" to TanStack Start; added createServerFn BFF primitive section; added related pages (tanstack-start, frontend-portfolio)
  - `wiki/projects/k8s-bootstrap-pipeline.md` — added frontend-portfolio, nextjs, tanstack-start to Related Pages
  - `index.md` — added frontend-portfolio project, nextjs tool, tanstack-start tool; updated observability-stack description; updated bff-pattern description

## [2026-04-15] ingest | Notification Architecture Review
- Source: `raw/notification_implementation_review.md`
- Post-remediation final review — all 3 gaps resolved as of 15 April 2026
- Key findings:
  - Three notification planes: Grafana Unified Alerting → SNS → Email; CloudWatch Alarms → SNS → Email; ArgoCD Notifications → GitHub Commit Status API
  - 5 SNS topics: monitoring-alerts (worker-asg-stack, KMS encrypted, EC2 IAM→IMDSv2 publish), bootstrap-alarm (ssm-automation-stack, ExecutionsFailed, treatMissingData NOT_BREACHING), dlq-alerts (api-stack, ALARM+OK states), finops-alerts (budgets.amazonaws.com service principal, 50/80/100% thresholds, Bedrock sub-budget reuses same topic), security-baseline-alerts
  - Gap 1 (fixed): notificationEmail not passed to monitoringPoolStack — Grafana alerts published to SNS but never delivered; fixed in factory.ts
  - Gap 2 (already handled): inject_monitoring_helm_params in steps/apps.py was reading SSM ARN and patching ArgoCD Application as Step 5b
  - Gap 3 (fixed): ArgoCD notifications secret had no automated bootstrap path; new provision_argocd_notifications_secret (Step 5e) reads SSM SecureStrings, idempotent (409→replace), non-fatal
  - Grafana file-based provisioning: contactpoints.yaml + policies.yaml + rules.yaml in grafana-alerting ConfigMap; checksum/config annotation triggers rolling restart on change
  - Conditional SNS contact point: snsTopicArn="" (silent mode) until bootstrap Step 5b overwrites; disableResolveMessage: false → recovery notifications delivered
  - Routing: group_wait 30s, group_interval 5m, repeat_interval 4h, group_by [grafana_folder, alertname]
  - A→B→C evaluation required by Grafana UA (PromQL → Reduce last → Threshold)
  - 12 alert rules in 4 groups — key asymmetry: Pod CrashLooping for:0s (monotonic counter) vs Node Down for:2m (transient scrape flip)
  - DynamoDB alerts on traces_spanmetrics_* metrics — generated by Tempo SpanMetrics pipeline from OTel spans; DynamoDB has no native Prometheus endpoint
  - Span Ingestion Stopped (for:10m) = meta-alert on observability pipeline itself
  - ArgoCD Notifications: GitHub App auth (not PAT), defaultTriggers applies to all 10 apps without annotation, status label argocd/<app-name> visible in PR merge protection
- Pages created (1):
  - `wiki/concepts/notification-architecture.md` — all 3 notification planes, 5 SNS topics (CDK + IAM), Grafana unified alerting (contact point, routing policy, 12-rule catalogue), SSM→Helm wiring chain diagram, ArgoCD GitHub App commit status, CLI audit commands, 3 gap fixes, hardening roadmap
- Pages updated (3):
  - `wiki/concepts/observability-stack.md` — expanded Grafana Alerting section: full 12-rule table with `for` values, DynamoDB spanmetrics source explanation, A→B→C pattern, updated known gaps
  - `wiki/tools/argocd.md` — added ArgoCD Notifications section (GitHub App auth, Step 5e, defaultTriggers, commit status label, non-fatal behavior)
  - `index.md` — added notification-architecture entry; updated observability-stack description

## [2026-04-13] init | Knowledge base initialized
- Created directory structure: raw/, wiki/ (projects, concepts, tools, patterns, troubleshooting, commands, comparisons)
- Created CLAUDE.md schema
- Created index.md and log.md
- Initialized git repository

## [2026-04-13] ingest | K8s Bootstrap — Deploy & Test Reference
- Source: `raw/step-function-runtime-logging.md`
- Comprehensive wiki covering CDK-managed Kubernetes bootstrap pipeline: self-hosted K8s on EC2, two-tier Step Functions orchestration (SM-A bootstrap + SM-B config), SSM Run Command execution, local-first testing workflow, 4 ADRs, Linux permissions deep-dive
- Pages created (13):
  - `wiki/projects/k8s-bootstrap-pipeline.md` — project overview with architecture, ADRs, testing workflow, logging
  - `wiki/concepts/self-hosted-kubernetes.md` — kubeadm on EC2, 10-step CP bootstrap, 5-step worker bootstrap, idempotency
  - `wiki/concepts/shift-left-validation.md` — local-first testing philosophy, four gates, immutable infra / mutable scripts
  - `wiki/tools/aws-step-functions.md` — SM-A and SM-B definitions, poll loop, CDK pattern, logging
  - `wiki/tools/aws-ssm.md` — Run Command vs SSH, SSM documents, Session Manager, Parameter Store, bash preamble
  - `wiki/tools/calico.md` — CNI concept, why Calico, installation steps
  - `wiki/tools/aws-ccm.md` — cloud provider taint, what CCM does, installation
  - `wiki/tools/argocd.md` — GitOps role, two execution paths (bootstrap-run vs SM-A)
  - `wiki/tools/github-actions.md` — OIDC, custom CI image, path scoping, concurrency
  - `wiki/tools/just.md` — task runner recipes organized by workflow
  - `wiki/patterns/event-driven-orchestration.md` — SM-A → EventBridge → SM-B self-healing pattern
  - `wiki/patterns/poll-loop-pattern.md` — custom Step Functions SSM polling with CDK code
  - `wiki/troubleshooting/ssm-permission-denied.md` — root cause analysis, two-layer fix, EBS persistence
  - `wiki/commands/k8s-bootstrap-commands.md` — full command reference (deploy, bootstrap, SF, CloudWatch, CDK)
- Updated: index.md

## [2026-04-14] build | Mermaid diagram support
- Added `mermaid ^11.4.1` to portfolio-doc
- Created `portfolio-doc/src/components/MermaidDiagram.tsx` — SSR-safe, dark mode aware, responsive SVG rendering via dynamic import
- Updated `portfolio-doc/src/components/Fence.tsx` — routes `language === 'mermaid'` fences to MermaidDiagram component
- Updated `CLAUDE.md` — added Diagrams convention: use Mermaid for all visual representations; includes type guide and spectrum/flow/architecture examples
- Updated `wiki/concepts/shift-left-validation.md` — replaced plain-text cost spectrum with a `flowchart LR` Mermaid diagram

## [2026-04-14] build | Option B integration — wiki → S3 → portfolio-doc
- Created: `scripts/sync-wiki.py` — transforms wikilinks, builds portfolio frontmatter, generates Bedrock `.metadata.json` sidecars, uploads to S3 (both `kb-docs/` and `portfolio-docs/` prefixes)
- Created: `scripts/requirements.txt` — boto3, PyYAML
- Created: `.github/workflows/sync-wiki-to-s3.yml` — CI trigger on wiki/ or index.md changes
- Created: `portfolio-doc/scripts/fetch-wiki.mjs` — downloads wiki pages from S3 (or local path) into src/docs/{slug}/page.md; generates manifest.json
- Created: `portfolio-doc/scripts/generate-navigation.mjs` — reads manifest.json, generates src/lib/navigation.ts from wiki index.md sections
- Updated: `portfolio-doc/package.json` — added wiki:fetch, wiki:fetch:local, prebuild scripts
- Updated: `portfolio-doc/.gitignore` — excludes generated wiki pages and manifest
- Verified: build passes with 15 wiki pages rendered; navigation auto-generated with 7 sections

## [2026-04-14] ingest | Kubernetes Self-Healing System — System Design Review
- Source: `raw/kubernetes_system_design_review.md`
- Comprehensive system design review covering the full portfolio infrastructure: cluster topology, networking, API services, progressive delivery, observability, DR, and self-healing agent
- Pages created (7):
  - `wiki/concepts/self-healing-agent.md` — CloudWatch → EventBridge → Lambda → Bedrock ConverseCommand loop → MCP Gateway → SNS; FinOps observability
  - `wiki/tools/traefik.md` — DaemonSet + hostNetwork design, TLS boundary, Prometheus metrics, OTLP traces, PDB disabled (ArgoCD v3 bug)
  - `wiki/tools/argo-rollouts.md` — Blue/Green strategy, manual gate, Prometheus AnalysisTemplate, N-1 static asset retention
  - `wiki/concepts/observability-stack.md` — LGTM + Alloy, monitoring pool isolation, Traefik → Tempo traces, EBS PV lifecycle
  - `wiki/concepts/disaster-recovery.md` — backup matrix (etcd/PKI → S3, TLS/JWT → SSM), _reconstruct_control_plane, RTO 5–8 min
  - `wiki/patterns/bff-pattern.md` — pod-to-pod admin calls, CORS as defence-in-depth
  - `wiki/tools/hono.md` — public-api (port 3001) and admin-api (port 3002), IMDS credentials, DynamoDB GSI pattern, FinOps routes
- Pages updated (4):
  - `wiki/concepts/self-hosted-kubernetes.md` — added worker pool parameterization, cluster topology table, CA mismatch detection, stale PV cleanup, Cluster Autoscaler IAM split
  - `wiki/tools/argocd.md` — added App-of-Apps structure, 41-step bootstrap sequence, JWT key continuity, Image Updater, ignoreDifferences
  - `wiki/projects/k8s-bootstrap-pipeline.md` — added network path diagram, in-cluster services table, BFF and Argo Rollouts design decisions
  - `wiki/tools/aws-ssm.md` — added SSM over Fn::ImportValue design decision, DR SecureString parameters
- Updated: index.md

## [2026-04-14] analysis | LLM Wiki vs Bedrock Pipeline — System Design Review
- Created: `wiki/comparisons/llm-wiki-vs-bedrock-pipeline.md`
- Comparative analysis of LLM Wiki (interlinked synthesis) vs Bedrock article pipeline (automated delivery)
- Key finding: systems are complementary — wiki produces best content, Bedrock provides best delivery
- Proposed hybrid architecture: wiki pages as vector source instead of raw flat docs
- 3-phase migration plan: (1) CI sync wiki→S3, (2) automate wiki maintenance with Bedrock Ingest Agent, (3) full pipeline integration
- Long-term scalability analysis across 100/500/1000+ source thresholds
- Updated: index.md

## [2026-04-14] ingest | CDK Base Stack & Full Stack Catalogue Review
- Source: `raw/base-stack-review.md`
- Comprehensive CDK IaC review covering the complete 10-stack Kubernetes infrastructure: KubernetesBaseStack deep-dive, GoldenAMI pipeline, ControlPlane and WorkerAsg stacks, AppIAM, Data, API (serverless subscription), Edge (CloudFront+WAF), Observability, and SsmAutomation stacks
- Key findings: instance types were swapped in prior wiki (general-pool is t3.medium, monitoring-pool is t3.small); EBS CSI migration from local-path (2026-03-31); 3600s RunCommand timeout raised after 2026-04-13 production SIGKILL incident; EIP permanently bound to NLB (not EC2)
- Pages created (4):
  - `wiki/tools/aws-cloudfront.md` — K8sEdgeStack: CloudFront + WAF + ACM, two TLS points, X-Origin-Verify, cross-region SSM read timestamp pattern
  - `wiki/tools/aws-ebs-csi.md` — EBS CSI Driver: controller/node topology, ebs-sc StorageClass, WaitForFirstConsumer, 10Gi PVs, Recreate strategy, local-path migration
  - `wiki/tools/ec2-image-builder.md` — GoldenAmiStack: baked toolchain, 15 min → 2–3 min bootstrap, SSM AMI ID
  - `wiki/concepts/cdk-kubernetes-stacks.md` — full 10-stack catalogue with deployment order diagram, lifecycle separation, config-driven SG pattern, EBS data volume design
- Pages updated (7):
  - `wiki/concepts/self-hosted-kubernetes.md` — corrected instance types (general: t3.medium/t3a.medium, monitoring: t3.small/t3a.small), min/max (2/3 and 1/1), ebs-sc stale PV cleanup, local-path migration note
  - `wiki/projects/k8s-bootstrap-pipeline.md` — corrected cluster topology, expanded CDK stacks table (5→10 stacks), added new tool links
  - `wiki/tools/aws-step-functions.md` — added 3600s timeout incident (2026-04-13), Node Drift Enforcement, ResourceCleanupProvider
  - `wiki/concepts/disaster-recovery.md` — EIP permanently bound to NLB, EBS deleteOnTermination rationale, full cluster rebuild path
  - `wiki/concepts/observability-stack.md` — updated PV section (ebs-sc, 10Gi, Recreate strategy), local-path migration context
  - `wiki/tools/argocd.md` — EBS CSI Driver at Sync Wave 4, expanded sync wave table
  - `wiki/tools/aws-ssm.md` — added complete 14-parameter BaseStack SSM output table
- Updated: index.md

## [2026-04-14] ingest | Kubernetes App Review, kubectl Operations Reference & System Design Draft
- Sources: `raw/kubectl-operations-reference.md`, `raw/kubernetes_app_review.md`, `raw/kubernetes_system_design_review copy.md`
- Detailed app-layer and operations review covering: 7-wave ArgoCD sync map, ApplicationSet Git Directory Generator, multi-source Apps, Image Updater, 16-step bootstrap sequence, Helm chart golden-path architecture, IngressRoute ownership boundary, secret rotation OR pattern, IngressRoute priority cascade, Argo Rollouts scalar() bug fix, HPA targeting Rollout, ResourceQuota blue/green formula, NetworkPolicy dual ipBlock for Traefik hostNetwork, Crossplane IDP pattern, Steampipe cloud inventory datasource, cert-manager motivation, day-2 kubectl operations reference
- Note: `kubernetes_system_design_review copy.md` is an older draft (swapped instance types, stale local-path references); reviewed but no pages created from it
- Pages created (4):
  - `wiki/tools/crossplane.md` — Kubernetes-native IDP: EncryptedBucket/MonitoredQueue XRDs, Composition model, wave 4/5/6 ordering, credentials model
  - `wiki/tools/steampipe.md` — Cloud inventory SQL FDW in monitoring namespace: PostgreSQL Grafana datasource, IMDS credentials, three-level debugging workflow, SQL pitfalls
  - `wiki/commands/kubectl-operations.md` — day-2 cluster operations reference: get/describe/exec/rollout/logs, ArgoCD+kubectl workflow, JSONPath vs JMESPath comparison, OOMKilled/CrashLoopBackOff troubleshooting, Grafana 3-level debugging
  - `wiki/patterns/helm-chart-architecture.md` — chart layout pattern, feature flags, selectorLabels vs fullLabels immutability, golden-path service template, Secrets vs ConfigMap classification, ownership boundary table
- Pages updated (7):
  - `wiki/tools/argocd.md` — major rewrite: 7-wave sync map table, ApplicationSet Git Directory Generator, multi-source Applications, standard sync options, retry config, selfHeal vs ignoreDifferences, bootstrap sequence expanded to 16 detailed steps, Image Updater newest-build strategy
  - `wiki/tools/traefik.md` — added IngressRoute ownership boundary (deploy.py vs ArgoCD), CloudFront secret rotation OR pattern, IngressRoute priority cascade (200/100/50)
  - `wiki/tools/argo-rollouts.md` — expanded PromQL analysis with scalar() bug fix (2026-03-18), isNaN guard rationale, explicit thresholds; added HPA targeting Rollout YAML; added ResourceQuota blue/green formula
  - `wiki/tools/calico.md` — added NetworkPolicy dual ipBlock section (VPC CIDR + pod CIDR) for Traefik hostNetwork pods
  - `wiki/concepts/observability-stack.md` — added Steampipe as PostgreSQL FDW Grafana datasource; added steampipe to related pages
  - `wiki/commands/k8s-bootstrap-commands.md` — added kubectl-operations cross-reference in related pages
  - `wiki/index.md` — added crossplane and steampipe entries; updated descriptions for argocd, traefik, argo-rollouts, calico

## [2026-04-14] ingest | Kubernetes Observability Report & Prometheus Scrape Targets Guide
- Sources: `raw/kubernetes_observability_report.md`, `raw/prometheus-targets-troubleshooting.md`
- Key correction: the wiki incorrectly labelled Grafana Alloy as a DaemonSet log shipper — Alloy is a single-pod Deployment receiving Grafana Faro SDK (RUM) browser telemetry; Promtail is the actual DaemonSet log shipper (previously missing from the wiki entirely)
- Comprehensive additions: full 10-job Prometheus scrape inventory (including nextjs-app-preview for Blue/Green comparison), Tempo metrics_generator for DynamoDB observability without CloudWatch, Grafana dashboard GitOps pattern (Files.Glob → ConfigMaps → 60s auto-reload), 16-dashboard inventory, Grafana alerting via SNS (4 groups including Span Ingestion Stopped), traces↔logs correlation wiring, security hardening (IPAllowList + BasicAuth + non-root), CloudWatch 3-phase evolution story, FinOps cost formula (kube-state-metrics label_workload pricing)
- Prometheus troubleshooting: 6 real production scrape failures — all rooted in sub-path routing (--web.external-url=/prometheus); relabel two-source_labels fix, metrics_path fixes, annotation fix, missing job, replicas:0; sub-path prefix reference table; related Grafana datasource + Tempo remote_write URL fixes
- Pages created (2):
  - `wiki/tools/promtail.md` — DaemonSet log shipper: kubernetes-pods + journal scrape jobs, CRI parsing, Loki push API, Loki→Tempo TraceID derived fields
  - `wiki/troubleshooting/prometheus-scrape-targets.md` — 6-issue guide with root causes, fixes, verification commands, sub-path reference table, ConfigMap restart workflow
- Pages updated (4):
  - `wiki/concepts/observability-stack.md` — major rewrite: fixed Alloy/Promtail roles, corrected component topology diagram, added full scrape job table, Grafana datasource provisioning, dashboard GitOps pattern, 16-dashboard inventory, alerting (4 groups), traces↔logs correlation, security hardening, CloudWatch evolution story, FinOps cost formula
  - `wiki/tools/steampipe.md` — added cloud-inventory dashboard panel table, multi-region config (eu-west-1 + us-east-1)
  - `wiki/commands/kubectl-operations.md` — added ephemeral curl pod pattern section with NetworkPolicy-aware testing examples
  - `wiki/index.md` — updated observability-stack description; added promtail and prometheus-scrape-targets entries

## [2026-04-14] ingest | Monitoring Strategy Review & RUM Dashboard Review
- Sources: `raw/monitoring-strategy-review.md`, `raw/rum-dashboard-review.md`
- Key corrections: dashboard count corrected from 15–16 → 13 (actual JSON files in chart); Prometheus scrape jobs expanded to 12 with two additional jobs (kubernetes-nodes kubelet endpoint + kubernetes-service-endpoints annotation-driven); Traefik/node-exporter port 9100 collision documented
- New content: monitoring Helm chart directory structure (13 service-isolated subdirectories); Tempo config limits (max_bytes_per_trace 5MB, max_live_traces 2000, no search block); Loki config details (auth_enabled: false, rate limits); Alloy CORS open + StripPrefix IngressRoute; Faro Collector Health panels (Alloy Status, Memory RSS, Accepted vs Dropped throughput); JS error panels in rum.json; SEO angle for Core Web Vitals; ResourceQuota numbers (1500m CPU / 2Gi memory / 6 PVCs); known limitations table (single-AZ, Spot interruption, Tempo local storage, Faro CORS, Steampipe password); alerting observations (for: 0s, no inhibition rules)
- Pages updated (3):
  - `wiki/concepts/observability-stack.md` — added monitoring chart structure; corrected dashboard count to 13 with filenames; expanded scrape job table to 12; added Loki config section; expanded Alloy/RUM section (SEO, Faro Collector Health, JS error panels, CORS note); added ResourceQuota section; added Known Limitations table; updated alerting with known gaps; added Tempo config limits; corrected minor details throughout
  - `wiki/tools/steampipe.md` — added Steampipe plaintext password known issue note
  - `wiki/index.md` — updated observability-stack description (correct dashboard count, added known limitations)

## [2026-04-15] ingest | Scripts, Justfile & Operational Tooling Review
- Source: `raw/scripts_justfile_review.md`
- Key findings:
  - justfile is the stable CLI contract: 6 recipe groups (cdk/ci/test/k8s/ops/infra), all 26 GHA workflows call `just` recipes — one-line justfile change propagates everywhere
  - scripts/lib/: logger.ts monkey-patches console.{log,warn,error} for file capture (timestamped logs); resolveAuth() detects GITHUB_ACTIONS → zero if-branches in app code
  - control-plane-troubleshoot.ts (1,737 lines, 4 phases): SSM RunCommand as remote shell with named marker protocol; severity tiers (critical/warning/info); --fix and --skip-k8s flags
  - ssm-automation.ts: dual CWL/API log retrieval — CloudWatch paginated (unlimited) first, GetCommandInvocation (24KB) fallback; log group auto-resolution from document name
  - asg-audit.ts: Promise.all for 8 parallel API calls (16s → 2s); live resources vs CloudWatch dashboard widget definitions
  - control-plane-autofix.ts: encodes 3 runbooks (cert SAN mismatch, kubeadm-config podSubnet, worker not joining); --dry-run; post-repair diagnostic auto-runs
  - ebs-lifecycle-audit.ts: pre-deploy check for DeleteOnTermination: true on etcd data volume
  - cfn-troubleshoot.ts: filters to first CREATE_FAILED event only; invoked automatically by CI on non-zero CDK deploy
  - fix-control-plane-cert.sh: Bash emergency fallback (no Node.js); uses IMDSv2 token-based IMDS
  - kb-drift-check.py: .kb-map.yml maps code paths to KB docs; git diff cross-reference; dual-mode CI annotations vs human-readable; PyYAML-free fallback
  - Known debt: formatDuration() duplicated, listParemeters typo, no unit tests for scripts
- Pages created (2):
  - `wiki/concepts/operational-scripts.md` — full diagnostic scripts architecture: shared lib (logger.ts, aws-helpers.ts), flagship troubleshooter (4 phases, SSM marker protocol), ssm-automation inspector, asg-audit orphan detection, autofix runbooks, DynamoDB migration, kb-drift-check, 5 cross-cutting patterns, known tech debt
  - `wiki/troubleshooting/control-plane-cert-san-mismatch.md` — root cause (restored backup cert has old IPs), symptoms, diagnosis (just diagnose Phase 3), 3 repair options (autofix.ts, Bash fallback, full DR path), verification, prevention notes
- Pages updated (4):
  - `wiki/tools/just.md` — major rewrite: recipe groups table, why just vs npm/Make comparison table, CI/CD integration pattern, key design decisions, solo-dev operational rationale
  - `wiki/concepts/disaster-recovery.md` — added Certificate SAN Mismatch section with detection/repair references; added control-plane-cert-san-mismatch and operational-scripts links
  - `index.md` — added operational-scripts, control-plane-cert-san-mismatch entries; updated just description
  - `log.md` — this entry

## [2026-04-14] ingest | CI/CD Architecture, Infrastructure Testing & AWS DevOps Certification
- Sources: `raw/devops_cicd_architecture_review.md`, `raw/infra_tests_architecture_review.md`, `raw/aws-devops-professional-certification.md`
- Key findings:
  - 26-workflow GitHub Actions monorepo (~12K YAML + ~3.5K TypeScript + ~550 Python); TypeScript scripting layer replaces Bash for all non-trivial CI logic
  - AROA masking: `aws sts get-caller-identity → AROA → echo "::add-mask::$AROA_ID"` — IAM reconnaissance prevention above standard OIDC
  - sha-rAttempt image tags: `${github.sha}-r${github.run_attempt}` — immutable artifact per retry, prevents ECR tag overwrite
  - cancel-in-progress semantics differ: `true` for app pipelines (latest commit wins), `false` for infra pipelines (mid-deploy CloudFormation must complete)
  - CDK synth caching via synthesize.ts: runs once → artifact → all deploy jobs restore; ~4 min saved per pipeline run
  - verify-argocd-sync.ts: every ArgoCD API call proxied via SSM send-command; inline Python filter prevents 24KB SSM stdout truncation; self-healing CI bot token refresh
  - 50 test files (~8,000 lines TypeScript): 32 unit (Template.fromStack, parallel) + 16 integration (SSM-anchored, sequential, 60s timeout) + 5 fixture files
  - SSM anchor pattern: GetParametersByPath first → all resource IDs from SSM → three-layer assertion (deployed + published + correct value)
  - requireParam helper: replaces ! non-null assertion with descriptive error; diagnostic-first failure messages (formatIpPermission)
  - describe.each: both worker pool configs run same assertions
  - satisfies over as const: rename-safe SSM path management
  - jest-worker-setup.js: process.chdir(infraRoot) fixes monorepo CWD drift (Jest workers inherit CWD=/repo-root, CDK expects CWD=infra/)
  - DOP-C02 failed by 24 points (726/750) while working at AWS Dublin; SPIDER framework built from root cause analysis; passed on attempt 2 with 30 min remaining
  - Exam insight: "decision-making simulation" not knowledge test; all four options technically valid; constraint enumeration is the skill
- Pages created (4):
  - `wiki/concepts/ci-cd-pipeline-architecture.md` — 26-workflow architecture, TypeScript CI/CD scripting layer (pipeline-setup/preflight/synthesize/security-scan/finalize/observe-bootstrap/verify-argocd-sync), OIDC+AROA, sha-rAttempt, concurrency semantics, cross-repo dispatch, jq -Rs SSM encoding
  - `wiki/concepts/infra-testing-strategy.md` — CDK testing pyramid (32 unit + 16 integration + 5 fixture); unit patterns (Template.fromStack, describe.each, negative assertions, it.todo, no-conditionals-in-test); integration patterns (SSM anchor, requireParam, beforeAll caching, satisfies, diagnostic formatters)
  - `wiki/tools/checkov.md` — IaC security scanning: .checkov/config.yaml architecture, security-scan.ts orchestration, 5 custom IAM checks (CKV_CUSTOM_IAM_1-5), 5 custom SG checks (CKV_CUSTOM_SG_1-5), policy-as-code model, severity gating, SARIF output
  - `wiki/concepts/aws-devops-certification-connections.md` — DOP-C02 domain-by-domain mapping to project implementations; SPIDER framework; exam-to-production gap table; narrative threads for future article
- Pages updated (5):
  - `wiki/tools/github-actions.md` — added concurrency semantics table, immutable image tags, AROA masking, TypeScript scripting layer summary, [[ci-cd-pipeline-architecture]] cross-reference
  - `wiki/concepts/shift-left-validation.md` — added CDK infrastructure testing tier section (Template.fromStack, describe.each, integration gates in deploy pipeline)
  - `wiki/projects/k8s-bootstrap-pipeline.md` — fixed cluster topology table (monitoring pool: t3.medium not t3.small; ArgoCD in monitoring; general = nextjs/start-admin/public-api/admin-api); added CDK testing pyramid summary; added CI/CD architecture and certification connections links
  - `index.md` — added ci-cd-pipeline-architecture, infra-testing-strategy, aws-devops-certification-connections entries; updated github-actions and checkov descriptions
  - `log.md` — this entry

## [2026-04-14] ingest | Networking, DR Fix, Deployment Testing & Worker Architecture v2
- Sources: `raw/cross-node-networking-troubleshooting.md`, `raw/deployment_testing_guide.md`, `raw/fix-missing-kube-proxy.md`, `raw/image-cloudfront-troubleshooting-guide.md`, `raw/implementation_plan.md`, `raw/kubernetes_networking_report.md`
- User corrections applied: both pools use `t3.medium` (not t3.small for monitoring); ArgoCD folds into monitoring pool (not general); general pool workloads = nextjs, start-admin, public-api, admin-api
- Key findings:
  - VXLANCrossSubnet fails on single-subnet AWS (all nodes same subnet → direct routing → VPC drops pod IPs); VXLANAlways required
  - DR gap: S3 restore recovers admin.conf before kubeadm init → second-run path skips kubeadm entirely → kube-proxy/CoreDNS never deployed → ClusterIP breaks → CCM taint stuck → cluster dead; fixed with ensure_kube_proxy() + ensure_coredns() idempotent guards
  - start-admin :latest tag never matched by Image Updater regexp → always degraded; fix = SHA-tagged image
  - Content-hash build alignment: container and S3 must come from same build; ArgoCD selfHeal reverts kubectl set image → use parameter override
  - Worker architecture v2: 3 named stacks → single KubernetesWorkerAsgStack; IAM 3→2 roles; CA auto-discovery tags; zero-downtime 4-phase migration; 6 script impact files identified
- Pages created (4):
  - `wiki/concepts/cluster-networking.md` — VPC topology, 4-tier SGs, NLB over ALB rationale, Calico VXLAN, SourceDestCheck, IPAM /26 blocks, end-to-end traffic flows (inbound + cross-node sequence diagrams)
  - `wiki/troubleshooting/cross-node-networking.md` — 10-step diagnostic (node status → encapsulation mode → routing tables → VXLAN packet capture → NetworkPolicy), VXLANCrossSubnet vs VXLANAlways root cause, live fix + persistent fix locations
  - `wiki/troubleshooting/kube-proxy-missing-after-dr.md` — failure chain diagram, ensure_kube_proxy + ensure_coredns implementations, 6 test cases, manual recovery steps
  - `wiki/troubleshooting/nextjs-image-asset-sync.md` — 4-parallel-track pipeline diagram, 7-step diagnostic, 6 issues with fixes, ArgoCD parameter override pattern
- Pages updated (9):
  - `wiki/concepts/self-hosted-kubernetes.md` — corrected cluster topology: both pools t3.medium, ArgoCD moved general → monitoring, general workloads = nextjs/start-admin/public-api/admin-api, KubernetesWorkerAsgStack v2 note
  - `wiki/tools/calico.md` — added VXLANAlways vs VXLANCrossSubnet section, SourceDestCheck requirement, /26 IPAM, route table signatures, TCP Meltdown explanation, persistent fix locations
  - `wiki/concepts/disaster-recovery.md` — expanded Bootstrap Token Repair with kube-proxy missing gap, ensure_kube_proxy/ensure_coredns guard integration, link to kube-proxy-missing-after-dr
  - `wiki/concepts/cdk-kubernetes-stacks.md` — added full KubernetesWorkerAsgStack v2 section: design table, pool instantiation code, CA tags, IAM consolidation, 4-phase migration, script impact table
  - `wiki/tools/argo-rollouts.md` — added Deployment Testing Workflow (4 phases, argo rollouts plugin commands, preview X-Preview testing), start-admin :latest tag bug section
  - `wiki/commands/kubectl-operations.md` — added BlueGreen Deployment Testing section, Traefik Connectivity Testing section, Networking Diagnostics section (VXLANAlways check, kube-proxy recovery)
  - `wiki/tools/github-actions.md` — added Frontend Deployment Pipeline section (4-parallel-track Mermaid diagram, build alignment invariant, ArgoCD parameter override)
  - `wiki/index.md` — added cluster-networking, cross-node-networking, kube-proxy-missing-after-dr, nextjs-image-asset-sync, kubectl-operations; updated calico/argo-rollouts/cdk-kubernetes-stacks/disaster-recovery/self-hosted-kubernetes descriptions

## [2026-04-16] ingest + new domain | kubernetes_infrastructure_audit_16_04.md → DORA metrics concept + Resume domain

### Source
- `raw/kubernetes_infrastructure_audit_16_04.md` — 587 lines: 10-stack CDK audit, DORA metrics reframed for solo developer, quantified achievements scorecard, 8-gap analysis, architecture maturity ratings, TSDoc annotation plan

### Key takeaways
- DORA baselines established: Lead Time ~30min, TTSR ~15min, CFR ~2%, Deployment Frequency on-demand via ArgoCD
- 10 quantified engineering achievements with exact numbers (600 lines eliminated, 75% boot reduction, 265+ assertions, 1:0.47 test ratio)
- 8 infrastructure gaps (G1–G8) with specific fix paths — G1 (no automated DORA collection) and G2 (no smoke tests) highest priority
- Architecture maturity ratings: IaC ⭐⭐⭐⭐⭐, CI/CD ⭐⭐⭐⭐⭐, GitOps ⭐⭐⭐⭐⭐, Security ⭐⭐⭐⭐½, Observability ⭐⭐⭐⭐½

### New domain: Resume
New `wiki/resume/` directory — translation layer: implementation facts → job-application language.

### Pages created
- `wiki/concepts/dora-metrics.md` — DORA framework reframed for solo dev; current baselines with evidence; metric tracking plan; G1–G8 gap inventory; architecture maturity ratings
- `wiki/resume/narrative.md` — 3-act unified story (Platform → Application → AI); positioning statement; competency map; role emphasis guide; honest framing section
- `wiki/resume/achievements.md` — quantified scorecard with wiki evidence links; DORA, infra scale, observability, AI stats; resume bullet templates per archetype
- `wiki/resume/concept-to-resume.md` — 6-domain mapping tables (Infrastructure, Kubernetes, CI/CD, Observability, Security, AI Engineering); honesty boundaries per claim
- `wiki/resume/gap-awareness.md` — context boundaries table; G1–G8 infra gaps; security gaps (SH-S1/S2/S5/S6); AI engineering gaps; what was NOT built list; what's unusual list
- `wiki/resume/role-archetypes.md` — 5 archetypes with lead bullets, evidence pages, sample bullets, gap acknowledgement notes; archetype selector by JD signal

### Files updated
- `CLAUDE.md` — added `resume/` to wiki directory schema; added Operation 5 (Resume) rules with 6 mandatory steps
- `wiki/index.md` — added dora-metrics to Concepts; added Resume section with 5 entries; updated date to 2026-04-16

## [2026-04-16] correction + new pages | raw/resume-domain.md comparison → Resume domain fixes

### Source
- `raw/resume-domain.md` — v1.0 generated from live codebase scan; supersedes audit-derived claims in wiki/resume/*

### Corrections applied (audit was wrong, codebase scan is authoritative)

| File | What changed |
|---|---|
| `wiki/resume/gap-awareness.md` | G5 (PodDisruptionBudgets) marked RESOLVED — PDBs implemented in monitoring values.yaml. G6 downgraded to PARTIAL — NetworkPolicies exist for admin-api and monitoring but no cluster-wide default-deny. Added critical "service mesh" boundary (NEVER use phrase). Added formal SLOs boundary. Added GCP/large-scale/Commander.js absent boundaries. |
| `wiki/resume/achievements.md` | ArgoCD app count corrected 9 → 20+. Added 4 AWS accounts row. Added 4 Bedrock applications row (job-strategist was missing). GitHub Actions workflows corrected 26 → 22+. Sources updated to include raw/resume-domain.md. |
| `wiki/resume/narrative.md` | Added Support-to-DevOps transition narrative section. Corrected competency table: 4 accounts, 22+ workflows, 20+ ArgoCD apps. Sources updated. |

### Pages created
- `wiki/resume/agent-guide.md` — **direct path for AI agents**: confidence threshold table, step-by-step instructions for summary/bullets/cover letter, JD signal → narrative quick-map, 10 hard rules (no "service mesh", no SLA claims, no Terraform claims, etc.)
- `wiki/resume/concept-library.md` — STRONG/PARTIAL/ABSENT status per concept with actual evidence file paths from codebase scan; recommended_framing per concept; absent concepts table

### Files updated
- `wiki/index.md` — Resume section updated: agent-guide and concept-library added as first two entries (START HERE ordering)

## [2026-04-16] ingest | strategist_pipeline_design_review_16_04.md → Job Strategist wiki page

### Source
- `raw/strategist_pipeline_design_review_16_04.md` — Architecture & Security Audit of `bedrock-applications/job-strategist/` + `infra/lib/stacks/bedrock/`

### Key findings
- No Critical findings — pipeline is functional and deployable
- H3 (P0): `ASSETS_BUCKET` missing from Trigger Lambda CDK environment — silent 256KB breach on real inputs
- H1: 4 of 6 handlers use `process.env.VAR ?? ''` (silent fallback) instead of Zod fail-fast
- H2: No Bedrock retry logic — ThrottlingException/503 causes full pipeline failure
- M5: KB deduplication uses full passage string (including score prefix) — near-duplicate passages not filtered
- I2: 3 KB queries run sequentially — parallelising with Promise.all() saves ~30–40% research latency

### KB integration gap identified
- Research Agent queries portfolio KB 3× via RetrieveCommand (RAG/semantic retrieval)
- Resume domain pages (agent-guide, gap-awareness, concept-library) contain mandatory constraints — NEVER retrieved when not semantically similar to JD query
- Design changes needed: dedicated resume-domain queries, direct injection of hard rules into system prompt

### Pages created
- `wiki/ai-engineering/job-strategist.md` — full architecture, strengths table (S1-S8), H1-H3 findings, M1-M6 table, actual DynamoDB entity schema (vs wrong JSDoc), prompt engineering assessment, KB integration gap analysis, remediation priority matrix

### Files updated
- `wiki/index.md` — added job-strategist to AI Engineering section

## [2026-04-16] ingest | aws_support_career_review_2026.md → Career history + Voice library

### Source
- `raw/aws_support_career_review_2026.md` — sanitised annual review; omitted: manager name, internal tool/process acronyms (PAA/MAC), performance plan details; retained: accomplishments, certifications, education, management endorsement, authentic voice samples

### Additional content added (not in source document)
- 3 years HTML/CSS/JS internal wiki documentation across multiple AWS teams
- Case distribution automation project: architecture design, problem statement (10–20 hrs/week), technical design (Dante Scripts), business case status (pending security approval + SXO sponsorship)

### Key decisions
- Internal Amazon terms translated: "PAA Champion" → "service continuity lead", "Kiro SME" → "technical tooling SME", case types omitted
- Performance plan history omitted entirely — outcome ("Meets High Bar") retained
- Leadership Principles evidence retained with non-Amazon translation table
- Automation project framed as IN_PROGRESS — "designed" not "built"

### Pages created
- `raw/aws_support_career_review_2026.md` — sanitised source with resume-ready framing, authentic voice samples, LP translation table
- `wiki/resume/career-history.md` — Amazon TCSA work history in ATS-ready format; role context for transition narrative; automation project IN_PROGRESS framing; certifications; LP→universal translation
- `wiki/resume/voice-library.md` — authentic phrase anchors (Nelson's own writing), tone profile, sentence-length variation rules, banned AI terms, good verbs, cover letter voice guidelines, ATS keyword strategy, anti-AI-scan checklist

### Pages updated
- `wiki/resume/narrative.md` — Support-to-DevOps section enriched with concrete Amazon evidence (role, cert, degree, management endorsement, documentation work, automation project)
- `wiki/resume/achievements.md` — added Amazon Work History Accomplishments table + ATS bullet templates
- `wiki/resume/agent-guide.md` — added ATS Optimization Rules section, Human-Written Output Rules section; voice-library and career-history added to related pages
- `wiki/index.md` — Resume section updated with career-history and voice-library entries; agent-guide description updated to mention ATS/human-writing rules

## [2026-04-16] implement | wiki-mcp FastMCP K8s pod

### Operation
Designed and implemented wiki-mcp: FastMCP HTTP server that exposes the knowledge base as MCP tools, deployable as a Kubernetes pod on the existing cluster.

### Architecture
- FastMCP v2 streamable-http transport on port 8000
- Starlette ASGI composition: `/healthz` (K8s probes) + `/mcp` (FastMCP endpoint)
- S3 `kb-docs/` content source with 10-min in-memory TTL cache
- EC2 instance profile credentials (IMDS) — same as admin-api, zero K8s secrets
- Traefik IngressRoute: `ops.nelsonlamounier.com/wiki-mcp` → StripPrefix + BasicAuth → ClusterIP:80 → pod:8000
- Lambda traffic path: non-VPC Lambda → public HTTPS → Traefik → wiki-mcp pod → S3

### Tools exposed (7)
- `get_page(path)` — fetch any wiki page by path
- `get_resume_constraints()` — combined agent-guide + gap-awareness + voice-library
- `get_career_history()` — Amazon work history
- `get_achievements()` — quantified scorecard
- `search(query, category)` — keyword search with path + content matching
- `list_pages(category)` — list available pages
- `get_index()` — full wiki index

### Files created
- `scripts/wiki_mcp/__init__.py` — package init
- `scripts/wiki_mcp/kb.py` — S3 content reader with TTL cache
- `scripts/wiki_mcp/server.py` — FastMCP server with 7 tools + ASGI composition
- `scripts/wiki_mcp/Dockerfile` — 3-stage Python 3.12-slim build, non-root uid 1001
- `kubernetes-app/workloads/charts/wiki-mcp/chart/` — Helm chart (Chart.yaml, values.yaml, 4 templates)
- `kubernetes-app/workloads/argocd-apps/wiki-mcp.yaml` — ArgoCD app (wave 5, Image Updater)

### Files updated
- `scripts/requirements.txt` — added fastmcp>=2.13.0, uvicorn[standard], starlette
- `scripts/sync-wiki.py` — added index.md upload to kb-docs/ prefix

### Pending (one-time setup before first sync)
1. `kubectl create namespace wiki-mcp`
2. Create `wiki-mcp-basicauth` K8s Secret (htpasswd format)
3. Create `wiki-mcp-config` ConfigMap with `WIKI_S3_BUCKET`
4. Store BasicAuth header in SSM `/wiki-mcp/basicauth-header`
5. CDK change: add S3 read policy to worker node IAM role for kb-docs/*
6. Create ECR repo `wiki-mcp`, build + push initial image
