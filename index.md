---
title: Wiki Index
type: index
updated: 2026-04-14
---

# Knowledge Base Index

## Projects

- [[projects/k8s-bootstrap-pipeline]] — CDK-managed self-hosted Kubernetes bootstrap pipeline on EC2 with Step Functions, SSM, and full cluster topology for `nelsonlamounier.com`
- [[projects/frontend-portfolio]] — Yarn 4 monorepo: Next.js 15 public site (`apps/site`) + TanStack Start admin dashboard (`apps/start-admin`); OTel traces, prom-client metrics, Faro RUM, Cognito PKCE auth, 4-stage Docker builds

## Concepts

- [[concepts/self-hosted-kubernetes]] — kubeadm on EC2: cluster topology (both pools t3.medium), KubernetesWorkerAsgStack v2, bootstrap steps, CA mismatch, stale PV cleanup
- [[concepts/cluster-networking]] — VPC topology (single AZ), 4-tier Security Groups, NLB over ALB, Calico VXLAN/VXLANAlways, SourceDestCheck, /26 IPAM, end-to-end traffic flows
- [[concepts/shift-left-validation]] — local-first testing philosophy: unit tests (5s) → dry-run (30s) → SSM trigger (1min) → CI pipeline (10min); CDK testing tier
- [[concepts/self-healing-agent]] — Reactive Autonomous Agent: CloudWatch Alarm → EventBridge → Lambda ConverseCommand+tool_use loop → 6 MCP tools (AgentCore, Cognito M2M) → S3 episodic memory → SNS; hybrid prompt design; see ai-engineering/self-healing-agent for LLM depth
- [[concepts/observability-stack]] — LGTM + Promtail DaemonSet + Alloy Faro/RUM + 13 GitOps dashboards; 12-job Prometheus scrape inventory; Tempo span-metrics for DynamoDB; Grafana alerting via SNS; prom-client app metrics + Faro /log-proxy rewrite; known limitations (single-AZ, Spot, Faro CORS)
- [[concepts/notification-architecture]] — three notification planes (Grafana→SNS, CloudWatch→SNS, ArgoCD→GitHub); 5 SNS topics; 12 Grafana alert rules (A→B→C evaluation, traces_spanmetrics DynamoDB, Span Ingestion Stopped meta-alert); SSM→Helm wiring chain; ArgoCD GitHub App commit status; 3 gaps fixed
- [[concepts/disaster-recovery]] — etcd + PKI backup to S3, TLS and JWT to SSM, _reconstruct_control_plane DR path, RTO ~5–8 min; kube-proxy/CoreDNS addon guards on second-run path
- [[concepts/cdk-kubernetes-stacks]] — full 10-stack CDK catalogue with deployment order, lifecycle separation, config-driven SG pattern, KubernetesWorkerAsgStack v2 (3→2 stacks, CA tags, zero-downtime migration)
- [[concepts/ci-cd-pipeline-architecture]] — 26-workflow monorepo CI/CD: reusable workflow library, TypeScript CI/CD scripting layer (pipeline-setup/synthesize/security-scan/finalize), OIDC+AROA masking, sha-rAttempt image tags, concurrency semantics, cross-repo dispatch
- [[concepts/operational-scripts]] — scripts/local/ diagnostic suite: control-plane-troubleshoot.ts (4-phase, 1737 lines), ssm-automation.ts (dual CWL/API log retrieval), asg-audit.ts (orphan detection), control-plane-autofix.ts (3 runbooks); shared lib (resolveAuth, logger.ts monkey-patch); kb-drift-check.py
- [[concepts/infra-testing-strategy]] — CDK testing pyramid: 32 unit tests (Template.fromStack, describe.each, negative assertions) + 16 integration tests (SSM anchor, requireParam, beforeAll caching); diagnostic-first failure messages
- [[concepts/aws-devops-certification-connections]] — DOP-C02 exam domains mapped to real project implementations: Blue/Green↔ArgoRollouts, IaC↔CDK10Stack, DR↔etcd+kubeproxy, Monitoring↔LGTM, Security↔Checkov+OIDC+AROA; SPIDER framework; narrative threads for future article

## Tools

- [[tools/nextjs]] — Next.js 15 App Router: `output: 'standalone'`, 7 API routes, prom-client metrics, OTel `instrumentation.ts` hook, Faro `/log-proxy` rewrite, 4-stage Docker build, 5 security gaps
- [[tools/tanstack-start]] — TanStack Start (Vinxi/Vite): `createServerFn` type-safe RPC, 12 server modules, Cognito PKCE auth, full CSP, Vitest testing, 4-stage Docker build
- [[tools/aws-bedrock]] — ConverseCommand vs InvokeAgentCommand; Extended Thinking API; KB RetrieveCommand + Pinecone; Application Inference Profiles (FinOps); Guardrails (content filters, topic denial, grounding); prompt caching; runAgent() utility; EMF metrics
- [[tools/aws-step-functions]] — orchestration engine for SM-A/SM-B; 3600s timeout story; Node Drift Enforcement; ResourceCleanupProvider
- [[tools/aws-ssm]] — remote execution layer: Run Command, Session Manager, 14-param BaseStack outputs, DR SecureStrings
- [[tools/aws-cloudfront]] — CloudFront + WAF + ACM edge stack: TLS model, X-Origin-Verify, cross-region SSM read pattern
- [[tools/aws-ebs-csi]] — EBS CSI Driver: controller/node topology, ebs-sc StorageClass, WaitForFirstConsumer, local-path migration
- [[tools/ec2-image-builder]] — Golden AMI pipeline: pre-baked K8s toolchain, bootstrap time from 15 min → 2–3 min
- [[tools/calico]] — Calico CNI via Tigera operator: pod networking, VXLANAlways encapsulation (VXLANCrossSubnet fails on single-subnet AWS), SourceDestCheck, /26 IPAM, NetworkPolicy dual-ipBlock for hostNetwork
- [[tools/aws-ccm]] — AWS Cloud Controller Manager: removes cloud provider taint to unblock pod scheduling
- [[tools/argocd]] — GitOps controller: 7-wave sync map, ApplicationSet, multi-source Apps, bootstrap sequence
- [[tools/traefik]] — DaemonSet + hostNetwork ingress: IngressRoute ownership boundary, secret rotation, priority cascade
- [[tools/argo-rollouts]] — Blue/Green: scalar() analysis fix, HPA targeting Rollout, ResourceQuota formula, deployment testing workflow, start-admin :latest tag bug
- [[tools/crossplane]] — Kubernetes-native IDP: EncryptedBucket/MonitoredQueue XRDs, golden-path service provisioning
- [[tools/steampipe]] — Cloud inventory SQL FDW in monitoring namespace: Grafana datasource, cloud-inventory dashboard, exec queries, SQL pitfalls
- [[tools/promtail]] — Log shipping DaemonSet: kubernetes-pods + journal scrape jobs, CRI parsing, Loki push, Loki→Tempo TraceID derived fields
- [[tools/hono]] — Hono/Node.js API services: public-api (port 3001) and admin-api (port 3002) with IMDS credentials
- [[tools/github-actions]] — CI/CD with OIDC+AROA masking, custom Docker CI image, path-scoped monorepo triggers, TypeScript scripting layer, immutable sha-rAttempt image tags
- [[tools/checkov]] — IaC security scanning: 10 custom rules (5 IAM + 5 SG), policy-as-code model, severity gating (CRITICAL/HIGH block; MEDIUM/LOW non-blocking), SARIF output
- [[tools/just]] — task runner: stable CLI contract for 6 recipe groups (cdk/ci/test/k8s/ops/infra); why just > npm/Make; CI integration pattern; ops group invokes TypeScript diagnostics

## Patterns

- [[patterns/event-driven-orchestration]] — SM-A SUCCEED → EventBridge → SM-B auto-fires: self-healing config injection
- [[patterns/poll-loop-pattern]] — custom Step Functions poll loop for SSM Run Command completion (no native waiter exists)
- [[patterns/bff-pattern]] — Backend-for-Frontend: start-admin `createServerFn` calls admin-api pod-to-pod; browser never crosses origin to admin-api

## Troubleshooting

- [[troubleshooting/ssm-permission-denied]] — EACCES on /data/app-deploy/ from ssm-shell: root cause (root:root 755) and two-layer fix (group-write + root session)
- [[troubleshooting/prometheus-scrape-targets]] — 6 real scrape failures (relabel bug, 404s, redirect loop, missing jobs, replicas:0); sub-path prefix reference table; ephemeral curl pod diagnostics
- [[troubleshooting/cross-node-networking]] — 10-step Calico diagnostic: VXLANCrossSubnet vs VXLANAlways root cause, routing table patterns, VXLAN packet capture, NetworkPolicy testing
- [[troubleshooting/kube-proxy-missing-after-dr]] — DR gap: S3 restore skips kubeadm init → kube-proxy/CoreDNS never deployed → ClusterIP broken; ensure_kube_proxy + ensure_coredns guards; manual recovery
- [[troubleshooting/control-plane-cert-san-mismatch]] — post-ASG replacement cert SAN mismatch (old IPs in restored backup cert); diagnosis (just diagnose Phase 3); automated repair (just fix-cert / control-plane-autofix.ts); Bash emergency fallback
- [[troubleshooting/nextjs-image-asset-sync]] — content-hash build alignment, 6 issues (404s, Image Updater IAM, self-heal reverts, start-admin :latest bug, CloudFront invalidation, IfNotPresent); ArgoCD parameter override pattern

## Commands

- [[commands/k8s-bootstrap-commands]] — complete command reference: just recipes, AWS CLI, SSM debugging, CDK operations
- [[commands/kubectl-operations]] — day-2 operations: get/describe/exec/rollout/logs, BlueGreen testing, Traefik connectivity, networking diagnostics, ArgoCD workflow, JSONPath reference

## AI Engineering

- [[ai-engineering/article-pipeline]] — Deterministic Workflow Agent: 3-Lambda (Research/Haiku → Writer/Sonnet → QA/Sonnet) + Step Functions; ConverseCommand; adaptive Extended Thinking; DynamoDB single-table; 19 gaps (S/C/P/R); prompt caching; KB RetrieveCommand
- [[ai-engineering/inference-time-techniques]] — 11 techniques assessed against article pipeline: Extended Thinking ✅, Adaptive Compute ✅, CoT ⚠️, Self-Consistency ❌ (Gap R4), Sequential Revision ⚠️ (Gap R5 HIGH), Search+Verifier ✅, ToT 🚫, SFT/RL 🚫
- [[ai-engineering/chatbot]] — RAG-Grounded Conversational Agent: InvokeAgentCommand + Guardrails (content filters + grounding 0.7) + 6-layer defence-in-depth Lambda; 20 gaps (S/C/P/A); review based on KB prior to LLM Wiki migration
- [[ai-engineering/rag-techniques]] — RAG technique inventory for chatbot: 12 techniques (A–L), A8 (no eval pipeline, HIGH) most critical; migration impact column shows which gaps worsen/improve with LLM Wiki as KB source
- [[ai-engineering/self-healing-agent]] — Reactive Autonomous Agent: ConverseCommand + tool_use loop, 6 MCP tools via AgentCore, Cognito M2M, S3 episodic memory, hybrid prompt design, 15 gaps (4× HIGH security + SH-R4/R5)

## Comparisons

- [[comparisons/llm-wiki-vs-bedrock-pipeline]] — LLM Wiki vs Bedrock article pipeline: where each excels, hybrid architecture proposal, 3-phase migration plan
