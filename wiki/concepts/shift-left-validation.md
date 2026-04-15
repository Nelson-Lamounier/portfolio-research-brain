---
title: Shift-Left Validation
type: concept
tags: [devops, testing, shift-left, ci-cd, developer-experience, cdk, jest]
sources: [raw/step-function-runtime-logging.md, raw/infra_tests_architecture_review.md]
created: 2026-04-13
updated: 2026-04-14
---

# Shift-Left Validation

Push validation as early as possible in the development loop. The further left a defect is caught, the cheaper it is to fix:

```mermaid
flowchart LR
    A["Local test\n&lt; 5 seconds"] --> B["SSM dry-run\n&lt; 30 seconds"]
    B --> C["CI pipeline\n10+ minutes"]
    C --> D["Production"]
    style A fill:#22c55e,stroke:#16a34a,color:#fff
    style B fill:#84cc16,stroke:#65a30d,color:#fff
    style C fill:#f59e0b,stroke:#d97706,color:#fff
    style D fill:#ef4444,stroke:#dc2626,color:#fff
```

## The Problem

Before the local-first workflow, every change required a full pipeline round-trip:

```
Edit → commit → push → GHA triggers → CDK synth (1-2 min) → CDK deploy (2-5 min)
→ Step Functions execution (3-5 min) → CloudWatch tail = 10-15 min per iteration
```

A broken SSM preamble, wrong S3 path, or missing env var = 10 min to surface + another full cycle to fix.

## The Local-First Loop

```
Edit deploy.py → local unit tests (< 5s, no AWS)
→ sync to S3 (< 10s) → ssm-shell dry-run (< 30s)
= under 1 minute per iteration
```

Only when all local tests pass does a commit get pushed. The pipeline runs a known-good change.

## Four Testing Gates

Applied in the [[k8s-bootstrap-pipeline]]:

| Gate | Command | Time | Requires AWS? |
|------|---------|------|---------------|
| 1. Unit tests | `just deploy-test <script>` | < 5s | No |
| 2. Dry-run on node | `ssm-shell` + `--dry-run` | < 30s | Yes |
| 3. SSM document trigger | `just deploy-script <script>` | < 1 min | Yes |
| 4. Full SM-B execution | `just config-run development` | 3-5 min | Yes |

### How Unit Tests Work Without AWS

The `deploy_helpers/ssm.py` resolver checks for matching environment variables before making a boto3 API call. Setting `COGNITO_USER_POOL_ID=test-value` bypasses SSM. `_load_boto3()` is patched at module level — no AWS credentials needed.

## Immutable Infrastructure, Mutable Scripts

CDK-managed resources (SSM Documents, Step Functions, IAM) are immutable — replaced, not patched. The Python scripts they execute are mutable — they live on S3 and can be updated without re-deploying infrastructure.

`deploy-sync` exploits this boundary: push a new `deploy.py` to S3 in 10 seconds and test immediately, without touching CloudFormation.

## CDK Infrastructure Testing Tier

The same shift-left philosophy applies to CDK infrastructure changes. The [[infra-testing-strategy]] describes the full testing pyramid:

```mermaid
flowchart LR
    U["CDK unit test\nTemplate.fromStack\n&lt;1s, no AWS"] --> I["CDK integration test\nReal AWS SDK\n30–60s, post-deploy"]
    I --> P["Production deploy"]
    style U fill:#22c55e,color:#fff
    style I fill:#3b82f6,color:#fff
    style P fill:#ef4444,color:#fff
```

**Unit tests catch before CI**: a missing SSM parameter output in a CDK stack is caught by `Template.fromStack` assertions in <1s — not after a 5–15 min `cdk deploy`. A misconfigured Security Group rule is caught in the same test run.

**Integration test gates in the deploy pipeline**: [[ci-cd-pipeline-architecture]] embeds an `_integration-tests.yml` call after every CDK stack deployment. A stack that deploys successfully but leaves resources broken fails the integration gate before downstream stacks run.

**Key patterns**:
- `Template.fromStack` + `Match.objectLike` — validates semantically meaningful properties without brittle snapshot pinning
- `describe.each` — runs the same assertions against both worker pool configurations
- `it.todo()` — structured technical debt: yellow in CI, not hidden
- Negative assertions (`expect(stackMap).not.toHaveProperty('worker')`) — verify decommissioned resources stay gone

## Related Pages

- [[k8s-bootstrap-pipeline]] — project applying this concept
- [[infra-testing-strategy]] — the CDK testing pyramid in full detail
- [[ci-cd-pipeline-architecture]] — pipeline with integration test gates after every CDK deploy
- [[just]] — task runner implementing these gates
- [[k8s-bootstrap-commands]] — the specific commands
