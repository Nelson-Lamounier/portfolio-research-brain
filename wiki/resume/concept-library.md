---
title: Concept Library
type: resume
tags: [resume, concepts, evidence, framing, status, devops, kubernetes, ai-engineering]
sources: [raw/resume-domain.md]
created: 2026-04-16
updated: 2026-04-16
---

# Concept Library

Per-concept status, evidence file paths, and recommended framing. Use this alongside [[agent-guide]] for resume generation. When a concept is STRONG, claim it. When PARTIAL, use `recommended_framing` only.

---

## Container Orchestration & Kubernetes

### Self-healing infrastructure
**Status: STRONG**

Evidence:
- `kubernetes-app/workloads/argocd-apps/nextjs.yaml` — ArgoCD Application with `syncPolicy.automated.selfHeal=true` and `prune=true`
- `kubernetes-app/platform/argocd-apps/monitoring.yaml` — Platform monitoring with identical self-heal config
- `infra/lib/stacks/kubernetes/control-plane-stack.ts` — ASG min=1/max=1 provides instance-level self-healing
- `kubernetes-app/k8s-bootstrap/boot/steps/wk/verify_membership.py` — Worker re-join logic

Recommended framing:
> "Deployed self-healing Kubernetes workloads via ArgoCD GitOps — automatic drift correction against Git, ASG-backed instance recovery, and automated worker re-join. Zero manual cluster access required for recovery."

---

### Microservices / namespace isolation
**Status: STRONG**

Evidence:
- `kubernetes-app/workloads/argocd-apps/nextjs.yaml` — nextjs-app namespace
- `kubernetes-app/workloads/argocd-apps/start-admin.yaml` — start-admin namespace
- `kubernetes-app/workloads/argocd-apps/admin-api.yaml` — admin-api namespace
- `kubernetes-app/workloads/argocd-apps/public-api.yaml` — public-api namespace
- `kubernetes-app/platform/charts/monitoring/chart/values.yaml` — monitoring namespace with ResourceQuota and NetworkPolicy
- `kubernetes-app/workloads/charts/admin-api/chart/templates/networkpolicy.yaml` — admin-api NetworkPolicy
- `kubernetes-app/platform/charts/monitoring/chart/templates/network-policy.yaml` — monitoring NetworkPolicy

Recommended framing:
> "Architected namespace-isolated microservices topology with per-namespace NetworkPolicies and ResourceQuotas — independent deployability and blast radius containment across 6+ service boundaries."

---

### Kubernetes internals (kubeadm / control plane)
**Status: STRONG**

Evidence:
- `infra/lib/stacks/kubernetes/control-plane-stack.ts` — kubeadm control plane stack with LaunchTemplate, ASG, UserData, Calico CNI
- `kubernetes-app/k8s-bootstrap/boot/steps/cp/kubeadm_init.py` — kubeadm init bootstrap step
- `kubernetes-app/k8s-bootstrap/boot/steps/cp/dr_restore.py` — etcd DR restore from S3
- `kubernetes-app/k8s-bootstrap/boot/verify-cluster.sh` — control plane verification

Differentiator note: self-hosted kubeadm exposes control plane internals (etcd, kube-apiserver, CNI, kubelet) that EKS/GKE abstract away. Surface prominently when JD requires Kubernetes troubleshooting depth.

Recommended framing:
> "Self-hosted Kubernetes via kubeadm — hands-on control plane internals (etcd lifecycle, kube-apiserver, Calico CNI, kubelet configuration), automated DR restore from S3-backed etcd snapshots, and node-level operations that managed services abstract away."

---

### Service mesh
**Status: PARTIAL**

Evidence:
- `kubernetes-app/platform/argocd-apps/traefik.yaml` — Traefik v3 ingress controller
- `kubernetes-app/platform/charts/monitoring/chart/templates/traefik/basicauth-middleware.yaml`
- `kubernetes-app/platform/charts/monitoring/chart/templates/traefik/ip-allowlist-middleware.yaml`
- `kubernetes-app/platform/charts/monitoring/chart/templates/traefik/rate-limit-middleware.yaml`

**Honest boundary (CRITICAL):** Traefik v3 = L7 ingress + middleware chains. NOT a service mesh. No mTLS between pods. No circuit breaking, retries, or sidecar-based traffic policies (Istio/Linkerd). **Agents MUST NEVER use the phrase "service mesh" for this project.**

Recommended framing:
> "Traefik v3 for ingress routing, cross-namespace traffic management, and middleware-based auth enforcement (BasicAuth, IP allowlisting, rate limiting) — L7 routing without a full service mesh."

---

### Cluster autoscaling
**Status: STRONG**

Evidence:
- `infra/lib/stacks/kubernetes/worker-asg-stack.ts` — generic parameterised worker ASG with Cluster Autoscaler discovery tags, Spot instances
- `kubernetes-app/platform/argocd-apps/cluster-autoscaler.yaml` — CA deployed via ArgoCD
- `kubernetes-app/platform/charts/monitoring/chart/values.yaml` — PodDisruptionBudgets for Prometheus, Grafana, Loki protecting against CA scale-down

Pool configuration: general (t3.small Spot, 1–4 nodes), monitoring (t3.medium Spot, 1–2 nodes)

Recommended framing:
> "Implemented ASG-backed Kubernetes auto-scaling with Cluster Autoscaler — dual worker pools (general/monitoring) on Spot instances with PodDisruptionBudgets protecting critical observability workloads."

---

## GitOps & Delivery

### GitOps delivery model (ArgoCD)
**Status: STRONG**

Evidence:
- `kubernetes-app/k8s-bootstrap/system/argocd/platform-root-app.yaml` — App-of-Apps root Application, platform tier
- `kubernetes-app/k8s-bootstrap/system/argocd/workloads-root-app.yaml` — App-of-Apps root Application, workloads tier
- `kubernetes-app/platform/argocd-apps/` — 15+ platform ArgoCD Applications: monitoring, traefik, cert-manager, cluster-autoscaler, crossplane, metrics-server, argocd-image-updater, opencost, descheduler, argo-rollouts, etc.
- `kubernetes-app/workloads/argocd-apps/` — 5 workload Applications: nextjs, start-admin, admin-api, public-api, golden-path-service

Scale: **20+ applications** managed declaratively. This is the canonical count — use this, not "5 + 4".

Recommended framing:
> "Implemented GitOps delivery via ArgoCD App-of-Apps — 20+ applications with automated sync, self-heal, and image tag promotion from ECR, eliminating direct cluster access as a deployment mechanism."

---

### Separated CI/CD pipeline design
**Status: STRONG**

Evidence:
- `.github/workflows/ci.yml` — CI pipeline: change detection, security audit, ESLint, TypeScript, CDK synth, Checkov, Helm validation, Python tests; runs on custom Docker CI image
- `.github/workflows/deploy-kubernetes.yml` — CD for K8s infra
- `.github/workflows/gitops-k8s.yml` — CD for K8s workloads via ArgoCD
- `.github/workflows/deploy-bedrock.yml` — CD for Bedrock AI stacks
- `.github/workflows/deploy-frontend.yml` — CD for frontend Docker build + ECR push

Design rationale: CI runs on every commit; CD on merge to main/develop only. Reduces per-commit pipeline time.

Scale: **22+ workflow files** (not 26 — use 22+).

Recommended framing:
> "Architected separated CI/CD across 22+ GitHub Actions workflows — change-detection-driven quality gates, Checkov IaC security scanning, and custom Docker CI images for reproducible builds."

---

## Observability

### Three-pillar observability
**Status: STRONG**

Evidence:
- Metrics: `kubernetes-app/platform/charts/monitoring/chart/templates/prometheus/` — Prometheus v3.3.0, 15-day retention, EBS PVC, PDB
- Metrics: `kubernetes-app/platform/charts/monitoring/chart/templates/node-exporter/` — Node Exporter v1.9.1 DaemonSet
- Metrics: `kubernetes-app/platform/charts/monitoring/chart/templates/github-actions-exporter/` — CI/CD pipeline metrics
- Logs: `kubernetes-app/platform/charts/monitoring/chart/templates/loki/` — Loki v3.5.0
- Logs: `kubernetes-app/platform/charts/monitoring/chart/templates/promtail/` — Promtail DaemonSet
- Traces: `kubernetes-app/platform/charts/monitoring/chart/templates/tempo/` — Tempo v2.7.2 with OTLP gRPC/HTTP
- RUM: `kubernetes-app/platform/charts/monitoring/chart/templates/alloy/` — Grafana Alloy v1.8.2 as Faro collector
- Compliance: `kubernetes-app/platform/charts/monitoring/chart/templates/steampipe/` — Steampipe in-cluster AWS compliance scanning

Recommended framing:
> "Deployed three-pillar observability (Prometheus, Loki, Tempo) with Grafana dashboards, Faro RUM collection via Alloy, and Steampipe compliance scanning — covering infrastructure, application, and CI/CD telemetry."

---

### SLO / alerting design
**Status: PARTIAL**

Evidence:
- `kubernetes-app/platform/charts/monitoring/chart/values.yaml` — Grafana alerting with SNS topic ARN
- `infra/lib/stacks/kubernetes/worker-asg-stack.ts` — SNS Topic for monitoring alerts

**Honest boundary:** Grafana alerting and SNS topics are configured but formal SLO definitions (error budgets, burn-rate alerts, recording rules) are NOT defined. Alerting is threshold-based.

Recommended framing:
> "Configured Grafana alerting with SNS notification integration and PodDisruptionBudgets for monitoring resilience — threshold-based alerts covering pod health, node status, and pipeline failures."

---

## Infrastructure as Code

### AWS CDK TypeScript (multi-account)
**Status: STRONG**

Evidence:
- `infra/lib/config/environments.ts` — 4 AWS accounts: development (771826808455), staging (692738841103), production (607700977986), management (711387127421). Cross-region: eu-west-1 primary, us-east-1 edge.
- `infra/lib/stacks/kubernetes/` — 5+ K8s stacks: base, control-plane, worker-asg, edge, golden-ami
- `infra/lib/stacks/bedrock/` — 4+ Bedrock stacks
- `infra/lib/stacks/shared/` — VPC, ECR, Cognito
- `infra/lib/stacks/org/dns-role-stack.ts` — cross-account DNS validation role

Recommended framing:
> "Managed all AWS infrastructure through CDK TypeScript across 4 accounts (dev/staging/prod/management) — zero console-deployed resources, cross-region stacks, and cross-account IAM roles for DNS validation and CI/CD."

---

## Security & Secrets Management

### Zero-trust / OIDC federation
**Status: STRONG**

Evidence:
- `.github/workflows/deploy-kubernetes.yml` — `permissions.id-token: write` for GitHub OIDC
- `infra/lib/stacks/org/dns-role-stack.ts` — cross-account IAM role with trust policy
- `infra/lib/stacks/kubernetes/control-plane-stack.ts` — scoped IAM with condition keys (kms:ViaService, iam:PassedToService), SSM SecureString
- `infra/lib/stacks/kubernetes/edge-stack.ts` — CloudFront origin secret as SSM SecureString with zero-downtime rotation

**Honest boundary:** Some IAM policies use wildcard resources (ec2:Describe* for CCM, kms:Decrypt for SSM) due to AWS API limitations. Not a full zero-trust network architecture — no mTLS between pods.

Recommended framing:
> "Implemented OIDC-federated CI/CD with GitHub Actions — zero long-lived credentials, cross-account IAM roles with condition-scoped policies, SSM SecureString secrets management, and documented zero-downtime secret rotation."

---

## AI / ML Integration

### AWS Bedrock AI pipeline integration
**Status: STRONG**

Evidence:
- `infra/lib/stacks/bedrock/pipeline-stack.ts` — article pipeline: S3 trigger → Research (Haiku) → Writer (Sonnet) → QA (Sonnet), Application Inference Profiles for cost tracking
- `bedrock-applications/article-pipeline/` — article generation pipeline
- `bedrock-applications/job-strategist/` — job strategy pipeline
- `bedrock-applications/chatbot/` — Bedrock chatbot with Knowledge Base RAG
- `bedrock-applications/self-healing/` — self-healing agent (diagnose CloudWatch alarms, tool-use)
- `kubernetes-app/platform/charts/monitoring/chart/dashboards/self-healing.json` — Grafana monitoring dashboard for agent

Scale: **4 Bedrock applications** (not 3 — job-strategist is the 4th).

Differentiator: most infrastructure candidates have zero production-pattern AI experience. Surface prominently for any JD mentioning AI tooling or automation.

Recommended framing:
> "Built multi-agent AI pipelines on AWS Bedrock — 4 applications (article generation, job strategy, chatbot with RAG, self-healing agent) using Step Functions orchestration, tool-use patterns, and per-agent cost tracking via Application Inference Profiles."

---

## Developer Tooling

### justfile task runner
**Status: STRONG**

Evidence:
- `justfile` — CI pipeline uses just recipes for all operations (just audit, lint, typecheck, build, deps-check-ci, test-stacks, ci-synth-validate, helm-validate-charts, bootstrap-pytest, ci-security-scan)
- `.github/workflows/ci.yml` — all CI steps execute through justfile recipes
- `packages/script-utils/` — `@repo/script-utils` shared utilities package
- `infra/scripts/cd/sync-bootstrap-scripts.ts` — TypeScript deployment scripts with OIDC auth mode detection
- `frontend-ops/push-to-ecr.ts` / `frontend-ops/sync-static-to-s3.ts` — TypeScript operational scripts

Recommended framing:
> "Implemented justfile task runner aligning all local and CI operations — 15+ recipes ensuring dev/CI parity, with TypeScript deployment scripts and a shared utilities package for cross-environment automation."

---

## Absent Concepts — Do Not Claim

| Concept | Safe alternative framing |
|---|---|
| Service mesh (Istio/Linkerd) | "Traefik v3 ingress and cross-namespace routing" |
| GCP / GKE | "AWS-native, Kubernetes skills transferable" |
| Terraform / HCL | "AWS CDK TypeScript (equivalent IaC capability)" |
| Fine-tuning / RLHF | "AWS Bedrock API — managed inference, no model training" |
| EKS / GKE / AKS | "Evaluated managed K8s, chose kubeadm for full-stack learning depth" |
| Multi-region active-active | "Single-region (eu-west-1) with CloudFront edge in us-east-1" |
| Formal SLOs / error budgets | "Threshold-based alerting with SNS notifications" |
| Commander.js CLI | "justfile task runner with TypeScript deployment scripts" |
| Enterprise-scale clusters | "Self-hosted dual-pool cluster with Cluster Autoscaler" |
| Large-team CI/CD governance | "Solo-maintained CI/CD pipeline — 22+ workflows" |

---

## Related Pages

- [[agent-guide]] — how to USE this library for resume generation
- [[achievements]] — quantified scorecard with evidence links
- [[gap-awareness]] — full gap inventory and honest boundaries
- [[concept-to-resume]] — implementation detail → job language mappings
- [[role-archetypes]] — per-role emphasis
