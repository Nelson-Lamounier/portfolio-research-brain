---
title: Agent Guide — Resume Generation
type: resume
tags: [resume, agents, guide, confidence, framing, devops, ai-engineering]
sources: [raw/resume-domain.md]
created: 2026-04-16
updated: 2026-04-17T18:30
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

> **Abbreviation used throughout this page:** "JD" = job description (the full text of the role posting being applied to).

1. Read [[narrative]] → Section "One-Sentence Positioning" as the foundation.
2. Identify role type from the JD → select the matching variant from [[narrative]] "Role Identity Variants" or [[role-archetypes]] archetype selector.
3. If JD values both infra and product delivery → use the unified narrative from [[narrative]] "The Unified Story".
4. If JD mentions SRE or reliability → include the Support-to-DevOps transition narrative from [[narrative]].
5. Never use a concept whose status is ABSENT or PARTIAL without the `recommended_framing`.

**Summary content filter — strict:**

The Professional Summary must only contain concepts that either:
1. Appear in the JD (exact term or close synonym), OR
2. Are tier-1 differentiators for the role type (see quick-map below)

Concepts present in the KB or original resume but absent from the JD are **silently excluded from the summary**. They belong in the Skills section (for ATS keyword coverage) or experience bullets (for evidence) — never in the summary.

Examples of concepts to exclude from the summary when the JD doesn't mention them:

| Concept | Exclude from summary when JD doesn't mention |
|---|---|
| FinOps / cost optimisation | JD doesn't say "cost", "FinOps", "billing" |
| Policy-as-code | JD doesn't say "OPA", "policy", "compliance automation" |
| AI / Bedrock pipelines | JD doesn't say "AI", "LLM", "Bedrock", "agent" |
| DORA metrics | JD doesn't say "DORA", "MTTR", "lead time", "reliability" |
| Multi-account IaC | JD doesn't say "IaC", "CDK", "multi-account" |

The summary is for the human reader who has 10 seconds. Every sentence must earn its place by mapping to a JD requirement or a role-type differentiator.

**JD Signal → Narrative variant quick-map:**

| JD mentions | Use |
|---|---|
| "IaC", "CDK", "platform team", "multi-account" | Platform Engineering narrative |
| "SRE", "MTTR", "incident response", "reliability" | Support-to-DevOps transition + DORA metrics |
| "full-stack", "React", "TypeScript", "frontend" | Full-stack + platform unified narrative |
| "LLM", "AI", "Bedrock", "agent", "RAG" | AI-augmented engineering narrative |
| "DevOps", "CI/CD", "pipelines", "cloud native" | Platform + delivery narrative |
| "staff", "principal", "architect" | Mix all three acts — show breadth |
| "troubleshoot", "customer", "solutions engineer", "escalation", "TSE", "technical support", "support depth" | Customer-facing infrastructure narrative — see opener pattern below |

**Customer-facing infrastructure opener pattern (TSE / Solutions Engineer / Support roles):**

> "Cloud infrastructure engineer with [N] years triaging enterprise [IAM / VPC / container networking / specific domain] escalations at AWS — debugging across [layer 1], [layer 2], and [layer 3] for production customer environments. [Cert name] certified. [Portfolio differentiator sentence.]"

Rules for this variant:
- **NEVER open with the certification name.** The voice-library tone profile mandates "Action-first, not title-first". The cert is sentence 2 or later.
- The first sentence establishes role identity (what Nelson did) + the customer-facing depth (3 years, enterprise escalations, AWS scale).
- Sentence 2: certification verbatim — `AWS Certified DevOps Engineer – Professional`.
- Sentence 3+: the portfolio differentiator most relevant to the job description (Kubernetes depth, IaC, observability, AI pipelines).
- If the job description explicitly values both support depth AND infrastructure building → include the dual-perspective line: "built the platform AND triaged production failures on it — both sides inform every design decision."

**Summary structure when a gap must be acknowledged (e.g. platform unfamiliarity):**

The summary must close on a strength, not a gap. Ending on the gap is the last thing a recruiter reads before moving on — it anchors the impression on the weakness.

Correct structure:
1. Role identity + depth claim (sentence 1)
2. Certification + evidence (sentence 2)
3. Gap bridge — honest, one sentence, forward-looking (sentence 3, middle)
4. Portfolio differentiator — the strongest signal for this role (closing sentence)

Example for a role where the candidate lacks platform X:
> "[Role identity + depth]. [Cert]. [Platform X] ramp-up is an active onboarding objective; [cloud/infra fundamentals] transfer directly. [Strongest portfolio differentiator for this role]."

Never end on: "X is a gap I am working on", "I am actively pursuing Y", or any framing that puts the gap as the final word.

**kubeadm differentiator for TSE / Kubernetes roles — MUST articulate the WHY:**

Naming "kubeadm" without context is weak. The differentiator is the insight it signals:
> "kubeadm exposes control plane internals — etcd, kube-apiserver, kubelet, Calico CNI — that managed Kubernetes services abstract away. That is the layer that breaks in production customer escalations."

When the JD mentions Kubernetes, container debugging, or cluster operations, the summary or relevant bullet MUST include the "why kubeadm matters here" framing, not just the tool name.

**Use the managed service name from the JD — never hardcode one:**

| JD mentions | Managed service to name in framing |
|---|---|
| "GKE", "Google Kubernetes Engine", "Anthos" | GKE |
| "EKS", "Amazon EKS", "Elastic Kubernetes Service" | EKS |
| "AKS", "Azure Kubernetes Service" | AKS |
| No specific service named | "managed Kubernetes services" |

Apply this to the framing templates:

| JD context | Framing to use |
|---|---|
| Managed K8s customer escalations (JD-specific service) | "kubeadm-built cluster exposes the control-plane internals [JD managed service] abstracts — the same layer that surfaces in production customer escalations" |
| Kubernetes internals / container runtime debugging | "bootstrapped control plane from scratch via kubeadm — etcd operations, kubelet config, Calico CNI pod networking — no managed service abstractions" |
| Infrastructure depth / hands-on ops | "built and operated the cluster, not just deployed workloads onto it — both sides of the failure surface" |

The differentiator is not "I used kubeadm". It is: "I chose kubeadm deliberately to learn the layer that managed services hide — and that layer is exactly what breaks in production."

---

## Step-by-Step: Achievement Bullets

1. Draw from [[achievements]] Achievement Bank.
2. Prioritise bullets where the concept status in [[concept-library]] is STRONG.
3. For PARTIAL concepts → use only the `recommended_framing` from [[concept-library]].
4. For IN_PROGRESS items → use "architectural evolution" framing: "Deployed X — currently extending to Y."
5. For ABSENT concepts → do not generate a bullet.
6. Preserve all numbers — never round or estimate beyond what's in [[achievements]].

**Addition 2 — Cross-domain instruction: the KB is one connected intelligence system**

The KB spans multiple domains. Agents must treat them as interconnected layers of a single evidence base, not independent documents:

| Domain | What it provides |
|---|---|
| [[achievements]] | Canonical numbers, bullet templates, scope qualifiers |
| [[concepts/dora-metrics]] | Delivery performance outcomes: lead time, MTTR, CFR, deploy frequency |
| [[concepts/infra-testing-strategy]] | Test coverage depth: 265+ assertions, 8 suites, test-to-code ratio |
| [[concepts/ci-cd-pipeline-architecture]] | Pipeline timing, workflow count, two-pipeline split evidence |
| [[concepts/self-hosted-kubernetes]] | Control plane implementation detail, node pool config, networking |
| [[concepts/observability-stack]] | Dashboard count, scrape jobs, stack architecture |
| [[concepts/disaster-recovery]] | RTO numbers, backup strategy, recovery path |
| [[tools/*]] | Tool-specific implementation depth (ArgoCD, Calico, Traefik, etc.) |
| [[ai-engineering/*]] | AI system design, inference techniques, cost metrics |

**Every bullet describing a technical implementation MUST close with an outcome.** "Built X using Y" is incomplete. The workflow:

1. Start with the technical description from [[achievements]] bullet templates
2. Identify which KB domain holds the outcome evidence for that implementation
3. Cross-reference that domain and append the outcome to close the bullet
4. Use only concrete values from the KB. Never qualify a metric with "~", "estimated", "approximately", or "(est.)". If no measured value exists in the KB, use a qualitative outcome instead ("zero manual intervention", "eliminated config drift").

**Outcome-closed bullet format:**
> "[Strong verb] [specific technology + implementation detail], [concrete outcome from KB domain]"

**Cross-domain outcome lookup:**

| Implementation | KB domain to cross-reference | Outcome to append |
|---|---|---|
| Kubernetes cluster / ArgoCD / GitOps | [[concepts/dora-metrics]], [[tools/argocd]] | self-heal reverts within 3 min; on-demand deploy frequency; [TTSR: replace with measured value] |
| CI/CD pipeline / GitHub Actions | [[concepts/dora-metrics]], [[concepts/ci-cd-pipeline-architecture]] | two-pipeline split (infra validation → compute deploy); [lead time: replace with measured job duration]; [CFR: replace with measured value] |
| IaC / CDK / test assertions | [[concepts/infra-testing-strategy]], [[concepts/dora-metrics]] | 265+ assertions, 8 suites, test-to-code ratio 1:0.47; [CFR: replace with measured value] |
| Golden AMI / EC2 boot | [[tools/ec2-image-builder]], [[concepts/dora-metrics]] | Boot time 75% reduction: 12 min to 3 min; [TTSR: replace with measured value] |
| SSM Automation / bootstrap | [[tools/aws-ssm]], [[concepts/dora-metrics]] | Stack failure recovery decoupled from full redeployment; [MTTR: replace with measured value] |
| Observability stack | [[concepts/observability-stack]], [[concepts/dora-metrics]] | 13 dashboards, 12 scrape jobs; [MTTR: replace with measured value] |
| AI engineering | [[ai-engineering/*]] | ~90% prompt cache cost reduction; 4 production systems |
| Disaster recovery | [[concepts/disaster-recovery]] | etcd + PKI backup to S3; [RTO: replace with timed etcd restore from S3 — run `etcdctl snapshot restore`, measure wall-clock time from trigger to healthy control plane] |

Never output "Built X using Y and Z" without an outcome. If no KB metric applies, use a qualitative outcome: "zero manual intervention", "eliminated config drift", "no dropped cases during transition".

**Key Achievements section limits — hard constraints:**

- Maximum **4 bullets**. Select the 4 most relevant to the job description. Drop the rest.
- Maximum **100 words total** across all 4 bullets. See word count budget table. Count before outputting. Trim to fit.
- Each bullet must stand alone — no preamble, no section header sentence.

**Achievement bullet ordering rule — role-type driven, not optional:**

Determine the role type from the job description before selecting or ordering any bullets. Apply the matching rule below exactly.

**Infrastructure / support roles** (TSE, SRE, Platform Engineer, Solutions Engineer, DevOps Engineer):

1. Kubernetes operational bullets first (kubeadm, Calico CNI, ArgoCD self-healing, control plane work)
2. Customer-facing incident triage second (IAM incident triage, CloudTrail analysis, escalation resolution)
3. IaC and CI/CD pipeline bullets third (CDK consolidation, OIDC pipelines, drift detection)
4. Observability fourth — use the Kubernetes-native implementation (Prometheus/Loki/Tempo on K8s), not Docker Compose
5. Serverless, frontend, and full-stack bullets are **excluded entirely**

**Full-stack / product roles** (Software Developer, Full Stack Engineer, Backend Engineer, Product Engineer):

1. Serverless and API bullets first (Lambda, API Gateway, DynamoDB single-table design)
2. Frontend or product delivery second (if applicable)
3. CI/CD and IaC third
4. Kubernetes operational depth is **de-prioritised** — include only if JD explicitly mentions K8s

**AI / ML engineering roles** (Bedrock, LLM, Agent, RAG):

1. Bedrock AI pipelines first (4 applications, agent orchestration, RAG pipelines)
2. CI/CD and IaC second
3. Kubernetes and observability third (supporting infrastructure context only)
4. Serverless excluded unless it directly supports the AI pipeline

**When the role type is ambiguous:** default to infrastructure ordering and include a note in `analysis_notes` flagging the ambiguity.

**Achievement filtering — drop, do not reorder, bullets that don't map to the JD:**

A bullet that names a technology not mentioned in the job description and not in the top 3 JD requirements occupies space that should go to a relevant bullet. Remove it from the tailored version. It is not a reorder — it is a deletion.

Examples for TSE / GKE-focused roles:
- Drop: "Serverless REST APIs" (Lambda/API Gateway — not Kubernetes, not customer support)
- Drop: "ECS container hardening" (ECS is not GKE)
- Drop: "FinOps cost optimisation / CloudTrail / Cost Explorer / Trusted Advisor / idle EBS volumes" (not in TSE JD)

**Experience section pre-flight — AGENT-INTERNAL ONLY. Run silently. Do not include this list in any output.**

1. AWS section bullet order: (1) customer-facing escalation triage, (2) service continuity lead, (3) scripted automation / Python/Bash — specifically "eliminating 10–20 hours/week of manual case distribution overhead", (4) KB documentation — present but tightened to the shortest version.
2. KB documentation bullet constraint: the HTML/CSS/JavaScript internal knowledge base bullet must be the shortest bullet in the section. If it is currently the longest, trim it. Maximum 25 words.
3. Freelance / Self-Directed title: MUST be "Self-Directed Platform Engineer". NEVER "Freelance Software Engineer". See [[career-history]] Freelance section.
4. Freelance section deduplication: CI/CD pipeline and container hardening must not be restated in full if already present in Key Achievements. Apply the one-clause maximum rule. See [[career-history]] Freelance deduplication enforcement.
5. Serverless REST API bullet (Lambda/API Gateway/DynamoDB/HMAC): REMOVE from Freelance for TSE roles.
6. Cost analysis bullet (CloudTrail/Cost Explorer/Trusted Advisor/idle EBS): REMOVE from AWS section for TSE roles.
7. Meta/Accenture role: frame as distributed systems investigation and cross-functional collaboration. NEVER as QA operations. See [[career-history]] Meta/Accenture section.
8. Em dash in mid-sentence position: scan every bullet. Replace any "— applying", "— using", "— enabling", "— providing" construction with a comma or restructure as a new clause. Em dash is permitted only in date ranges and role/company separators.

**Implementation variant selection — pick the version that matches the JD context:**

When the same capability exists in multiple implementations (e.g. observability as Docker Compose stack vs Kubernetes-native), always select the implementation that matches the JD context:

| JD context | Use this implementation |
|---|---|
| Kubernetes / GKE / container ops | Kubernetes-native observability (Prometheus scraping pod metrics, Loki collecting container logs, Tempo tracing across services on the K8s cluster) |
| General DevOps / platform | Docker Compose 7-container observability stack |
| Both present in JD | Kubernetes-native; mention Docker Compose only if space allows |

Never default to the Docker Compose version for a Kubernetes-focused role. The agent must read the JD context before selecting which implementation to cite.

**Numbers that are safe to claim directly:**
- 25 ArgoCD-managed applications, 25/25 healthy (measured 2026-04-17 — use "25" not "20+")
- 4 AWS accounts (dev/staging/prod/management)
- 4 Bedrock AI applications (article pipeline, job strategist, chatbot, self-healing agent)
- 265+ CDK test assertions
- 22+ GitHub Actions workflows
- ~90% prompt cache cost reduction (Writer Lambda only — scoped to that Lambda)
- DORA metrics (lead time, TTSR, CFR): DO NOT use these until real measured values replace this line. Omit entirely if no concrete value exists in [[concepts/dora-metrics]]. A hedged number signals an unmeasured system.

---

## Step-by-Step: Key Projects

1. Select projects from [[achievements]] — see "Project Templates by Role Type" section.
2. Maximum **2 projects** per resume. Select the 2 most relevant to the job description.
3. For each project, apply the same role-type ordering as Key Achievements — lead with the technology most relevant to the job description.
4. Use the implementation variant that matches the JD context (see implementation variant selection rule in the Achievement Bullets section above).

**Mandatory pre-flight deduplication check — AGENT-INTERNAL ONLY. Run silently before writing any project description. Do not include this check or its output in the resume.**

Before drafting the second project, list every concept, tool, and number already used in Key Achievements. Cross-reference against what you plan to write. Any item that appears in Key Achievements must not be restated in Projects — it may appear as a single passing reference at most.

CI/CD pipeline detail is the most common failure point. If Key Achievements already contains:
- GitHub Actions workflow count (22+)
- CDK test assertions (265+)
- OIDC, Checkov, drift detection, or rollback mechanics

Then the second project description must not re-explain these. The second project earns its place by surfacing detail that Key Achievements cannot carry — architectural decisions, integration patterns, the problem it solved that no other section covers.

**What the second project should do that Key Achievements cannot:**
- Name the specific architectural constraint that drove the project's design
- Surface one implementation detail not visible from bullet-format evidence (e.g. the two-pipeline split rationale, the Alloy → Loki ingestion path, the etcd backup trigger mechanism)
- Close on an outcome scoped to that project specifically — not a number already used elsewhere

**Project framing rule — proactive choice, not gap-filling:**

Never frame a project as "addressing a lack of X" or "solving a missing Y." This signals the project was reactive. Frame every project as a deliberate architectural decision.

- Wrong: "addressing the lack of unified monitoring across containerised workloads"
- Right: "Designed a production-grade observability platform implementing metrics, logs, and distributed traces across containerised workloads"

**Cross-section deduplication rule:**

Before finalising any section, check what has already been stated in earlier sections. Each concept, tool, or detail may appear in full only once across the entire resume. Every subsequent mention must add new signal — a deeper implementation detail, a different context, a specific outcome — or be removed entirely.

| Already stated in | Rule for subsequent sections |
|---|---|
| Key Achievements | Projects gets one clause maximum for the same concept — no full restatement |
| Projects | Experience bullets reference it briefly or omit it |
| Summary | Achievements and Projects do not restate the same framing |
| Skills section | Experience bullets do not list the same tools again — only use them in evidence sentences |

Apply this to all repeated content including:
- CI/CD pipeline (OIDC, Checkov, drift detection, rollback) — if in Achievements, Projects gets one clause only
- Certification names — state once (Summary or Certifications section), do not repeat in bullets
- Tooling lists (kubectl, ArgoCD, Prometheus, Grafana) — name them in the most relevant bullet, not in every section
- Numbers (265+ CDK assertions, 20+ ArgoCD apps) — use in the section where they are most impactful, reference briefly elsewhere

The test: if removing the sentence from a section loses no information the reader didn't already have, remove it.

**No low-signal padding:**

Remove any detail that describes systems administration fundamentals rather than engineering decisions. Examples to always remove from project descriptions:
- "applied Linux file permissions (chmod/chown)" — this is baseline sysadmin, not a differentiator
- "configured SSH access" — assumed
- "installed dependencies" — assumed

**Project selection — JD-driven, not role-type lookup:**

Do not use a fixed role-type table. Instead:

1. Read the job description top 3 requirements.
2. Read all available project templates from [[achievements]] — each template has a `[CONTEXT]` tag describing what role it is relevant for.
3. Select the 2 project templates whose `[CONTEXT]` tag best matches the job description requirements.
4. If two projects cover the same technology domain, pick the one with more specific implementation detail.

The agent is responsible for making this match — the KB provides the raw material, the job description provides the filter. Examples of how the match should work:

- JD requires Kubernetes cluster operations → select "Self-hosted Kubernetes cluster via kubeadm"
- JD requires TypeScript, system design, or full-stack delivery → select "Next.js + TanStack Start monorepo"
- JD requires AI, LLM, or Bedrock → select "Bedrock AI pipelines"
- JD requires observability or monitoring in a K8s context → select "Kubernetes-native observability"
- JD requires observability in a general DevOps context → select "Docker Compose observability stack"
- JD requires IaC or platform engineering → select "10-stack CDK platform"

If no project in [[achievements]] directly matches a JD requirement, pick the closest by domain and note the gap in `analysis_notes`.

---

## Step-by-Step: Technical Skills

1. Read the JD. Identify the top 3–5 technical domains the role values (e.g. Kubernetes, observability, IaC, scripting, security). These become the first subsections in order.
2. Order subsections to mirror JD priority — not alphabetically, not breadth-first. The most JD-relevant subsection appears first.
3. Apply deduplication: each tool or concept appears in **one subsection only**. If a tool fits two categories, place it in the subsection where it is most JD-relevant and omit from all others.
4. Apply the role-specific additions and constraints below before outputting.

**Subsection ordering rule — explicit examples:**

| JD priority signal | Lead subsection |
|---|---|
| Kubernetes, container ops, GKE | Kubernetes & Container Orchestration |
| IaC, CDK, platform engineering | Cloud Infrastructure & IaC |
| SRE, reliability, incident response | Observability & Reliability |
| AI, LLM, Bedrock, agents | AI & ML Engineering |
| TypeScript, React, full-stack | Languages & Frameworks |

**Scripting / tooling subsection — mandatory for TSE and SRE roles:**

Any resume targeting a TSE, SRE, Support Engineer, or Solutions Engineer role **must** include a scripting/tooling subsection. Minimum content: `bash`, `Python`, `justfile task runner`, `kubectl`, `aws-cli`. This subsection signals operational depth — the ability to triage, automate, and debug without a GUI.

**GKE onboarding signal — infrastructure and support roles:**

When the JD targets a GCP-native team (GKE, Anthos, GCP) and GCP direct experience is absent, add "GKE (actively onboarding)" to the Kubernetes subsection. This is the truthful framing — it acknowledges the gap while signalling active closure. Do not omit it and do not claim full GKE experience.

**Container hardening — placement constraint:**

Container hardening details (image scanning, non-root containers, read-only filesystems, seccomp profiles, network policy enforcement) belong in the **Security subsection only**. Do not repeat them in the Kubernetes subsection. The Kubernetes subsection covers orchestration and operations; the Security subsection covers hardening.

**Skills section depth rule — names only, no explanatory detail:**

The Skills section lists capabilities. It does not explain them. Any implementation detail that duplicates a Key Achievements or experience bullet violates the cross-section deduplication rule and wastes word budget.

- Correct: `container hardening (non-root, read-only fs, seccomp, network policy)`
- Wrong: `container hardening — image scanning, non-root containers, read-only filesystems, seccomp profiles, and network policy enforcement to restrict lateral movement`

The detail version belongs in the achievement bullet. The skills entry names the concept and the techniques in a parenthetical — one line, no verb, no outcome sentence. If the full detail is already in Key Achievements, the Skills entry must be the short form only.

**Deduplication across subsections — strict:**

Before outputting the Skills section, scan all subsections for repeated terms. Each tool or concept may appear once only. Remove every duplicate — keep the instance in the most JD-relevant subsection.

Examples of common duplications to catch:
- `ArgoCD` in both Kubernetes and CI/CD — keep in Kubernetes for K8s roles, CI/CD for DevOps roles
- `Prometheus` in both Observability and Kubernetes — keep in Observability
- `Calico CNI` in both Kubernetes and Security — keep in Kubernetes; mention network policy in Security without repeating the tool name
- `kubectl` in both Kubernetes and Scripting/Tooling — keep in Scripting/Tooling for TSE roles where operational tooling is the signal

**"portfolio-scale" is banned in the Skills section:**

Do not write "portfolio-scale", "portfolio project", or similar qualifiers inside the Skills section. Skills are capabilities, not scope claims. The scope signal is already carried by the specificity of the tools listed and the evidence in experience bullets. Adding "portfolio-scale" to a skills list signals hobby project and undersells.

If a scope qualifier is needed, use it in experience bullets only — not in the skills list itself.

---

## Step-by-Step: Cover Letter

> **Output format — cover letters are plain prose only.** No markdown headings (##, ###) anywhere in the letter. Opening, Core Value, Honest Context, and Closing are agent-internal orientation labels — they are never rendered in the output. The hiring manager receives only the letter text.

1. Open with role identity variant from [[narrative]] Section 1.2 or [[role-archetypes]].
2. Use the most relevant narrative block from [[narrative]] Section 5.
3. Select 2–3 achievement bullets from [[achievements]] that map to the JD's top 3 requirements.
4. If JD mentions AI tooling → always include Bedrock/AI content (4 applications, STRONG status).
5. If JD mentions reliability/DORA → include DORA metrics section from [[dora-metrics]].
6. If JD mentions Kubernetes internals → surface kubeadm depth and control-plane operations.
7. Close with the dual-perspective differentiator: "built the platform and deployed production workloads onto it" — no capitalised AND (see Human Writing Rules, anti-AI pattern).

**DORA metrics requirement — cover letters are not exempt from the cross-domain rule:**

The same cross-domain isolation failure that weakens resume bullets applies to cover letters. A cover letter for any infrastructure, SRE, or platform role must contain **at least two DORA-flavoured outcome statements** — not just count metrics (20+ applications, 265+ assertions).

Before finalising the Core Value paragraph:
1. Cross-reference [[concepts/dora-metrics]] for outcome evidence.
2. Identify which DORA metric is most relevant to the JD (TTSR for SRE/support roles, lead time for DevOps/platform roles, CFR for roles emphasising quality/reliability).
3. Attach the outcome to the tool mention — never list a tool without its outcome in a cover letter.

Wrong: "ArgoCD managing 20+ applications with self-healing and drift correction"
Right: "ArgoCD managing 20+ applications — automated rollback to any prior Git state, self-healing reverts within 3 minutes of drift detection"

DORA statements for cover letter use — only include if a measured value exists in [[concepts/dora-metrics]]:
- Lead time: [replace with measured GitHub Actions CI + CD job duration]
- CFR: [replace with measured value from ArgoCD rollback history]
- MTTR: [replace with timed rollback measurement]

Do not insert any of these statements until the brackets above are replaced with real values. Use qualitative outcomes in the interim: "consistent deployment cadence", "sub-minute drift correction", "infrastructure changes validated against 265+ assertions before deploy".

**GCP onboarding — evidence gate (cover letters):**

See [[gap-awareness]] GCP section. Do not claim specific GCP activities (GKE cluster deployed, Cloud IAM configured) unless confirmed evidence exists. Use "actively beginning GCP onboarding" if evidence is absent.

**"portfolio-scale" / "solo-operated" ban in cover letters:**

These qualifiers are banned from cover letter body text. In a cover letter, the framing contrast carries the scope signal:
- Wrong: "Portfolio-scale, solo-operated Kubernetes cluster, designed from first principles"
- Right: "Designed from first principles, not from a managed control plane" — the contrast implies solo depth without naming it as a limitation

If scope qualification is genuinely needed (e.g. addressing scale directly), use: "self-managed", "independently built and operated", or "built without a managed service abstraction".

**Closing paragraph rule — echo the opening thesis:**

The closing paragraph must loop back to the core framing established in the opening sentence. If the letter opened with an insight about failure-to-recovery, the close must reference it. A close that doesn't echo the opening reads as generic.

Pattern:
- Opening thesis: "X is the mental model I bring to this role"
- Closing echo: "That same [X] is what I'd bring to [specific team/role/challenge at this company]"

Never close on a gap or a forward-looking qualifier. Close on the strongest claim in the letter, restated in the language of the role.

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

> **Output boundary:** The final output is the resume or cover letter document ONLY. Never include pre-flight checklists, validation summaries, internal notes, section headers from this KB, or any agent reasoning in the output. All checklists and pre-flight steps are run silently before writing — they do not appear in the document the hiring manager receives.

These rules prevent AI-detection tools from flagging the output and ensure the text reads authentically:

1. **Before generating any bullet or paragraph, retrieve a phrase from [[voice-library]]** and use it as an anchor. This is mandatory — not optional.
2. **Banned verbs** — NEVER use: spearheaded, leveraged, orchestrated, revolutionized, streamlined, synergized, fostered, utilized. See [[voice-library]] for the full banned list.
3. **Vary sentence length** — mix short (under 12 words), medium, and long sentences. No more than 3 consecutive bullets of the same length.
4. **No consecutive same-verb openers** — if bullet 1 starts with "Built", bullet 2 cannot also start with "Built".
5. **Specific proper nouns over generic descriptions** — "Grafana Alloy", "Calico CNI", "kubeadm" NOT "monitoring collector", "network plugin", "cluster bootstrapper".
6. **Cover letters: first-person direct** — "I built X" not "X was built" or "responsible for building X".
7. **No opener clichés** — never start a cover letter with "I am writing to express my interest in". Start with the insight or the journey.
8. **Anti-AI-scan checklist** — before finalising any document, verify all items in [[voice-library]] Anti-AI-Scan Checklist.
   Additional patterns caught here (not in voice-library yet):
   - **Capitalised AND for mid-sentence emphasis** — e.g. "built the platform AND deployed workloads onto it". Fully capitalised conjunctions used as emphasis are an AI-generation signal. Use sentence structure to carry the weight instead: "built the platform, then deployed production workloads onto it — both sides of the same failure surface."
9. **Em dash (—) formatting rule — strict.**
   - Em dashes are permitted in **two places only**: date ranges (e.g. "2022–2025") and role/company separators (e.g. "Senior Engineer — AWS").
   - Em dashes used as mid-sentence connectors are **banned** in all generated resume and cover letter text.
   - Use a comma, full stop, or restructure the sentence instead.
   - Maximum one em dash per section. Multiple em dashes in a single paragraph is a strong AI-detection signal to experienced recruiters.
   - Wrong: "Built a self-managed cluster — kubeadm, Calico CNI — no managed abstractions."
   - Right: "Built a self-managed cluster via kubeadm with Calico CNI, no managed service abstractions."
10. **Professional Summary opener — NEVER cert-first.** "Certified X" or "AWS Certified X" as the first words violates the voice-library tone profile ("Action-first, not title-first"). The first sentence MUST be a role identity statement derived from the JD signal quick-map above. The certification belongs in sentence 2 or later.
11. **Professional Summary word count: 100 words maximum.** Count before outputting. Trim to fit. Never exceed 100 words.
12. **Professional Summary closing sentence — DORA metric required.** The final sentence of the summary must contain one concrete DORA-flavoured number from [[concepts/dora-metrics]]. Do not close on a gap bridge, a GCP mention, or a general differentiator. Close on a delivery metric. If no measured value exists in the KB, close on the next best concrete number (265+ CDK assertions, 13 dashboards, 20+ ArgoCD applications) — but a delivery metric is always preferred.

---

## Resume Word Count Budget — Hard Limits

Count words before outputting any section. Trim before returning. These are maximums, not targets.

| Section | Limit | Notes |
|---|---|---|
| Professional Summary | **100 words max** | Hard ceiling. Count before returning. Trim to fit. Must close on a DORA metric or concrete delivery number. |
| Experience (all roles combined) | **370 words max** | Distribute across roles by recency and relevance; most recent role gets the most words |
| Skills | **150 words max** | Subsection headers count toward the total |
| Key Projects (both combined) | **160 words max** | 80 words per project is a reasonable split |
| Key Achievements (all bullets) | **100 words max** | Maximum 4 bullets |
| Education + Certifications + Profile header | **~80 words** | Structural content — keep compact |
| **Grand Total** | **~880 words** | Count the full document before returning |

**Enforcement rule for agents:**

After generating all sections, sum the word counts. If the total exceeds 880:
1. Trim Experience first — cut the least JD-relevant bullet from the oldest role.
2. Trim Skills second — remove any tool that is not in the JD's top 5 requirements.
3. Trim Projects third — shorten the less JD-relevant project by one sentence.
4. Never trim the Key Achievements below 3 bullets. The Summary has a 100-word ceiling with no floor — trim as needed, but the closing DORA metric sentence must survive.

Do not generate and return an over-budget resume. The word count check is a required pre-flight step, not an optional post-process.

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
10. **ALWAYS add scope qualifier in experience bullets** — "solo-operated" or "self-managed" prevents overclaiming enterprise scale. Required in experience bullets only.
    **BANNED in both Professional Summary AND Skills section:** never write "portfolio-scale" or "portfolio scale" in either location. In the summary, technical specifics (kubeadm, Calico CNI, ArgoCD, 265+ CDK test assertions) carry the signal. In the skills section, specificity of tools carries the signal. "Portfolio scale" in either location signals hobby project and cancels the credibility built by the detail around it. Let the tools speak.
11. **NEVER claim "AWS Solutions Architect" or any AWS certification other than `AWS Certified DevOps Engineer – Professional`.** The only AWS certification held is `AWS Certified DevOps Engineer – Professional` (2025). Any other AWS credential — Solutions Architect Associate, Solutions Architect Professional, Developer Associate, SysOps Administrator — is a fabrication. A recruiter who checks Credly in the first 60 seconds will see only the DevOps Professional certification. Inventing a credential at the top of the resume is an immediate disqualification.
    **Profile title field rule:** the `profile.title` field must contain a role descriptor, not a credential string. Permitted examples: "Cloud Infrastructure Engineer", "DevOps Engineer", "Platform Engineer". Never write a certification name as a job title. The certification belongs in the `certifications` array and once in the summary body, nowhere else.

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
