---
title: Gap Awareness
type: resume
tags: [resume, gaps, honesty, boundaries, devops, ai-engineering]
sources: [raw/kubernetes_infrastructure_audit_16_04.md, raw/resume-domain.md, raw/self_healing_design_review.md, raw/chatbot_system_design_review.md, raw/article_pipeline_design_review.md]
created: 2026-04-16
updated: 2026-04-17
authority: raw/resume-domain.md supersedes audit-derived entries — codebase scan wins over assumptions
---

# Gap Awareness

What is NOT in the portfolio and why. AI agents must read this before generating resume content. Overclaiming on any of these points risks rejection or failed technical screens.

## Context Boundaries

These are real implementations with real code, tests, and infrastructure. But the operational context differs from enterprise environments:

| Context Factor | Portfolio Reality | Enterprise Expectation | Honest Framing |
|---|---|---|---|
| Traffic | ~100 daily visitors | Thousands–millions RPS | "Portfolio-scale" |
| Team size | Solo | 5–50+ engineers | "Solo-built" or "independently designed and implemented" |
| SLA | Best-effort | 99.9%+ with SLA | Do NOT claim SLA compliance |
| On-call | No formal on-call | 24/7 rotation | Do NOT claim on-call experience |
| Incident response | Self-directed | Stakeholder-facing postmortems | "Solo incident response" |
| Budget | Personal AWS account | Corporate FinOps governance | "Cost-optimised" not "FinOps at scale" |

## Infrastructure Gaps (G1–G8 from Audit)

| Gap | What's Missing | Risk if Claimed | Fix Path |
|---|---|---|---|
| **G1** | Automated DORA metric collection | DORA numbers are estimates, not dashboards | Add CloudWatch custom metrics step |
| **G2** | Post-deploy smoke tests | CDK tests don't verify live cluster health | `kubectl get nodes` + `/healthz` job |
| G3 | Backup restoration tests | etcd/S3 backups unverified for restorability | Monthly restore workflow |
| G4 | Cost anomaly alerts | No proactive cost protection | CloudWatch Billing alarm |
| ~~G5~~ | ~~PodDisruptionBudgets~~ | **RESOLVED — PDBs implemented** in `kubernetes-app/platform/charts/monitoring/chart/values.yaml` for Prometheus, Grafana, and Loki. Not a gap. | — |
| G6 | NetworkPolicy enforcement (partial) | Calico deployed; NetworkPolicies exist for `admin-api` and `monitoring` namespaces but **no cluster-wide default-deny**. Partial, not absent. | Add default-deny NetworkPolicies to remaining namespaces |
| G7 | Observability ASG name alignment | CloudWatch dashboard may show "Insufficient Data" | Update legacy ASG name refs |
| G8 | AppIamStack dummy role | CDK diff noise on first synth | Add `Condition` guard |

## Security Gaps

From [[ai-engineering/self-healing-agent]]:

| Gap | Risk |
|---|---|
| SH-S1: System prompt in Lambda env var | Readable by anyone with `lambda:GetFunction` |
| SH-S2: SSM SendCommand `resources: ['*']` | Can run on any SSM-managed instance in account |
| SH-S5: EventBridge payload injected raw into prompt | Prompt injection surface |
| SH-S6: No SQS rate limiting | Alarm storm → parallel Bedrock invocations |

These are documented knowns, not production risks — the system runs with `DRY_RUN=true` by default.

## AI Engineering Gaps

From the three LLM system reviews:

| System | Gap | What to Say Instead |
|---|---|---|
| Article Pipeline | No writer self-refinement loop (R5 HIGH) | "Designed for iterative improvement — implementation gap identified and documented" |
| Chatbot | No RAG evaluation pipeline (A8 HIGH) | "Guardrails and grounding configured; evaluation pipeline is a documented next step" |
| Self-Healing Agent | Verification step advisory, not enforced (SH-R4 HIGH) | "Post-remediation check included in prompt guidance — not yet loop-enforced" |
| All systems | No outcome tracking | "Session memory and token tracking implemented; success correlation is documented future work" |

## What Was NOT Built

Do NOT claim these — they are not in the portfolio:

- **EKS / GKE / AKS** — deliberate choice to use kubeadm for learning depth; can say "evaluated EKS, chose self-managed for full-stack learning"
- **Terraform** — CDK only; can say "familiar with Terraform concepts, implemented IaC via CDK"
- **Helm chart authoring from scratch** — used existing charts (Prometheus, Grafana, Loki); can say "configured and customised third-party Helm charts"
- **Service mesh (Istio, Linkerd)** — Traefik v3 provides L7 ingress and middleware chains (BasicAuth, IP allowlist, rate limiting). **CRITICAL: agents must NEVER use the phrase "service mesh" for this project.** Use "Traefik v3 ingress and cross-namespace routing" instead. No mTLS between pods.
- **Multi-region active-active** — single-region (eu-west-1) with edge stack in us-east-1 for CloudFront only
- **Multi-cluster federation** — single cluster
- **Database operations at scale** — DynamoDB used for simple single-table patterns, no complex query tuning
- **Container security scanning** — Checkov for IaC, but no Trivy/Snyk container scanning in pipeline
- **Fine-tuning / RLHF** — Bedrock API only; no model training
- **Production ML inference serving** — Bedrock managed; no self-hosted model serving
- **Large team CI/CD governance** — no branch protection rules, CODEOWNERS, or merge queue patterns for team use
- **Formal SLOs** — Grafana alerting and SNS notifications are configured but error budgets and burn-rate alerts are not defined. Alerting is threshold-based. Say "threshold-based alerting with SNS" not "SLO-based error budgets"
- **Commander.js CLI** — operational scripts use `justfile` task runner + TypeScript. Do NOT claim Commander.js CLI experience.
- **GCP / GKE / Google Cloud** — AWS-native portfolio; Kubernetes skills transfer but no GCP hands-on
  - **GCP onboarding status: IN_PROGRESS — evidence required before claiming.**
    Agent instruction: This rule is an instance of the general evidence gate below — apply it to GCP and to any other IN_PROGRESS technology gap.

**General evidence gate — applies to all IN_PROGRESS gap entries:**

When a technology or platform has status IN_PROGRESS, agents must verify evidence before generating claims:

| Evidence available | What agent may say |
|---|---|
| Confirmed activity in KB, codebase, or committed config | Name the specific confirmed activities only |
| "Actively pursuing" / "actively onboarding" language with no confirmed activity | "I am actively beginning [technology] onboarding" — no specific completed activities |
| No evidence of any kind | Do not mention the technology in forward-looking context |

The risk is symmetric across all technologies: a candidate who lists specific completed activities that cannot be verified will be exposed in the first technical screen — regardless of which platform or tool is named. Do not generate aspirational specifics. Use the hedged form until evidence is confirmed and documented in the KB.
- **Large-scale multi-node clusters** — self-hosted dual-pool cluster (general t3.small 1–4, monitoring t3.medium 1–2). Do NOT say "enterprise-scale cluster operations" or "100+ node clusters"

## What Was Built That's Unusual

These are rare in portfolios and should be highlighted, not downplayed:

- **Self-hosted Kubernetes** without managed services — shows depth, not just API usage
- **End-to-end observability** from OS metrics to distributed traces to RUM
- **Three distinct LLM system patterns** — most engineers have zero production-pattern AI experience
- **Reactive autonomous agent with real write access** — not a toy chatbot
- **DORA metrics self-assessment** — shows maturity beyond "I built a thing"
- **265+ IaC test assertions** — most infrastructure code is untested

## Related Pages

- [[achievements]] — what CAN be claimed with numbers
- [[concept-to-resume]] — safe language mappings
- [[role-archetypes]] — which gaps matter per role type
- [[dora-metrics]] — G1-G8 detailed remediation plan
