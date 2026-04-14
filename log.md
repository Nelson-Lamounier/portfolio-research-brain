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
