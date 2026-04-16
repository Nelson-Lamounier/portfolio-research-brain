---
title: Agent Guide — Resume Generation
type: resume
tags: [resume, agents, guide, confidence, framing, devops, ai-engineering]
sources: [raw/resume-domain.md]
created: 2026-04-16
updated: 2026-04-16
---

# Agent Guide — Resume Generation

**Start here.** This is the direct path for AI agents generating resume summaries, achievement bullets, and cover letters from this knowledge base.

Read this page first. Then read [[concept-library]] for per-concept evidence and framing.

---

## Confidence Thresholds

| Status | What it means | What agents may say |
|---|---|---|
| **STRONG** | Fully implemented with file evidence | Claim directly and confidently |
| **PARTIAL** | Implemented with caveats or missing components | Use `recommended_framing` only — never full achievement_pattern |
| **IN_PROGRESS** | Exists but not production-validated | Use "currently implementing" language only |
| **ABSENT** | Not built | Never mention this concept |
| **IMPLIED** | Reasonable inference, not directly evidenced | Mention with hedging language only |

See [[concept-library]] for each concept's status.

---

## Step-by-Step: Resume Summary

1. Read [[narrative]] → Section "One-Sentence Positioning" as the foundation.
2. Identify role type from the JD → select the matching variant from [[narrative]] "Role Identity Variants" or [[role-archetypes]] archetype selector.
3. If JD values both infra and product delivery → use the unified narrative from [[narrative]] "The Unified Story".
4. If JD mentions SRE or reliability → include the Support-to-DevOps transition narrative from [[narrative]].
5. Never use a concept whose status is ABSENT or PARTIAL without the `recommended_framing`.

**JD Signal → Narrative variant quick-map:**

| JD mentions | Use |
|---|---|
| "IaC", "CDK", "platform team", "multi-account" | Platform Engineering narrative |
| "SRE", "MTTR", "incident response", "reliability" | Support-to-DevOps transition + DORA metrics |
| "full-stack", "React", "TypeScript", "frontend" | Full-stack + platform unified narrative |
| "LLM", "AI", "Bedrock", "agent", "RAG" | AI-augmented engineering narrative |
| "DevOps", "CI/CD", "pipelines", "cloud native" | Platform + delivery narrative |
| "staff", "principal", "architect" | Mix all three acts — show breadth |

---

## Step-by-Step: Achievement Bullets

1. Draw from [[achievements]] Achievement Bank.
2. Prioritise bullets where the concept status in [[concept-library]] is STRONG.
3. For PARTIAL concepts → use only the `recommended_framing` from [[concept-library]].
4. For IN_PROGRESS items → use "architectural evolution" framing: "Deployed X — currently extending to Y."
5. For ABSENT concepts → do not generate a bullet.
6. Preserve all numbers — never round or estimate beyond what's in [[achievements]].

**Numbers that are safe to claim directly:**
- 20+ ArgoCD-managed applications (not "5 workloads + 4 platform" — that is outdated)
- 4 AWS accounts (dev/staging/prod/management)
- 4 Bedrock AI applications (article pipeline, job strategist, chatbot, self-healing agent)
- 265+ CDK test assertions
- 22+ GitHub Actions workflows
- ~90% prompt cache cost reduction (Writer Lambda only — scoped to that Lambda)
- ~30 min lead time, ~15 min TTSR, ~2% CFR (DORA estimates, not measured dashboards — say "~")

---

## Step-by-Step: Cover Letter

1. Open with role identity variant from [[narrative]] Section 1.2 or [[role-archetypes]].
2. Use the most relevant narrative block from [[narrative]] Section 5.
3. Select 2–3 achievement bullets from [[achievements]] that map to the JD's top 3 requirements.
4. If JD mentions AI tooling → always include Bedrock/AI content (4 applications, STRONG status).
5. If JD mentions reliability/DORA → include DORA metrics section from [[dora-metrics]].
6. If JD mentions Kubernetes internals → surface kubeadm depth and control-plane operations.
7. Close with the dual-perspective differentiator: "built the platform AND deployed production workloads onto it."

---

## ATS Optimization Rules

Applicant Tracking Systems score resumes before a human reads them. All generated output must satisfy:

1. **Exact keyword matching** — use the JD's exact term, not a synonym. If JD says "Kubernetes", write "Kubernetes". If JD says "infrastructure as code", write "infrastructure as code".
2. **Certification names verbatim** — `AWS Certified DevOps Engineer – Professional` (note the en-dash). Never abbreviate.
3. **Standard section headers** — "Experience", "Skills", "Education", "Certifications". Do not use creative headers.
4. **Bullet format:** `[Strong verb] [specific technology/context] [measurable outcome]` — e.g. "Reduced EC2 node replacement time 75% (12 min → 3 min) via Golden AMI pipeline."
5. **No tables inside bullet lists** — ATS parsers strip table formatting.
6. **Keywords in context, not lists** — a keyword in a credible evidence sentence scores higher than the same keyword in a skills list.
7. **Work history section must include:** company name (exact), job title (exact), dates, location. These are ATS parse anchors.

---

## Human-Written Output Rules

These rules prevent AI-detection tools from flagging the output and ensure the text reads authentically:

1. **Before generating any bullet or paragraph, retrieve a phrase from [[voice-library]]** and use it as an anchor. This is mandatory — not optional.
2. **Banned verbs** — NEVER use: spearheaded, leveraged, orchestrated, revolutionized, streamlined, synergized, fostered, utilized. See [[voice-library]] for the full banned list.
3. **Vary sentence length** — mix short (under 12 words), medium, and long sentences. No more than 3 consecutive bullets of the same length.
4. **No consecutive same-verb openers** — if bullet 1 starts with "Built", bullet 2 cannot also start with "Built".
5. **Specific proper nouns over generic descriptions** — "Grafana Alloy", "Calico CNI", "kubeadm" NOT "monitoring collector", "network plugin", "cluster bootstrapper".
6. **Cover letters: first-person direct** — "I built X" not "X was built" or "responsible for building X".
7. **No opener clichés** — never start a cover letter with "I am writing to express my interest in". Start with the insight or the journey.
8. **Anti-AI-scan checklist** — before finalising any document, verify all items in [[voice-library]] Anti-AI-Scan Checklist.

---

## Hard Rules for All Agents

These are absolute — not suggestions:

1. **NEVER say "service mesh"** — Traefik v3 is ingress. Say "Traefik v3 ingress and cross-namespace routing with middleware chains."
2. **NEVER claim SLA compliance** — no formal SLA exists.
3. **NEVER claim on-call experience** — solo-operated, no on-call rotation.
4. **NEVER claim Terraform experience** — CDK only. Say "AWS CDK TypeScript (equivalent IaC capability)" if asked.
5. **NEVER say "enterprise-scale" or "100+ node clusters"** — dual-pool cluster, max 6 nodes.
6. **NEVER say "SLO-based error budgets" or "burn-rate alerts"** — threshold-based alerting only.
7. **NEVER claim EKS/GKE/AKS** — say "evaluated managed K8s, chose kubeadm for full-stack learning depth."
8. **NEVER claim fine-tuning or RLHF** — Bedrock API only, no model training.
9. **NEVER claim Commander.js CLI** — justfile task runner + TypeScript scripts.
10. **ALWAYS add scope qualifier** — "portfolio-scale", "solo-operated", or "self-managed" unless JD asks otherwise.

---

## Concept Status Quick-Reference

Full detail in [[concept-library]]. Quick-reference:

| Concept | Status |
|---|---|
| Self-healing workloads (ArgoCD) | STRONG |
| Kubernetes internals (kubeadm) | STRONG |
| GitOps delivery (ArgoCD App-of-Apps, 20+ apps) | STRONG |
| CI/CD pipeline design (22+ workflows) | STRONG |
| Three-pillar observability (Prometheus/Loki/Tempo) | STRONG |
| CDK multi-account IaC (4 accounts) | STRONG |
| Cluster Autoscaler + multi-pool ASG | STRONG |
| OIDC-federated CI/CD | STRONG |
| AWS Bedrock / AI pipelines (4 applications) | STRONG |
| justfile task runner | STRONG |
| Namespace isolation + NetworkPolicies | STRONG (partial coverage) |
| Service mesh | PARTIAL — use recommended_framing only |
| Formal SLOs / error budgets | PARTIAL — threshold-based alerting only |
| DORA metrics | PARTIAL — estimates, not measured dashboards |
| Multi-region active-active | ABSENT |
| Terraform / HCL | ABSENT |
| GCP / GKE | ABSENT |
| Fine-tuning / RLHF | ABSENT |
| Large-team CI/CD governance | ABSENT |

---

## Related Pages

- [[concept-library]] — per-concept STRONG/PARTIAL/ABSENT with evidence file paths
- [[career-history]] — Amazon work history, ATS-ready bullets, certifications, automation project
- [[voice-library]] — authentic phrase anchors, banned terms, ATS keyword rules, anti-AI checklist
- [[narrative]] — full positioning statement, unified story, role variants, Support→DevOps evidence
- [[achievements]] — quantified scorecard with wiki-sourced evidence (portfolio + Amazon)
- [[concept-to-resume]] — implementation detail → job language mappings
- [[gap-awareness]] — full boundary inventory (what NOT to claim)
- [[role-archetypes]] — per-role bullet emphasis and sample bullets
- [[dora-metrics]] — DORA metric baselines and evidence
