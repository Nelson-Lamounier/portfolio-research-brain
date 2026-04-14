---
title: Wiki Log
type: log
---

# Knowledge Base Log

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
