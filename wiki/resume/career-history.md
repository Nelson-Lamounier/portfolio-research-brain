---
title: Career History
type: resume
tags: [resume, career, amazon, aws, support, devops, work-history, ats]
sources: [raw/aws_support_career_review_2026.md]
created: 2026-04-16
updated: 2026-04-16
---

# Career History

Canonical work history for resume generation. ATS-ready format — action verb + context + outcome. Agents: use exact certification names, exact company names, and exact dates as written here. Do NOT paraphrase certification titles.

---

## Amazon Web Services — Technical Customer Service Associate
**Period:** 2023–2026 (approx — confirm exact start date before submitting)
**Location:** Dublin, Ireland (EMEA)
**Team:** Customer Service, EMEA

### Role in one line (ATS-optimised)

Technical customer-facing engineer providing escalated AWS infrastructure support — IAM, VPC, EC2, CloudFormation, networking, and cross-service architecture across enterprise and commercial accounts.

### Why this role matters for the transition narrative

This is not a generic call-centre support role. The day-to-day work was:
- Diagnosing AWS production misconfigurations under customer pressure
- Navigating IAM policy boundaries, VPC routing, and service limits
- Handling multi-service escalations that frontline support could not resolve

This gave first-hand exposure to how AWS infrastructure fails in production — the exact failure modes that the portfolio projects are designed to recover from automatically. See [[narrative]] Support-to-DevOps section.

### ATS-ready bullets (use verbatim or lightly adapted)

```
Resolved complex AWS infrastructure escalations across IAM, VPC, EC2,
CloudFormation, and networking — diagnosing production misconfigurations
for enterprise customers as the final technical point of contact before
executive escalation.

Served as regional service continuity lead — proactively covered escalated
customer case queues during team capacity constraints, maintaining EMEA
customer resolution timelines under high-demand conditions.

Became Subject Matter Expert in internal technical tooling — delivered
knowledge transfer across the team via structured sessions and direct
mentoring, enabling faster resolution on complex technical cases.

Designed scripted automation system to replace a 10–20 hours/week manual
case distribution workflow: resource querying, data retrieval by tag,
fair distribution algorithm, and automated Slack notifications. Authored
full business case and ROI analysis for global rollout.

Authored and deployed HTML/CSS/JavaScript internal knowledge base pages
for multiple AWS teams — structured operational processes as navigable
reference documentation, reducing onboarding time and improving
cross-team knowledge transfer over 3 years.
```

### IN_PROGRESS: Case Distribution Automation Project

**Status:** Architecture complete — pending management sponsorship and security review

Design for full automation of EMEA case distribution workflow:
- Problem: 10–20 hours/week manual overhead; 4-platform data fragmentation (case console, spreadsheet, doc tool, Slack)
- Solution: "Dante Scripts" automation — resource management, case retrieval by tag, distribution algorithm, Slack dispatch
- Business impact: Global rollout candidate; estimated hundreds of hours/week saved across regions
- Documentation complete: business requirements, ROI analysis, technical approach, metrics impact

**Framing for resume (IN_PROGRESS rules apply — use "designed" not "built"):**
> "Identified 10–20 hours/week manual overhead in regional case management. Designed end-to-end scripted automation system covering resource querying, case retrieval, distribution logic, and Slack notification dispatch. Authored business case and ROI analysis. Global deployment candidate pending security approval."

---

## Internal Documentation — Multiple AWS Teams
**Period:** 2023–2026 (3 years, ongoing)
**Scope:** Cross-team internal knowledge base

### Summary

Assisted multiple internal teams in creating and maintaining structured process documentation. Work involved deploying HTML, CSS, and JavaScript pages for internal knowledge bases — structuring complex workflows as searchable, navigable reference material.

### ATS-ready bullets

```
Built and maintained internal HTML/CSS/JavaScript knowledge base pages
for multiple teams over 3 years — translating complex operational
workflows into navigable reference documentation used across the organisation.

Collaborated with stakeholders across teams to document technical processes
as structured web pages, reducing reliance on tribal knowledge and
improving cross-team onboarding efficiency.
```

### Concept status for this skill

| Skill | Status | Notes |
|---|---|---|
| HTML/CSS/JavaScript (documentation context) | STRONG | 3 years, multiple teams |
| Technical writing / knowledge management | STRONG | Evidenced across 3 years |
| Internal tooling documentation | STRONG | Cross-team scope |

---

## Certifications & Education

| Credential | Issuer | Status | Year |
|---|---|---|---|
| AWS Certified DevOps Engineer – Professional | Amazon Web Services | Completed | 2025 |
| Higher Diploma in Computer Science | [Institution — confirm name] | Completed | 2025 |

**ATS note:** Always write "AWS Certified DevOps Engineer – Professional" in full — ATS systems match on the exact AWS certification name. Do NOT abbreviate to "AWS DevOps cert" or "DevOps Professional certification."

---

## Performance Recognition

- Year-end rating: **Meets High Bar** (exceeds standard performance threshold — Amazon performance framework)
- Management explicitly endorsed career progression toward a technical engineering role, citing AWS certification and Higher Diploma completion as evidence of readiness
- Peer recognition themes (consistent across year): customer obsession, ownership, composure under pressure, cross-team flexibility

**Framing note:** "Meets High Bar" is Amazon-internal language. For non-Amazon JDs, translate to: "Strong performer — exceeded performance targets." Do NOT assume the reviewer knows Amazon's performance framework.

---

## Self-Directed Platform Engineer — Portfolio Projects
**Period:** 2022–present (ongoing alongside employment)
**Title canonical form:** "Self-Directed Platform Engineer" — NEVER "Freelance Software Engineer"

### Why the title matters

"Freelance Software Engineer" signals client work and hourly billing. "Self-Directed Platform Engineer" signals deliberate technical investment — the correct read for a portfolio-driven engineering candidate.

### Permitted bullets for TSE / SRE / infrastructure roles

Include only bullets that demonstrate:
1. Kubernetes operational depth (kubeadm, ArgoCD, Calico CNI, Traefik v3, Argo Rollouts)
2. IaC and CI/CD pipeline design (CDK TypeScript, GitHub Actions, OIDC)
3. Observability stack (Kubernetes-native: Prometheus, Loki via Grafana Alloy, Tempo over gRPC/OTLP)
4. Disaster recovery (etcd + PKI backup to S3, self-healing node replacement)
5. AI engineering if JD mentions AI/LLM/Bedrock

### Bullets to EXCLUDE for TSE / SRE / infrastructure roles

The following bullets must NOT appear in the Freelance / Self-Directed section for TSE-type roles. They are either wrong-context or already covered elsewhere:

| Bullet | Reason to exclude |
|---|---|
| Serverless REST API (Lambda, API Gateway, DynamoDB, HMAC token) | Not Kubernetes, not customer support context — belongs in full-stack/backend roles only |
| Cost analysis / CloudTrail / Cost Explorer / Trusted Advisor / idle EBS | FinOps signal, not SRE signal — not in TSE JD |
| CI/CD pipeline described in full | Already in Key Achievements as the stronger version — deduplication rule applies |
| Container hardening described in full | Already in Key Achievements — one instance only across the resume |

### Deduplication enforcement for this section

Before writing any Freelance / Self-Directed bullets, list what is already in Key Achievements. Any concept already stated in Key Achievements at full length must not be restated here. Apply the one-clause maximum rule — a brief reference (tool name + one outcome word) is permitted, a full re-explanation is not.

---

## Meta / Accenture — Quality Operations
**Title canonical form:** Use the exact job title from DynamoDB resume data — do not rephrase

### Framing for TSE / infrastructure roles

**NEVER frame this role as QA operations for a TSE or infrastructure application.** The QA operations framing signals test script execution and defect logging — irrelevant to the TSE hiring signal.

The useful angles from this role for TSE / SRE / platform applications:

1. **Distributed systems investigation at scale** — exposure to investigating failures across large-scale, distributed consumer platforms. Frame as: systematic investigation across distributed systems components, cross-service failure correlation, structured debugging methodology.
2. **Cross-functional collaboration methodology** — working across engineering, product, and operations teams at scale. Frame as: structured coordination across multiple stakeholder teams, escalation path navigation, documentation of findings for non-technical and technical audiences.

### ATS-ready framing for TSE roles

```
Investigated and documented failures across distributed consumer-scale platform
components, applying systematic cross-service correlation methodology to identify
root-cause patterns across engineering and product boundaries.

Coordinated across engineering, product, and operations teams to document and
communicate system-level findings, developing structured escalation and
knowledge-transfer processes for cross-functional audiences.
```

### What NOT to include

- QA test case execution or defect logging framing
- Any reference to "testing" as the primary activity
- Specific QA tooling not relevant to the JD

---

## Leadership Principles → Non-Amazon Translation

When applying to non-Amazon roles, translate Amazon LP evidence to universal competencies:

| Amazon LP demonstrated | Universal framing |
|---|---|
| Customer Obsession | Customer-first decision making, composure under pressure |
| Ownership | Proactive problem ownership beyond assigned scope |
| Invent and Simplify | Technical solution design for identified inefficiencies |
| Learn and Be Curious | Continuous self-development (cert + degree during employment) |
| Deliver Results | Consistent performance delivery under metrics pressure |
| Earn Trust | Trusted peer technical advisor; go-to resource for complex cases |

---

## Related Pages

- [[narrative]] — Support-to-DevOps transition narrative (uses this as evidence)
- [[achievements]] — Amazon TCSA accomplishments with scope qualifiers
- [[voice-library]] — Nelson's authentic language anchors for human-written output
- [[agent-guide]] — how to use this page in resume generation
- [[gap-awareness]] — what NOT to claim from this role
