---
title: Role Archetypes
type: resume
tags: [resume, role, archetypes, devops, sre, full-stack, ai-engineering, platform]
sources: [raw/kubernetes_infrastructure_audit_16_04.md]
created: 2026-04-16
updated: 2026-04-16
---

# Role Archetypes

Per-role emphasis maps. Agents: when given a job description, identify the archetype, pull the bullets from [[achievements]], apply the language from [[concept-to-resume]], and respect [[gap-awareness]]. Adapt emphasis — never invent new claims.

## Archetype 1: Platform / Infrastructure Engineer

**What they care about:** IaC correctness, stack design patterns, cloud resource lifecycle, scalability foundations.

**Lead with:**
- 10-stack CDK architecture with lifecycle-separated stacks (change frequency, not AWS service type)
- Data-driven config (19 SG rules from one file, parameterised pools eliminate 600 lines)
- 265+ CDK assertions — infra code is tested code
- SSM Parameter Store as cross-stack service mesh (no CF export lock-in)

**Supporting evidence:**
- [[cdk-kubernetes-stacks]] — full stack catalogue, deployment order, config-driven pattern
- [[concepts/cluster-networking]] — VPC topology, SG depth, NLB design
- [[infra-testing-strategy]] — CDK testing pyramid, 1:0.47 test ratio

**Sample bullets:**
```
Designed 10-stack CDK architecture with change-frequency lifecycle separation —
IAM grants redeploy in ~30 s without touching compute stacks, reducing blast
radius and deployment risk.

Centralised environment configuration in a 774-line TypeScript config file driving
19 security group rules, worker pool sizing, AMI versions, and cluster networking
— all with automated CDK assertion coverage.

Eliminated ~600 lines of duplicated stack code by refactoring 3 named worker stacks
into a single parameterised KubernetesWorkerAsgStack.
```

**Gaps to acknowledge if asked:** single-AZ, portfolio scale, solo-operated.

---

## Archetype 2: Site Reliability Engineer (SRE)

**What they care about:** DORA metrics, TTSR, observability, incident automation, runbooks, DR.

**Lead with:**
- DORA baselines: ~30 min lead time, ~15 min TTSR, ~2% CFR, on-demand deploys
- Self-healing reactive agent — autonomous diagnosis + remediation with real write access
- Disaster recovery: etcd + PKI to S3, RTO ~5–8 min
- Dual-layer observability: CloudWatch + LGTM + Faro RUM

**Supporting evidence:**
- [[dora-metrics]] — metric baselines, evidence, tracking plan
- [[concepts/self-healing-agent]] — reactive agent architecture
- [[disaster-recovery]] — DR path, RTO, backup strategy
- [[observability-stack]] — LGTM stack, 13 dashboards, alerting pipeline

**Sample bullets:**
```
Achieved DORA-class metrics on a self-managed Kubernetes platform: ~30 min
lead time, ~15 min TTSR, ~2% change failure rate — underpinned by 8 CDK
test suites and a 7-stage gated CI/CD pipeline.

Built reactive self-healing agent (AWS Bedrock ConverseCommand + 6 MCP tools)
that autonomously diagnoses CloudWatch alarms and triggers bootstrap Step Functions
— zero manual intervention for transient node failures.

Designed full disaster recovery path: etcd + PKI backup to S3 every 6 hours,
TLS and JWT to SSM SecureString, control-plane reconstruction RTO ~5–8 min.
```

**Gaps to acknowledge if asked:** DORA numbers are estimates (G1), no formal SLA, solo on-call.

---

## Archetype 3: Senior Full-Stack Engineer

**What they care about:** application architecture, TypeScript correctness, test coverage, deployment maturity.

**Lead with:**
- Yarn 4 monorepo with two distinct application patterns (Next.js 15 + TanStack Start)
- Type-safe RPC via `createServerFn` — no API contract drift
- Production security patterns: CSP, Cognito PKCE, no credentials in browser
- Blue/Green deployments via Argo Rollouts

**Supporting evidence:**
- [[tools/nextjs]] — 7 API routes, OTel, prom-client, Faro, 4-stage Docker
- [[tools/tanstack-start]] — `createServerFn`, 12 server modules, full CSP, Vitest
- [[frontend-portfolio]] — monorepo overview, 20-dimension comparison
- [[tools/argo-rollouts]] — Blue/Green strategy, HPA, analysis runs

**Sample bullets:**
```
Built Yarn 4 monorepo hosting Next.js 15 public site and TanStack Start admin
dashboard — type-safe RPC via createServerFn, full CSP, Cognito PKCE auth,
OTel distributed tracing, Prometheus metrics, Faro RUM.

Implemented Blue/Green deployment via Argo Rollouts with analysis runs and HPA
targeting — zero-downtime deploys with automatic rollback on failed health checks.

Designed 4-stage Docker multi-stage builds (deps/prune/build/runtime) using
Node.js Alpine, keeping production images minimal for security and pull speed.
```

**Gaps to acknowledge if asked:** portfolio traffic, no team-scale PR workflow experience.

---

## Archetype 4: AI / ML Engineer

**What they care about:** LLM system design, inference-time techniques, agent architectures, production safety.

**Lead with:**
- Three distinct Bedrock patterns: Deterministic Workflow, Managed RAG, Reactive Autonomous
- Extended Thinking adaptive budgeting (2K–16K tokens via complexity scorer)
- Prompt caching (~90% cost reduction), Guardrails (content filters + grounding 0.7)
- MCP Gateway with Cognito M2M, S3 episodic memory

**Supporting evidence:**
- [[ai-engineering/self-healing-agent]] — full agentic loop, tool design, 15 gaps
- [[ai-engineering/inference-time-techniques]] — 11-technique assessment
- [[ai-engineering/article-pipeline]] — Extended Thinking, adaptive compute, prompt caching
- [[ai-engineering/chatbot]] — Guardrails architecture, RAG gaps, defence-in-depth

**Sample bullets:**
```
Implemented three production-pattern LLM systems on AWS Bedrock: deterministic
workflow agent (Step Functions + adaptive Extended Thinking), managed RAG agent
(Guardrails grounding threshold 0.7, 6-layer defence), reactive autonomous agent
(ConverseCommand tool-use loop with real write access to production infrastructure).

Applied inference-time scaling: adaptive Extended Thinking with 5-signal complexity
scorer (3 tiers, 2K–16K token budget) reducing Writer Lambda token cost while
maintaining quality on complex topics.

Implemented S3-backed episodic session memory with cross-invocation self-refinement
— model receives prior tool call sequence and is explicitly instructed not to repeat
failed remediation paths.
```

**Gaps to acknowledge if asked:** no model fine-tuning, no self-hosted inference, DORA numbers are estimates.

---

## Archetype 5: DevOps / Cloud Engineer

**What they care about:** CI/CD maturity, cloud native patterns, security posture, cost efficiency.

**Lead with:**
- 26-workflow GitHub Actions monorepo with reusable library and OIDC
- `just` task runner ensuring local-CI parity
- Checkov 10 custom rules, CDK-NAG, severity gating
- Spot instances, Intelligent Tiering, CI container cost savings

**Supporting evidence:**
- [[ci-cd-pipeline-architecture]] — 26 workflows, TypeScript scripting layer, OIDC+AROA
- [[tools/github-actions]] — custom Docker image, path-scoped triggers, sha-rAttempt tags
- [[tools/checkov]] — 10 custom rules, SARIF output, severity gating
- [[tools/just]] — 6 recipe groups, local-CI parity rationale

**Sample bullets:**
```
Designed 26-workflow GitHub Actions CI/CD system for a Yarn 4 monorepo: reusable
workflow library, OIDC-based AWS auth with AROA masking, path-scoped triggers,
immutable sha-rAttempt image tags, custom CI container eliminating ~3 min/run.

Implemented policy-as-code IaC security scanning: 10 custom Checkov rules
(5 IAM + 5 SG), CDK-NAG AwsSolutions pack, CRITICAL/HIGH blocking pipeline
gates — integrated into pre-flight stage before any AWS API calls.

Optimised infrastructure cost via Spot instances on all worker pools (~60–70%
cost reduction vs. On-Demand), S3 Intelligent Tiering, and 3-day access log
lifecycle expiration.
```

**Gaps to acknowledge if asked:** single environment (dev), solo-maintained, portfolio traffic.

---

## Archetype Selector

If the job description mentions: → Use archetype:

| JD Signal | Archetype |
|---|---|
| "IaC", "CDK", "Terraform", "platform team" | Platform / Infrastructure |
| "SRE", "reliability", "on-call", "DORA", "MTTR" | SRE |
| "React", "TypeScript", "full-stack", "frontend" | Full-Stack |
| "LLM", "AI", "ML", "Bedrock", "RAG", "agent" | AI / ML |
| "CI/CD", "DevOps", "pipeline", "cloud native" | DevOps / Cloud |
| "staff", "principal", "architect" | Mix Acts 1+2+3 equally — show breadth |

## Related Pages

- [[narrative]] — unified story that connects all archetypes
- [[achievements]] — numbers to pull into bullets
- [[concept-to-resume]] — safe implementation → language mappings
- [[gap-awareness]] — boundaries to respect per archetype
