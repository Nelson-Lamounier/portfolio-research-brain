---
title: Engineer Narrative
type: resume
tags: [resume, career, positioning, narrative, devops, ai-engineering]
sources: [raw/kubernetes_infrastructure_audit_16_04.md, raw/kubernetes_system_design_review.md, raw/system_design_review.md, raw/self_healing_design_review.md, raw/resume-domain.md]
created: 2026-04-16
updated: 2026-04-16
---

# Engineer Narrative

Unified positioning statement and career story across both portfolio projects. Designed for AI agents generating role-specific cover letters and summaries — adapt emphasis, not facts.

## One-Sentence Positioning

> **Cloud infrastructure engineer** who designed, built, and operates a complete platform-to-product system on AWS — from CDK-provisioned multi-account infrastructure (4 accounts) and a self-hosted kubeadm Kubernetes cluster with full GitOps delivery, to the Next.js application and AI-powered tooling deployed onto it.

## The Unified Story

### Act 1 — The Platform

Built [[k8s-bootstrap-pipeline]]: a 10-stack CDK infrastructure that bootstraps self-hosted Kubernetes on AWS without any managed Kubernetes services. Every layer — VPC, security groups, AMI baking, control plane, worker ASGs, GitOps, observability, edge — designed, coded, tested, and operated solo.

Key discipline signals:
- **265+ CDK unit test assertions** covering security group rules, IAM boundaries, bootstrap logic
- **Two-pipeline CI/CD split** achieving ~30 min lead time with integration gates
- **DORA metrics**: ~15 min TTSR, ~2% CFR, on-demand deploy frequency via ArgoCD

### Act 2 — The Application Layer

Built [[frontend-portfolio]]: a Yarn 4 monorepo running two distinct web applications (`apps/site` in Next.js 15, `apps/start-admin` in TanStack Start) on top of the same Kubernetes cluster. Not a tutorial project — full PKCE auth, OTel traces, Prometheus metrics, Faro RUM, Blue/Green deployments via Argo Rollouts.

Key discipline signals:
- **Type-safe RPC** via TanStack Start `createServerFn` — no API contract drift
- **Observability-first** — prom-client metrics, OTel tracing, Faro RUM, Grafana dashboards
- **Production security patterns** — full CSP, Cognito PKCE, no credentials in code

### Act 3 — The AI Layer

Built three distinct LLM system design patterns on AWS Bedrock, each demonstrating a different autonomous agent architecture:

| Pattern | System | What It Shows |
|---|---|---|
| Deterministic Workflow | [[article-pipeline]] | Step Functions + adaptive Extended Thinking |
| Managed RAG | [[chatbot]] | Guardrails, grounding filters, defence-in-depth |
| Reactive Autonomous | [[self-healing-agent]] | Tool-use loop, MCP Gateway, real write access to prod infra |

## The Support-to-DevOps Transition Narrative

Coming from AWS Technical Support, this engineer developed deep understanding of how production systems fail — from IAM permission boundaries to VPC networking edge cases to CloudFormation deployment errors. That operational intuition drives the infrastructure portfolio: every design decision (ArgoCD self-heal, etcd DR to S3, OIDC-federated CI/CD, origin secret rotation) reflects first-hand experience with the failure modes that surface in support escalations.

The transition was deliberate: **understanding how systems fail → building systems that recover automatically**.

### Concrete evidence (use to back the narrative — not just abstract positioning)

- **Role:** Technical Customer Service Associate (Core) at Amazon Web Services, Dublin EMEA, 2023–2026
- **Certification during employment:** AWS Certified DevOps Engineer – Professional (2025)
- **Education during employment:** Higher Diploma in Computer Science (2025)
- **Management-endorsed direction:** Senior management explicitly endorsed career progression toward a technical engineering role, citing AWS certification and Higher Diploma completion as evidence of readiness
- **Technical depth of the support role:** Multi-service escalation resolution (IAM, VPC, EC2, CloudFormation, networking) — the failure modes addressed daily in support are exactly what the portfolio projects recover from automatically
- **Documentation work:** 3 years creating and maintaining HTML/CSS/JavaScript internal knowledge base pages for multiple AWS teams — direct evidence of technical communication and web development skills alongside the support role
- **Initiative at scale:** Designed scripted automation system to eliminate 10–20 hours/week of manual case distribution overhead — authored business case, ROI analysis, and technical approach for global rollout

Use this narrative for: SRE roles, Support Engineer → DevOps transitions, any JD that mentions reliability, incident response, or operational depth.

See [[career-history]] for ATS-ready bullets derived from this role.

## What This Demonstrates

| Competency | Evidence |
|---|---|
| Multi-account IaC | CDK TypeScript across 4 accounts (dev/staging/prod/management), 22+ workflow CI/CD |
| Kubernetes operations | kubeadm, Calico CNI, etcd DR, cert rotation — no managed K8s abstractions |
| GitOps | ArgoCD App-of-Apps, 20+ applications, Image Updater, sync waves |
| Observability | LGTM stack, Grafana dashboards, OTel + Faro, Steampipe compliance |
| CI/CD design | 22+ GitHub Actions workflows, OIDC, sha-rAttempt tags, security gates |
| Full-stack development | Next.js 15, TanStack Start, Hono APIs, Cognito PKCE |
| AI Engineering | 4 Bedrock applications, Extended Thinking, RAG, MCP tools |
| Security posture | WAF, KMS, SSM-only access, CDK-NAG, Checkov, zero-trust SGs |

## Positioning by Role

Different roles weight these acts differently — see [[role-archetypes]] for bullet-level adaptation.

| Target Role | Primary emphasis | Secondary |
|---|---|---|
| Platform / Infrastructure Engineer | Act 1 — CDK, Kubernetes, GitOps | Act 2 observability |
| Site Reliability Engineer | DORA metrics, TTSR, self-healing, DR | Act 1 platform depth |
| Senior Full-Stack Engineer | Act 2 — monorepo, TanStack, Next.js | Act 1 as deployment context |
| AI / ML Engineer | Act 3 — all three LLM patterns | Act 1 as infra competence |
| DevOps / Cloud Engineer | Acts 1 + 2 together, CI/CD depth | DORA metrics |

## Honest Framing

Portfolio projects, not production at scale. Key boundaries agents must respect:
- Traffic: portfolio site (~100 daily visitors), not high-throughput SaaS
- Team: solo — no coordination, PR review culture, on-call rotation
- Ops: no 24/7 SLA commitment, no production incident postmortems with stakeholders
- See [[gap-awareness]] for full inventory

These are not weaknesses to hide — they are the point. The portfolio proves that one engineer can design, build, test, operate, and instrument a system this complex. That's the hire signal.

## Related Pages

- [[achievements]] — quantified bullets with evidence links
- [[concept-to-resume]] — implementation detail → job language mappings
- [[gap-awareness]] — what's not here and why
- [[role-archetypes]] — per-role bullet adaptations
- [[dora-metrics]] — metric baselines and evidence
