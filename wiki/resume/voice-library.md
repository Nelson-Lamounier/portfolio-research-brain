---
title: Voice Library
type: resume
tags: [resume, voice, writing-style, ats, human-written, anti-ai, authenticity]
sources: [raw/aws_support_career_review_2026.md]
created: 2026-04-16
updated: 2026-04-16
---

# Voice Library

Nelson's authentic writing voice and language anchors. Agents: retrieve this page before generating any resume bullet or cover letter paragraph. Anchor at least one phrase per paragraph to this library.

**Why this exists:** AI-generated resume text is detectable because it draws from a shared probability distribution of "impressive-sounding" phrases. Human text is detectable because it anchors to a specific person's recurring vocabulary and sentence rhythm. This page encodes Nelson's actual rhythm — extracted from documents he wrote himself.

---

## Authentic Phrases — Use as Anchors

These are direct extracts from Nelson's own writing. They are already human. Use them as the opening or core of generated bullets, then extend with evidence.

### Action phrases (how Nelson describes what he did)

- "I took on the role of..."
- "I proactively covered [...] for fellow builders"
- "sharing my expertise to ensure..."
- "Through this initiative, I supported colleagues and helped maintain..."
- "providing timely, personalised guidance when colleagues encountered..."
- "I participated actively in [...] while managing my existing responsibilities"
- "My ability to multitask and contribute meaningfully to this cross-functional initiative"
- "I have made meaningful contributions across several key areas"
- "I chose to lean into learning as my primary response"
- "Recognising a knowledge gap, I proactively enrolled..."
- "I became a go-to resource, supporting builders through [...] and one-to-one [communication]"
- "taking responsibility for service continuity outcomes beyond my assigned workload"
- "enabling faster resolution for complex technical challenges"

### Outcome phrases (how Nelson describes the impact)

- "demonstrating my ownership mindset and commitment to team success beyond my core responsibilities"
- "enabling me to approach customer challenges with greater depth and confidence"
- "This achievement has significantly strengthened my technical foundation"
- "helping maintain consistent customer resolution timelines"
- "reflect my commitment to delivering for customers, supporting my peers, and investing in my own professional growth"

### Transition/positioning phrases

- "The transition was deliberate: [X] → [Y]"
- "built the platform AND deployed production workloads onto it"
- "understanding how systems fail → building systems that recover automatically"

---

## Tone Profile

Nelson's writing has specific tonal markers. Agents must preserve these:

| Trait | Example | NOT this |
|---|---|---|
| **Action-first, not title-first** | "I took on the role..." | "In my role as X, I..." |
| **Specific over generic** | "official channels and one-to-one Slack" | "various communication methods" |
| **Outcome-linked effort** | "covered cases [...] maintaining customer resolution timelines" | "covered cases when needed" |
| **Honest about the journey** | "lean into learning as my primary response" | "consistently excelled in all areas" |
| **Direct first-person** | "I built X" | "X was built" / "responsible for building X" |
| **Specificity in numbers** | "10–20 hours per week", "3 agents, 21 cases" | "significant hours", "several agents" |

---

## Sentence Length Variation (Anti-AI Pattern)

AI generates uniformly medium-length sentences. Human writing varies. Mix these patterns:

**Short punch (impact statement):**
> "The result: zero dropped cases during the transition period."
> "Self-hosted Kubernetes — no managed services abstractions."

**Medium evidence (most bullets):**
> "Designed and deployed HTML/CSS/JavaScript internal documentation pages for multiple AWS teams, reducing onboarding time and improving cross-team knowledge transfer over 3 years."

**Long context (intro or positioning):**
> "Coming from AWS Technical Support, where the work is diagnosing how production systems fail under pressure, every infrastructure design decision — ArgoCD self-heal, etcd DR to S3, OIDC-federated CI/CD — was informed by first-hand experience with the failure modes that surface in support escalations."

**Rule:** No more than 3 consecutive bullets of similar length. After two medium bullets, insert a short one.

---

## Banned Terms (AI Overuse)

These words appear disproportionately in AI-generated resumes. Using them increases AI-detection scores. Agents MUST NOT use these:

| Banned | Use instead |
|---|---|
| spearheaded | led, drove, initiated, built |
| leveraged | used, applied, relied on |
| orchestrated | coordinated, ran, managed |
| revolutionized | changed, improved, replaced |
| streamlined | simplified, reduced, cut |
| robust | reliable, tested, production-ready |
| seamless | smooth, uninterrupted (use sparingly — Nelson uses it once authentically) |
| cutting-edge | (just name the technology) |
| state-of-the-art | (just name the technology) |
| best-in-class | (omit — it's unverifiable) |
| results-driven | (omit — it's empty) |
| dynamic professional | (omit — always) |
| passionate about | (omit — says nothing) |
| demonstrated proficiency in | "built X" / "shipped X" / "ran X" |
| utilized | used |
| facilitate | run, enable, allow |
| synergized | (never) |
| fostered | built, developed |
| stakeholders | name them: "customers", "engineers", "management" |

---

## Verbs Nelson Actually Uses

These appear in his own writing — they are authentic to his voice:

**High frequency (authentic):** took on, supported, covered, provided, maintained, enabled, contributed, completed, helped, enrolled, participated, shared, demonstrated, strengthened

**Portfolio context:** built, configured, deployed, wrote, designed, ran, debugged, shipped, implemented, automated, tested, operated

**Rule:** Start each bullet with one of these verbs, not a banned verb. Mix them — no verb appears more than twice in any 6-bullet section.

---

## Cover Letter Voice Guidelines

For cover letters (first-person voice, more personal register):

1. **Open with the "why"** — not a summary of the CV, but the reason this role connects to the journey:
   > "The transition from AWS Technical Support to platform engineering was deliberate — ..."

2. **Use one authentic phrase from this library** in the first paragraph to anchor the voice.

3. **Middle paragraphs: specific evidence** — name specific technologies, specific numbers, specific outcomes. No generic claims.

4. **Close with the dual-perspective line** (already in [[agent-guide]]):
   > "I built the infrastructure platform AND deployed production workloads onto it — both sides of that experience inform every design decision."

5. **Avoid:** Opening with "I am writing to express my interest in..." — this is the most common AI cover letter opener and is also the most generic. Start with the insight or the journey instead.

---

## ATS Keyword Strategy

ATS systems match keywords from the JD. Rules for keyword usage:

1. **Use exact terms from the JD** — if the JD says "Kubernetes", use "Kubernetes", not "container orchestration platform". ATS matches exact strings.

2. **Certification names verbatim:**
   - `AWS Certified DevOps Engineer – Professional` ← exact (note the en-dash)
   - Never: "AWS DevOps cert", "DevOps Professional", "Amazon DevOps certification"

3. **Place keywords in context** — ATS systems have evolved to penalise keyword stuffing. A keyword appearing in a credible evidence sentence scores higher than a keyword in a list.
   - Weak (keyword stuffing): "Skills: Kubernetes, CDK, ArgoCD, Terraform"
   - Strong (keyword in context): "Bootstrapped self-managed Kubernetes clusters via kubeadm on AWS EC2 — no managed service abstractions."

4. **Section headers matter** — ATS expects: "Experience", "Skills", "Education", "Certifications". Do not use creative headers like "What I Built" or "Technical Adventures".

5. **Bullet format ATS reads best:**
   `[Strong verb] [specific technology or context] [measurable outcome]`
   Example: `Reduced EC2 node replacement time 75% (12 min → 3 min) via Golden AMI pipeline.`

---

## Anti-AI-Scan Checklist

> **AGENT-INTERNAL VALIDATION — NEVER INCLUDE IN OUTPUT.**
> Run this checklist silently before finalising any section. If all items pass, proceed to output the resume or cover letter content only. Do not output this checklist, any pass/fail summary, or any internal notes.

Verify silently:

1. No consecutive bullets start with the same verb
2. No banned terms present (check the list above)
3. At least one bullet uses a short sentence (under 12 words)
4. At least one authentic phrase from the library is present in the document
5. Specific proper nouns used (tool names, company names, numbers) — not generic descriptions
6. First-person in cover letter ("I built") not passive ("was built", "responsible for")
7. Sentence lengths vary across the document
8. No phrase like "passionate about", "results-driven", "dynamic professional"

---

## Related Pages

- [[career-history]] — work history content that applies these voice guidelines
- [[agent-guide]] — step-by-step usage instructions for resume generation
- [[narrative]] — positioning statements to anchor cover letter openings
- [[achievements]] — quantified bullets to anchor with authentic voice phrases
