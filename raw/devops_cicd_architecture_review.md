# DevOps CI/CD Architecture Review
## `.github/` Implementation Deep-Dive

> **Audience**: This document is written for two readers simultaneously:
> - **Nelson (Author / Learning)** — explanations include the *why* behind every design decision, the trade-offs chosen, and the concepts being applied.
> - **External Reviewer** — the document stands alone as a professional architectural review without assumed prior knowledge of the codebase.

---

## Table of Contents

1. [Repository Layout & Taxonomy](#1-repository-layout--taxonomy)
2. [Foundational Concepts Applied](#2-foundational-concepts-applied)
3. [Security Architecture](#3-security-architecture)
4. [Composite Actions (Reusable Steps)](#4-composite-actions-reusable-steps)
5. [Reusable Workflow Library (Shared Components)](#5-reusable-workflow-library-shared-components)
6. [CI Pipeline — The Quality Gate (`ci.yml`)](#6-ci-pipeline--the-quality-gate-ciyml)
7. [Tooling Infrastructure — CI Docker Image & Justfile](#7-tooling-infrastructure--ci-docker-image--justfile)
8. [Platform Orchestration Pipelines](#8-platform-orchestration-pipelines)
   - Day-1 Orchestration
   - K8s Infrastructure Deployment
   - SSM Bootstrap & Post-Bootstrap Config
   - GitOps Validation
9. [Application Deployment Pipelines](#9-application-deployment-pipelines)
   - Frontend Monorepo (Next.js + TanStack Start)
   - BFF API Services (admin-api + public-api)
   - Bedrock AI Infrastructure
   - Self-Healing Agent
10. [Operational & Maintenance Workflows](#10-operational--maintenance-workflows)
11. [Cross-Pipeline Patterns Analysis](#11-cross-pipeline-patterns-analysis)
12. [Security Posture Summary](#12-security-posture-summary)
13. [DevOps Best Practices Applied](#13-devops-best-practices-applied)
14. [Known Gaps & Future Improvements](#14-known-gaps--future-improvements)
15. [TypeScript CI Scripting Layer (`infra/scripts/ci/`)](#15-typescript-ci-scripting-layer-infrascriptsci)
    - `pipeline-setup.ts` — Pre-flight config resolution
    - `preflight-checks.ts` — Input & credential validation
    - `synthesize.ts` — CDK synth + output extraction
    - `security-scan.ts` — Checkov orchestration
16. [TypeScript CD Scripting Layer (`infra/scripts/cd/`)](#16-typescript-cd-scripting-layer-infrascriptscd)
    - `finalize.ts` — Post-deploy summary & verification
    - `observe-bootstrap.ts` — SSM Automation observer
    - `deploy-nextjs-secrets.ts` — Secrets injection via SSM
    - `verify-argocd-sync.ts` — GitOps health polling
17. [Checkov IaC Security Framework](#17-checkov-iac-security-framework)
    - Config architecture
    - Custom IAM checks (`iam_rules.py`)
    - Custom Security Group checks (`sg_rules.py`)

---

## 1. Repository Layout & Taxonomy

The `.github/` directory is organised into a strict two-tier hierarchy that separates **reusable components** from **runnable pipelines**:

```
.github/
├── actions/                    # Composite Actions (step-level reuse)
│   ├── configure-aws/          # OIDC + IAM identity masking
│   └── setup-node-yarn/        # Deterministic Node.js + Yarn toolchain
│
└── workflows/
    ├── _build-push-image.yml       # Reusable: Docker build + push to ECR
    ├── _deploy-kubernetes.yml      # Reusable: 10-stack K8s deploy graph
    ├── _deploy-ssm-automation.yml  # Reusable: Bootstrap SSM trigger
    ├── _deploy-stack.yml           # Reusable: Generic CDK deploy
    ├── _migrate-articles.yml       # Reusable: MDX → DynamoDB migration
    ├── _post-bootstrap-config.yml  # Reusable: Post-bootstrap K8s secrets
    ├── _sync-assets.yml            # Reusable: Next.js static → S3
    ├── _verify-stack.yml           # Reusable: CDK stack drift check
    │
    ├── ci.yml                      # Orchestrator: CI quality gate
    ├── day-1-orchestration.yml     # Orchestrator: Full platform bootstrap
    │
    ├── build-ci-image.yml          # Tooling: Custom CI container
    ├── deploy-api.yml              # App: BFF API Services
    ├── deploy-bedrock.yml          # App: Bedrock AI 8-stack deploy
    ├── deploy-frontend.yml         # App: Frontend monorepo
    ├── deploy-kubernetes.yml       # Entry: K8s infra (calls reusable)
    ├── deploy-org.yml              # Infra: Root account DNS role
    ├── deploy-post-bootstrap.yml   # Ops: Re-inject K8s secrets
    ├── deploy-self-healing.yml     # App: Self-healing Bedrock agent
    ├── deploy-shared.yml           # Infra: Shared VPC + ECR
    ├── deploy-ssm-automation.yml   # Entry: Bootstrap trigger
    ├── gitops-k8s.yml              # Platform: ArgoCD validation
    ├── kb-staleness-audit.yml      # Maintenance: KB freshness (monthly)
    ├── publish-article.yml         # Ops: Article pipeline readiness
    ├── sync-kb-docs.yml            # Ops: Bedrock KB document sync
    └── test-article-pipeline.yml   # QA: Article pipeline integration test
```

**Naming convention**: Files prefixed with `_` are reusable workflows (invoked via `workflow_call`). They cannot be triggered independently and carry no input validation or confirmation gates — those belong to caller pipelines.

**Total: 26 workflow files** (8 reusable, 18 runnable).

---

## 2. Foundational Concepts Applied

### 2.1 CI/CD — What It Means Here

**Continuous Integration (CI)** is the practice of automatically validating every code change before it reaches the main branch. In this project, `ci.yml` is the CI gate: it runs on every `push` to `develop` and every pull request, catching linting errors, broken CDK synth, IaC misconfigurations, and dependency drift *before* any cloud resources are touched.

**Continuous Deployment (CD)** is the automated propagation of a validated build all the way to a running environment. This project implements CD via several focused pipelines (`deploy-frontend.yml`, `deploy-api.yml`, `deploy-bedrock.yml`) that trigger on `push` to `develop` when specific path filters match. The system is **push-triggered**, meaning every commit to `develop` that touches a relevant path automatically triggers the CD pipeline for that component.

### 2.2 Separation of Concerns

The pipelines follow a deliberate **split between infrastructure and application** deployment:

| Concern | What Changes | Pipeline |
|---------|-------------|----------|
| AWS infrastructure | CDK stacks (networking, compute, IAM) | `deploy-kubernetes.yml` |
| Cluster bootstrap | User-data, kubeadm, ArgoCD init | `deploy-ssm-automation.yml` |
| Application state | K8s Secrets, ConfigMaps, IngressRoutes | `_post-bootstrap-config.yml` |
| GitOps chart state | Helm chart values, ArgoCD Applications | `gitops-k8s.yml` |
| Frontend images | Docker build + ECR push + ArgoCD | `deploy-frontend.yml` |
| BFF services | Docker build + ECR push + deploy.py | `deploy-api.yml` |

This separation prevents a simple Helm chart update from triggering an unnecessary CDK deploy, and vice versa.

### 2.3 IaC vs. GitOps Split

A key architectural decision is the **boundary between CDK-managed resources and ArgoCD-managed resources**:

- **CDK owns**: AWS-level resources — EC2, VPC, SGs, ECR, S3, DynamoDB, CloudFront, IAM roles, SSM documents.
- **ArgoCD owns**: Kubernetes-level resources — Deployments, Services, NetworkPolicies, ResourceQuotas, Rollouts.
- **`deploy.py` owns**: Sensitive K8s resources that must not be stored in Git — `Secrets` (Cognito tokens, DynamoDB keys), `IngressRoute` (domain-bound routing), `ConfigMap` (runtime environment).

This three-way split resolves the classic tension in GitOps: "how do you manage secrets without committing them to Git?" The answer here is `deploy.py` acting as a secrets broker: it reads from AWS SSM (which itself stores encrypted values), constructs Kubernetes objects in memory, and applies them directly to the cluster via `kubectl`, never writing them to the repository.

---

## 3. Security Architecture

### 3.1 OIDC — Keyless Authentication

**Concept**: OIDC (OpenID Connect) is an identity federation protocol. GitHub can act as an **identity provider**, issuing short-lived, cryptographically signed tokens that prove "this action is running in repository X, on branch Y, triggered by event Z." AWS IAM is configured to **trust** these tokens, granting a specific IAM role without any stored access keys.

**Why this matters**: Traditional CI/CD systems store `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` as long-lived secrets. If those secrets leak (via log output, environment dumps, or a compromised third-party action), an attacker gains persistent AWS access. OIDC tokens expire within minutes and are scoped to a single workflow run.

**Implementation in this project**:
- Every pipeline that needs AWS access requests `id-token: write` permission — this grants the workflow the ability to request a JWT from GitHub's OIDC endpoint.
- `aws-actions/configure-aws-credentials` exchanges the JWT for temporary AWS credentials via `sts:AssumeRoleWithWebIdentity`.
- The assumed IAM role ARN is stored as a GitHub secret `AWS_OIDC_ROLE` and scoped to the `development` environment, so only workflows running against that environment can assume it.

### 3.2 The `configure-aws` Composite Action — Identity Masking

Beyond standard OIDC, this project implements a custom `configure-aws` action that adds a **critical security layer**: masking the IAM role's unique identifier (AROA).

```yaml
# .github/actions/configure-aws/action.yml (conceptual)
- name: Mask AROA ID
  run: |
    AROA=$(aws sts get-caller-identity --query 'UserId' --output text | cut -d: -f1)
    echo "::add-mask::$AROA"
```

**Why masking the AROA matters**: AWS CloudTrail logs identify principals by their AROA (the unique persistent ID behind a role). If an attacker can see the AROA in a build log, they can cross-reference it with CloudTrail to map which resources the role has access to — this is called **IAM reconnaissance**. The `::add-mask::` GitHub Actions command replaces all subsequent occurrences of the value in log output with `***`.

This goes beyond standard practice. Most projects mask access keys; this project also masks the role's internal identity, raising the bar significantly.

### 3.3 Environment Scoping

GitHub Environments are used to enforce **approval gates and secret segmentation**:

- **`development` environment**: Contains `AWS_OIDC_ROLE`, `ALLOW_IPV4`, `ALLOW_IPV6`, `CROSS_REPO_PAT`, `VERIFICATION_SECRET`, `AWS_ACCOUNT_ID`, `AWS_REGION`, `DOMAIN_NAME`, `HOSTED_ZONE_ID`, etc.
- **`management` environment**: Contains `ROOT_ACCOUNT_ID` and a separate `AWS_OIDC_ROLE` for the root AWS account.

Workflow jobs must declare `environment: development` (or `management`) to access these scoped secrets. A workflow job without an `environment:` declaration cannot access any of these sensitive values. This means a compromised workflow cannot "promote itself" to a more privileged environment.

### 3.4 EC2 Instance ID Masking

Throughout the K8s deployment and frontend pipelines, every time the SSM proxy resolves an EC2 instance ID, it immediately masks it:

```bash
echo "::add-mask::$INSTANCE_ID"
```

**Why**: The EC2 instance ID is not itself a secret, but exposing it in public build logs reveals attack surface — a potential attacker can use it to correlate with other AWS APIs.

### 3.5 Cross-Repository PAT Scoping

The `CROSS_REPO_PAT` secret is a GitHub Personal Access Token granting read access to the private `frontend-portfolio` repository. Its usage is constrained:
- Used only in `deploy-frontend.yml` (to `checkout` the frontend source) and `_migrate-articles.yml` (sparse checkout of article MDX files).
- Never used in infrastructure or API pipelines.
- The sparse-checkout on `_migrate-articles.yml` is particularly notable — it checks out **only** `src/app/articles/`, not the entire repository, minimising the blast radius if the token were compromised.

---

## 4. Composite Actions (Reusable Steps)

### 4.1 `configure-aws`

**Purpose**: OIDC credential exchange + AROA masking.

**Inputs**: `role-to-assume` (IAM role ARN), `aws-region`.

**What it solves**: Eliminates ~10 lines of duplicated OIDC configuration from every job that needs AWS access, while ensuring the AROA masking is never accidentally omitted.

### 4.2 `setup-node-yarn`

**Purpose**: Deterministic Node.js installation + Yarn dependency cache restoration.

**Inputs**: `node-version` (optional, defaults to 22).

**What it solves**: Node.js version drift. Without a composite action, different jobs might install different Node versions. The action pins the version and restores the Yarn cache deterministically by hashing `yarn.lock`, ensuring that if lock file hasn't changed, the `node_modules` restoration is instant (~5s vs ~90s for a fresh install).

---

## 5. Reusable Workflow Library (Shared Components)

### 5.1 `_deploy-stack.yml` — The Universal CDK Deploy Worker

This is the most used building block in the entire system. **Every single CDK stack deployment in the project routes through this workflow.**

**What it does** (in order):
1. Restores cached CDK `cdk.out/` synthesised templates (avoiding redundant synth on parallel jobs).
2. Authenticates to AWS via OIDC.
3. Runs a **pre-flight diff** (`cdk diff`) to detect drift between the synthesised template and live stack state.
4. Deploys the stack (`cdk deploy --require-approval <level>`).
5. Captures CloudFormation outputs and writes them to an outputs directory (used by downstream jobs).
6. Writes a rich step summary including stack name, environment, deploy time, and output values.

**Key design decisions**:
- `require-approval` is passed as an input. For `development` it is set to `never`. For future `staging`/`production` environments it would be set to `broadening` or `any-change`, requiring a human to review resource changes before CloudFormation proceeds.
- The CDK synth output is **cached between jobs** within the same workflow run. This means a 10-stack deploy only synthesises TypeScript once (in the `setup` job), then all parallel deploy jobs restore the cached `cdk.out/`.

**Inputs API** (selective):
| Input | Purpose |
|-------|---------|
| `stack-name` | CloudFormation stack to deploy |
| `project` | CDK app project scope (`kubernetes`, `bedrock`, `shared`) |
| `environment` | GitHub Environment for secrets |
| `require-approval` | CDK approval level |
| `aws-region` | Target region (supports cross-region: edge stack deploys to `us-east-1`) |
| `timeout-minutes` | Override for long operations (e.g., Golden AMI bake: 35 min) |
| `outputs-directory` | Where to write CloudFormation outputs JSON |
| `restrict-access` | WAF IP allowlist toggle (passed to CDK context) |

### 5.2 `_deploy-kubernetes.yml` — The 10-Stack Orchestration Graph

This is the most complex reusable workflow in the project: 1,156 lines, orchestrating 10 CDK stacks with a sophisticated dependency DAG.

**The deployment graph** (in execution order):

```
setup + validate-templates + verify-bff-ecr
         │
    deploy-data
    ┌─────┴──────┐
    │            │
deploy-api    verify-data-stack
                 │
            ┌────┴────┐
          deploy-base  (deploy-api continues)
          verify-base-stack
          ┌────┬────┬────┐
  deploy-goldenami  deploy-ssm  deploy-observability
  verify-goldenami  (parallel with golden ami bake)
          │
   deploy-controlplane
   verify-controlplane
   ┌──────┴──────┐
deploy-general-pool  deploy-monitoring-pool
verify-general-pool  verify-monitoring-pool
          └──────┬──────┘
            deploy-appiam
            deploy-edge
            verify-edge
            verify-bootstrap
            summary
```

**Integration test gates**: Every stack deployment is immediately followed by a verification job that calls real AWS APIs to confirm the stack is correctly configured. For example:
- `verify-data-stack` — confirms DynamoDB table exists, S3 bucket exists, SSM parameters were published.
- `verify-base-stack` — confirms VPC CIDR, all Security Group rules are correct.
- `verify-controlplane-stack` — confirms EIP association, instance is running with the right SGs.
- `verify-general-pool-stack` / `verify-monitoring-pool-stack` — confirms Launch Template, ASG health, IAM instance profile, SSM tags.
- `verify-edge-stack` — validates CloudFront behaviour ordering (auth behaviours before `/api/*` catch-all), cookie forwarding policy, and CSRF prevention.
- `verify-bootstrap` — polls the Step Functions bootstrap orchestrator for recent executions.

**Why integration test gates?** CDK deployment success means CloudFormation accepted the template, not that the resulting resource actually works as intended. A Security Group rule can be syntactically valid but functionally wrong (wrong port, wrong protocol). The integration tests catch these logical errors immediately after deploy, before the next stack (which depends on the first) tries to use it.

### 5.3 `_deploy-ssm-automation.yml` — Bootstrap Trigger

This reusable workflow handles the cluster's "Day-1 bootstrap" — the series of actions that transform newly-launched EC2 instances into joined Kubernetes nodes.

**What it does**:
1. Syncs all Python bootstrap scripts from the Git repository to S3 (`kubernetes-app/k8s-bootstrap/`).
2. Seeds the CloudFront origin secret into SSM (a once-per-environment operation).
3. Lists all EC2 instances tagged with `k8s:bootstrap-role` and groups them into control-plane and worker pools.
4. Triggers SSM Automation documents on each instance group (control-plane first, then workers — in strict order).
5. Polls SSM Automation execution IDs until completion.
6. Calls `_post-bootstrap-config.yml` to inject application secrets.

**The SSM-Proxy pattern**: The GitHub-hosted runner never has direct network access to the private Kubernetes cluster. Instead it uses `aws ssm send-command` (AWS Systems Manager) to execute shell commands on the EC2 instances. SSM agent runs on each EC2 instance and polls AWS endpoints for pending commands — it establishes an **outbound** connection, so the K8s API server doesn't need to be publicly reachable. This is the fundamental security design of the entire cluster operation model.

### 5.4 `_post-bootstrap-config.yml` — Application Secret Injection

This workflow runs *after* cluster bootstrap is complete and handles the sensitive Kubernetes objects that cannot be stored in Git.

**Per-application operations** (each executed via SSM `send-command` → `deploy.py` on the control-plane node):

| Application | Resources Created by deploy.py |
|-------------|-------------------------------|
| `nextjs` | `nextjs-secrets` (Secret), `nextjs-config` (ConfigMap), `nextjs` (IngressRoute) |
| `admin-api` | `admin-api-secrets` (Secret), `admin-api-config` (ConfigMap), `admin-api` (IngressRoute) |
| `public-api` | `public-api-config` (ConfigMap), `public-api` (IngressRoute) |
| `start-admin` | `start-admin-secrets` (Secret), `start-admin-config` (ConfigMap), `start-admin` (IngressRoute) |

**Why `deploy.py` and not ArgoCD?** ArgoCD reads from Git. Storing Kubernetes Secrets in Git — even encrypted — is a security smell. `deploy.py` acts as a bridge: it pulls plaintext credentials from AWS SSM (which uses KMS encryption at rest), constructs the Kubernetes objects in memory on the control-plane node, applies them with `kubectl`, and leaves no trace in the Git history.

**ArgoCD health verification**: After all secrets are applied, the workflow polls the ArgoCD API (via a bot token stored in AWS Secrets Manager by the bootstrap process) and confirms all Applications reach `Synced + Healthy` state. This is the final confirmation that the entire GitOps stack is operational.

### 5.5 `_sync-assets.yml` — Static Asset Pipeline

Handles the specific requirement of Next.js's static file strategy: `.next/static/` (CSS, JS bundles with content hashes) must be served directly from CloudFront/S3, not from the Next.js server, for performance.

**Two code paths** (shows evolution over time):
1. **Fast path** (current): The build job extracts `.next/static/` from the Docker container at build time and caches it separately. The sync job restores this lightweight cache directly — no Docker layer manipulation needed.
2. **Legacy path** (fallback): Restores the full Docker image tar, `docker load`s it, creates a temporary container, `docker cp`s the static directory out, then cleans up. This is much slower (~45s) but maintained for callers that haven't migrated.

The fast path reduces the asset sync job from ~5 minutes to ~60 seconds. The legacy path is preserved for backward compatibility through the configurable `static-cache-key-prefix` / `image-cache-key-prefix` inputs.

### 5.6 `_build-push-image.yml` — Docker Build & ECR Push

Generic reusable workflow for building a Docker image and pushing to ECR. Accepts image tag, Dockerfile path, and cache scope as inputs. Uses `docker/build-push-action@v6` with GitHub Actions cache (GHA cache) for Docker layer caching.

### 5.7 `_migrate-articles.yml` — Content Migration

Reusable workflow that runs the TypeScript migration script `migrate-articles-to-dynamodb.ts`. Performs a **sparse checkout** of the private `frontend-portfolio` repo (only `src/app/articles/` is fetched) and runs the idempotent migration followed by a verification step.

**Idempotency is key**: The migration script checks whether each article already exists in DynamoDB before writing. Calling it on every deployment is safe — it only writes new or modified articles.

### 5.8 `_verify-stack.yml` — Stack Drift Detection

A lightweight reusable workflow (only 2,554 bytes) that runs `cdk diff` against a live stack to detect configuration drift between the Git-committed template and the live CloudFormation state. Used as a non-blocking gate in the CI pipeline.

---

## 6. CI Pipeline — The Quality Gate (`ci.yml`)

**File size**: 703 lines. **Purpose**: Protect the `develop` branch from broken commits.

**Trigger**: Every `push` to `develop`, every PR targeting `develop`, and manual dispatch.

### 6.1 Change Detection — The Monorepo Optimisation

The first job in `ci.yml` runs `dorny/paths-filter`:

```yaml
detect-changes:
  steps:
    - uses: dorny/paths-filter@v3
      id: changes
      with:
        filters: |
          infra: ['infra/**', '.github/workflows/**']
          kubernetes: ['kubernetes-app/**']
          frontend: ['frontend-ops/**', 'api/**']
          bedrock: ['bedrock-applications/**']
```

Every downstream CI job checks `needs.detect-changes.outputs.<scope> == 'true'` before running. A commit that only touches `api/admin-api/` skips all infra linting, stack tests, and Kubernetes validation. This reduces median CI time from ~12 minutes to ~3 minutes for focused changes.

**Concept applied**: This is the **fan-out** pattern for monorepo CI — a single dispatcher job fans out to multiple independent validation paths, each gated on path-filter results.

### 6.2 Workflow Linting (`actionlint`)

```yaml
lint-workflows:
  runs-on: ubuntu-latest
  steps:
    - uses: rhysd/actionlint@v1
```

`actionlint` is a static analysis tool for GitHub Actions workflow files that catches:
- Incorrect expression syntax (`${{ }}`)
- Missing required inputs on `workflow_call`
- Invalid `needs:` references
- Incorrect `permissions:` declarations

Linting the CI configuration files themselves prevents a class of "the CI pipeline doesn't run because of a syntax error in the CI config" failures that are otherwise only discovered when a PR is opened.

### 6.3 CDK Stack Tests

```yaml
test-stacks:
  container:
    image: ghcr.io/nelson-lamounier/cdk-monitoring/ci:latest
  steps:
    - run: just test-stacks
```

Runs Jest-based unit tests on the CDK constructs and stacks. These are **pure TypeScript unit tests** using CDK's `assertions` library — they synthesise stacks in memory and assert on the resulting CloudFormation template structure without touching any AWS APIs.

**Example assertions**:
- "The Security Group has exactly one ingress rule for port 443 from `0.0.0.0/0`"
- "The DynamoDB table has point-in-time recovery enabled"
- "The Lambda function has a dead-letter queue"

These catch logical mistakes in the CDK code before deployment.

### 6.4 CDK Synthesis Validation

```yaml
validate-cdk-synth:
  steps:
    - run: just ci-synth kubernetes development
    - run: just ci-synth bedrock development
    - run: just ci-synth shared development
```

Performs a full CDK synthesis for all three project scopes and fails if any TypeScript compilation error or CDK construct validation error is thrown. This is the "does the IaC compile?" check before running tests or deploying.

### 6.5 IaC Security Scanning (Checkov)

```yaml
security-scan:
  steps:
    - uses: bridgecrewio/checkov-action@v12
      with:
        directory: infra/cdk.out/
        framework: cloudformation
        soft_fail: true
```

[Checkov](https://www.checkov.io) scans the synthesised CloudFormation templates against a library of 1,000+ security and compliance checks. Examples of checks relevant to this project:
- "EC2 instances should use IMDSv2 (not v1)"
- "KMS encryption should be enabled on EBS volumes"
- "CloudFront distributions should have WAF enabled"
- "S3 buckets should have public access blocked"

`soft_fail: true` means Checkov failures produce warnings rather than blocking the pipeline. This is appropriate while the project is in active development — the intent is visibility, not a hard gate.

### 6.6 Dependency Validation

```yaml
validate-dependencies:
  steps:
    - run: yarn install --immutable
```

The `--immutable` flag on `yarn install` fails if `package.json` has been modified but `yarn.lock` has not been updated to match. This catches the common mistake of manually editing a dependency version without running `yarn install` to regenerate the lock file — which would cause non-deterministic builds in production.

---

## 7. Tooling Infrastructure — CI Docker Image & Justfile

### 7.1 Custom CI Container (`build-ci-image.yml`)

**File size**: 91 lines. **Published to**: `ghcr.io/nelson-lamounier/cdk-monitoring/ci:latest`

**Why a custom image?** GitHub-hosted runners start with a generic `ubuntu-latest` image. Installing Helm, cfn-lint, kubectl, Just, and the correct Node version on every job wastes ~3 minutes per job. The custom image bakes all these tools in at image build time — every job that uses it starts with a fully-provisioned toolchain in seconds.

**Contents of the CI image**:
| Tool | Version | Purpose |
|------|---------|---------|
| Node.js 22 | Fixed | CDK synthesis, Jest tests |
| Just | Latest | Command runner (task orchestrator) |
| Helm | 3.x | Kubernetes chart validation |
| `cfn-lint` | Latest | CloudFormation template linting |
| `kubectl` | 1.29 | K8s operations (in validate jobs) |
| `checkov` | Latest | IaC security scanning |
| AWS CLI v2 | Latest | Stack verification |
| Python 3 | 3.12 | deploy.py, bootstrap scripts |

**Trigger**: `push` to `develop` when `Dockerfile` or `.github/workflows/build-ci-image.yml` changes. **Published to GHCR** (GitHub Container Registry), which integrates seamlessly with GitHub Actions authentication — no separate registry credentials needed.

### 7.2 Justfile — The Infrastructure Task Runner

The `Justfile` at the repository root defines named tasks (called "recipes") that unify local development commands and CI commands. Every `run: just <recipe>` in a workflow maps to the same command a developer runs locally.

**Key recipes used in pipelines**:
| Recipe | What It Does |
|--------|-------------|
| `just build` | TypeScript compile (tsc) |
| `just test-stacks` | Jest unit tests |
| `just ci-synth <project> <env>` | CDK synthesis + stack name extraction |
| `just ci-integration-test <suite> <env>` | Jest integration tests against live AWS |
| `just ci-pipeline-setup` | Resolve + validate + mask pipeline config |
| `just helm-validate-charts` | `helm lint` on all charts |
| `just ci-verify-argocd` | Poll ArgoCD API for sync health |
| `just ci-summary <project> <env>` | Generate Markdown summary |
| `just ci-failure-report` | Generate CloudFormation failure diagnostics |
| `just ci-log-audit` | Audit CloudWatch Log Group retention |

This pattern is a DevOps best practice called **runbook codification** — operational procedures defined as code, testable locally, and guaranteed to behave identically in CI.

---

## 8. Platform Orchestration Pipelines

### 8.1 Day-1 Orchestration (`day-1-orchestration.yml`)

**Purpose**: The single source of truth for deploying the entire platform from scratch on a new environment.

**Trigger**: Manual-only (`workflow_dispatch`) with two safety gates:
1. Must type `"DEPLOY-DAY1"` in an explicit confirmation input.
2. Environment is restricted to `development` — `staging` and `production` are explicitly rejected with an error.

**Concurrency**: `cancel-in-progress: false` — if a Day-1 run is already in progress, new triggers are queued, not cancelled. This prevents split-brain state where two parallel bootstraps fight over the same resources.

**Phase structure**:

```
Gate (validate + resolve stack names)
  │
  ├── Phase 1a: Shared VPC + ECR    ─┐
  ├── Phase 1b: Security Baseline    ├─ parallel
  └── Phase 1c: FinOps               ┘
              │
         Phase 2: K8s Infrastructure (10 stacks)
              │
         Phase 3: SSM Bootstrap (scripts + cluster init)
              │
         Phase 4: GitOps Validation (ArgoCD sync check)
              │
         Phase 5: Summary
```

**Each phase is independently toggleable** via boolean inputs (`deploy-shared`, `deploy-kubernetes`, `deploy-ssm`, `deploy-gitops`). This enables selective re-runs — for example, if Phase 3 fails, you can re-run with only `deploy-ssm=true` without re-deploying all CDK stacks.

**Phase gating with `always()` + result checks**: Each phase's `if:` condition uses:
```yaml
if: >-
  always()
  && inputs.deploy-kubernetes
  && (needs.deploy-shared.result == 'success' || needs.deploy-shared.result == 'skipped')
```

The `always()` ensures the `if:` condition is evaluated even when upstream jobs are skipped. The `|| 'skipped'` allows individual phases to be skipped (via their boolean toggle) without blocking downstream phases.

### 8.2 K8s Infrastructure Deployment (`deploy-kubernetes.yml` + `_deploy-kubernetes.yml`)

`deploy-kubernetes.yml` is a thin 53-line entry point that sets concurrency group (`deploy-k8s-{env}`) and calls `_deploy-kubernetes.yml`. The reusable workflow does the actual work (documented in §5.2).

**Notable job: `deploy-observability`** (the CloudWatch dashboard stack):

```
Depends on: deploy-base + verify-base-stack
Cost: $3.00/month
Purpose: Pre-K8s monitoring bridge
```

This stack was created during the **initial development phase**, before the in-cluster Prometheus/Grafana stack was operational. It deployed a CloudWatch-native dashboard showing EC2 instance health, EBS metrics, and basic K8s node metrics — enough to diagnose cluster issues during bootstrap. Once the Prometheus stack was stable, CloudWatch was retained but superseded for application-level observability. This is a concrete example of evolutionary architecture: the bridge technology stays in place until the destination is confirmed stable.

**Notable job: `deployment-failure-alert`**:

```yaml
if: >-
  always()
  && (needs.deploy-controlplane.result == 'failure' || ...)
  && inputs.cdk-environment != 'development'
```

This job only fires for `staging`/`production` failures. For `development`, failures are expected during rapid iteration and don't warrant an alert. For production, a failure triggers `just ci-failure-report` which queries CloudFormation events, extracts the stack rollback reason, and writes a structured incident report to the step summary.

### 8.3 SSM Bootstrap (`deploy-ssm-automation.yml` + `_deploy-ssm-automation.yml`)

`deploy-ssm-automation.yml` is the standalone entry point for **Day-2+ cluster operations** — triggering bootstrap without redeploying CDK stacks.

**Trigger**: Push to `develop` when `kubernetes-app/k8s-bootstrap/**` changes, or manual dispatch.

This enables live patching of the bootstrap Python scripts without going through a 45-minute CDK deploy cycle. A developer pushes a fix to `boot-k8s.sh`, the pipeline syncs only the S3 content, and triggers a re-bootstrap of all nodes.

### 8.4 GitOps Validation (`gitops-k8s.yml`)

**Concurrent usage**: This workflow serves dual purpose:
1. **Called by `day-1-orchestration.yml`** as the final platform validation gate (Phase 4).
2. **Standalone** for ArgoCD health verification after chart changes.

**Jobs**:

1. **`build-steampipe-image`**: The official Steampipe Docker image (v0.22.0) had a bug (OCI registry 403 error) preventing AWS plugin installation. Rather than waiting for an upstream fix, a custom Steampipe image is built from a pinned v2.4.0 binary with the AWS plugin pre-baked. This is an example of **vendoring** a broken upstream dependency to unblock progress.

2. **`validate`**: Uses the custom CI container to run `just helm-validate-charts` (Helm lint on all charts) and a custom Python YAML validator across all `values*.yaml` files. Catches syntax errors *before* ArgoCD auto-syncs them to the cluster.

3. **`verify-argocd`**: Polls the ArgoCD API via `just ci-verify-argocd` to confirm all Applications are `Synced + Healthy`. Non-blocking (informational) — after a Git push, ArgoCD takes ~3 minutes to auto-sync; this job documents the post-push health without blocking the developer.

---

## 9. Application Deployment Pipelines

### 9.1 Frontend Monorepo (`deploy-frontend.yml`)

**File size**: 1,125 lines. This is the most complex application pipeline in the project.

**The monorepo problem**: The `frontend-portfolio` private repository contains two independent applications:
- `apps/site/` — Next.js 15 SSR application (public portfolio)
- `apps/start-admin/` — TanStack Start admin dashboard (private `/admin/` route)

Each app has a separate Docker image, ECR repository, Kubernetes namespace, and Argo Rollout. They can be deployed independently.

**Trigger logic** (`resolve-targets` job):

```
Push to develop with specific apps → dorny/paths-filter on frontend-portfolio
Manual dispatch → explicit app selector input: 'site' | 'admin' | 'both'
Repository dispatch → client_payload.deploy-site, client_payload.deploy-admin
```

The repository dispatch trigger is particularly important: it allows the `frontend-portfolio` repo to trigger this pipeline on push to *its* `main` branch, without storing CD logic in the frontend repo itself. This is cross-repository CD via an event-driven `repository_dispatch` webhook.

**Deployment flow (Next.js site)**:

```
resolve-targets
    │
    ├── build-site (Docker build + layer cache + artifact extraction)
    │   ├── Extract .next/static/ to GHA cache (fast path for sync-assets)
    │   └── Save full image tar to GHA cache
    │
    ├── push-site (OIDC → ECR login → tag → push)
    ├── sync-assets (calls _sync-assets.yml: .next/static → S3 + CF invalidate)
    ├── deploy-site (OIDC → SSM put /nextjs/development/image-uri)
    │
    └── promote-site (SSM send-command → control-plane → kubectl-argo-rollouts)
```

**The Argo Rollouts promotion via SSM**:

```bash
# Running on the GitHub-hosted runner:
SCRIPT='
  sudo kubectl argo rollouts get rollout nextjs -n nextjs-app | grep Status | awk "{print $NF}"
  # Poll for "Paused" (green RS deployed, waiting for promotion)
  # kubectl argo rollouts promote nextjs -n nextjs-app
  # Poll for "Healthy"
'
aws ssm send-command \
  --instance-ids "$INSTANCE_ID" \
  --document-name "AWS-RunShellScript" \
  --parameters "$(printf '%s' "$SCRIPT" | jq -Rs '{commands:[.]}')"
```

**Why `jq -Rs`?** The shell script is a multi-line string containing special characters. The AWS CLI parameter parser requires a valid JSON string. `jq -Rs` encodes the raw string (`-R`) into a JSON-escaped single-line string (`-s`), producing literal newlines encoded as `\n`. Without this, the AWS CLI would choke on literal newlines.

**Blue/Green rollout cycle**:
1. Image URI is updated in SSM → ArgoCD Image Updater detects the change.
2. Argo Rollouts starts a new `green` ReplicaSet with the new image.
3. Analysis runs (configurable via `AnalysisTemplate` — in this case, `step: pause` causes the rollout to pause automatically).
4. Pipeline polls for `Paused` state (max 6 minutes: 24 × 15s).
5. Pipeline calls `kubectl argo rollouts promote` via SSM.
6. Traffic shifts to green RS; `blue` RS is scaled down.
7. Pipeline confirms `Healthy` state.

**Admin app — CloudFront cache invalidation** (`invalidate-admin` job):

TanStack Start uses Vite for bundling. Vite generates content-hashed asset filenames (e.g., `assets/index-CUbdlrCg.js`). After every deploy, the HTML references new hash-named assets. If CloudFront caches the old HTML, browsers request the old asset hashes which no longer exist — resulting in 404 errors for all CSS/JS.

The solution is to **invalidate `/admin/*` and `/admin/assets/*`** in CloudFront immediately after the Rollout promotion completes. The pipeline calls `aws cloudfront create-invalidation` and then waits for it to complete (`aws cloudfront wait invalidation-completed`) before the job succeeds.

**Article migration (`migrate-articles` job)**:

Runs in parallel with both deployment paths. It is independent — it doesn't need the Docker image to be deployed. It reads MDX article files from `frontend-portfolio/src/app/articles/` and writes them idempotently to DynamoDB. Controlled by:
- `inputs.skip-migration` (manual override)
- `github.event.client_payload.migrate == true` (for repository dispatch events, only migrate when explicitly requested)

### 9.2 BFF API Services (`deploy-api.yml`)

**File size**: 845 lines. Deploys two Node.js BFF (Backend for Frontend) services from *this* repository (no cross-repo checkout needed).

**Applications**:
- `admin-api` — Cognito-protected write API (article management, S3 asset upload, Bedrock Lambda orchestration)
- `public-api` — Public read API (article listing, slug resolution, subscription webhook, healthcheck)

**Parallel deployment** (no ordering between services):
```
resolve-targets
  ├── build-admin-api → push-admin-api → deploy-admin-api
  └── build-public-api → push-public-api → deploy-public-api
                                               │
                                         summary (always)
```

**Critical difference from frontend**: BFF services use plain Kubernetes `Deployments` (not Argo Rollouts). ArgoCD detects the updated `image-uri` SSM parameter via Image Updater and performs a rolling update automatically — no pipeline-driven promotion step is needed.

**`deploy-admin-api` job — three operations**:

1. **Write image URI to SSM** → ArgoCD Image Updater picks it up within ~2 minutes.
2. **Sync deploy scripts to S3** → ensures the control-plane runs the version of `deploy.py` from *this exact commit*.
3. **Run `admin-api deploy.py` via SSM** → creates/updates the Kubernetes Secret, ConfigMap, and IngressRoute.
4. **Force ArgoCD sync via SSM** → immediately triggers ArgoCD to reconcile the app rather than waiting for the 2-minute polling cycle.

**The S3 script sync before SSM execution** is a subtle but important pattern. Without it, the control-plane instance might run an older version of `deploy.py` that was staged from a previous pipeline run. By syncing scripts to S3 *and* fetching them fresh inside the SSM command, the pipeline guarantees the running script version matches the commit that triggered the pipeline — true **immutable deployment semantics** for scripts.

### 9.3 Bedrock AI Infrastructure (`deploy-bedrock.yml`)

**File size**: 207 lines. Deploys the 8-stack Bedrock AI architecture.

**Stack dependency graph**:
```
deploy-data (S3 bucket)
  ├── deploy-kb (Knowledge Base + Pinecone)
  ├── deploy-agent (Bedrock Agent)             → deploy-api (API Gateway)
  ├── deploy-content (DynamoDB)
  │         └── deploy-pipeline (Step Functions: Research → Writer → QA)
  └── deploy-strategist-data (DynamoDB)
            └── deploy-strategist-pipeline (Analysis SM + Coaching SM)
```

**Why `workflow_dispatch` only (push trigger commented out)**: The Bedrock infrastructure is expensive and slow to deploy (Lambda bundling, Bedrock Knowledge Base sync, Pinecone index configuration). Deploying it on every `develop` push would both increase AWS costs and slow down the development feedback loop. The push trigger exists in the code but is commented out — it can be re-enabled when the project reaches a maturity level where automated Bedrock redeploys make sense.

**Stateful stack lifecycle**: The `Bedrock-Data` stack (S3 bucket) must be deployed before all others because the S3 bucket name is passed as a parameter to multiple downstream stacks. Separation of the S3 data layer from the application stacks (`Bedrock-Kb`, `Bedrock-Agent`) follows the IaC principle of **separating stateful resources from stateless compute** — you can destroy and recreate the Agent and API stacks without risking data loss.

### 9.4 Self-Healing Agent (`deploy-self-healing.yml`)

**File size**: 112 lines. Deploys the 2-stack Bedrock AgentCore self-healing architecture.

**Architecture**:
1. `SelfHealing-Gateway` — AgentCore Gateway (MCP tool server). Registers Lambda functions (cluster health checks, ArgoCD queries, SSM command dispatchers) as MCP-compatible tools with Cognito M2M authentication.
2. `SelfHealing-Agent` — Bedrock ConverseCommand Lambda (MCP client). Triggered by EventBridge alarms, invokes the Gateway's tools to diagnose and remediate cluster failures.

**Push trigger** (active): Unlike `deploy-bedrock.yml`, the self-healing pipeline fires on every `develop` push that touches `infra/lib/stacks/self-healing/**` or `bedrock-applications/self-healing/**`. This reflects a more mature deployment lifecycle where automated redeploys are acceptable.

**Post-deploy smoke test**: After `deploy-agent` completes, `smoke-test` runs `just ci-integration-test self-healing development`. This calls real AWS APIs to verify:
- SSM parameters are populated (gateway URL, agent Lambda ARN)
- Lambda functions exist and are `Active`
- EventBridge rules are correctly configured
- SQS dead-letter queue is wired

---

## 10. Operational & Maintenance Workflows

### 10.1 Deploy Post-Bootstrap (`deploy-post-bootstrap.yml`)

**Purpose**: Re-run only Phase 3B of the Day-1 process — inject application secrets without triggering a full cluster bootstrap.

**Use case**: When a Cognito client secret is rotated, or a DynamoDB table ARN changes, this pipeline re-runs `deploy.py` for all applications and verifies ArgoCD health. No CDK deployment, no cluster restart.

**Trigger**: Manual dispatch only.

### 10.2 Deploy Shared VPC (`deploy-shared.yml`)

Entry-point wrapper for deploying only the Shared VPC, Security Baseline, and FinOps stacks independently of the Day-1 orchestration. Useful for updating WAF rules (which live in the Shared stack) without touching any cluster infrastructure.

### 10.3 Deploy Organisation Resources (`deploy-org.yml`)

Manages infrastructure in the **AWS root/management account** — specifically the cross-account IAM role that allows the development account to create Route 53 DNS records in the root account's hosted zone (for ACM certificate DNS validation).

**Confirmation gate**: Requires typing `"DEPLOY-ORG"` explicitly. Root account changes have a wider blast radius than development account changes — this gate forces intentionality.

### 10.4 Sync KB Docs (`sync-kb-docs.yml`)

Syncs documents to the Bedrock S3 Knowledge Base bucket (used by the AI content pipeline for RAG retrieval) without deploying any CDK stacks. Useful when the knowledge base content changes but the infrastructure hasn't.

### 10.5 Test Article Pipeline (`test-article-pipeline.yml`)

Integration tests for the Bedrock article generation pipeline (Step Functions: Research → Writer → QA → Publish). Verifies that a Step Functions execution reaches completion and produces a valid article, using mocked Bedrock responses where possible to reduce cost.

### 10.6 Verify Article Pipeline (`publish-article.yml`)

Pre-flight readiness check for the article pipeline. Queries live SSM parameters, Step Functions, all 5 agent Lambdas, DynamoDB, and S3 to confirm everything is correctly deployed before the admin dashboard attempts to trigger article generation. Writes a rich Markdown readiness report to the step summary.

### 10.7 KB Staleness Audit (`kb-staleness-audit.yml`)

**Trigger**: CRON schedule — 1st of every month at 09:00 UTC.

Scans all `knowledge-base/*.md` files for a `last_updated:` frontmatter field. Any document not updated in >90 days is flagged. If stale documents exist, a GitHub Issue is automatically created (via `peter-evans/create-issue-from-file`) with the full report, labelled `documentation`, `knowledge-base`, `maintenance`.

This transforms documentation freshness from a manual discipline into an automated audit with an actionable ticket. The `/kb-sync` workflow (triggered manually) is the prescribed remedy for resolving these issues.

---

## 11. Cross-Pipeline Patterns Analysis

### 11.1 SSM as a Configuration Bus

SSM Parameter Store serves as the **cross-service configuration bus** throughout the entire system:

| SSM Namespace | Published By | Consumed By |
|---------------|-------------|------------|
| `/shared/ecr-*/repository-uri` | CDK SharedVpcStack | deploy-frontend, deploy-api |
| `/k8s/{env}/scripts-bucket` | CDK DataStack | _deploy-ssm-automation, deploy-api |
| `/nextjs/{env}/image-uri` | deploy-frontend | ArgoCD Image Updater |
| `/admin-api/{env}/image-uri` | deploy-api | ArgoCD Image Updater |
| `/k8s/{env}/cloudfront-origin-secret` | _deploy-ssm-automation | CDK EdgeStack |
| `/nextjs/{env}/cloudfront/distribution-id` | CDK EdgeStack | deploy-frontend (invalidation) |

**Why SSM instead of CloudFormation cross-stack references?** CloudFormation cross-stack references (`Fn::ImportValue`) are compile-time dependencies. If Stack A exports a value and Stack B imports it, you cannot delete Stack A without first updating Stack B. SSM parameters are runtime dependencies — looser coupling that allows stacks to be deployed, updated, and deleted independently. When a stack needs a value from another stack, it reads from SSM at deploy time rather than being structurally coupled.

### 11.2 Image Tag Strategy

Every pipeline that builds a Docker image uses the composite tag:
```
IMAGE_TAG = "${github.sha}-r${github.run_attempt}"
```

**Why the run-attempt suffix?** `github.sha` is the commit hash — it's unique per commit but *not* per pipeline run. If a pipeline fails at the ECR push step and is re-run, without the `-r${run_attempt}` suffix, it would try to push the same tag again. ECR allows overwriting tags, which is dangerous (an old image layer cache could be reused, silently deploying stale layers). The run-attempt suffix makes every build attempt produce a unique, immutable tag. This is the **immutable artifact principle** applied to container images.

### 11.3 Concurrency Configuration

| Pipeline | Concurrency Group | Cancel-in-progress |
|----------|------------------|-------------------|
| `deploy-frontend` | `deploy-frontend-{ref}` | `true` |
| `deploy-api` | `deploy-api-{ref}` | `true` |
| `deploy-kubernetes` | `deploy-k8s-{env}` | `false` |
| `deploy-ssm-automation` | `deploy-ssm-{env}` | `false` |
| `day-1-orchestration` | `day-1-orchestration-{env}` | `false` |

**Pattern**: Application pipelines use `cancel-in-progress: true` — if a newer commit arrives while a deploy is in progress, cancel the old deploy and start fresh with the latest code. This is safe for stateless application containers.

Infrastructure pipelines use `cancel-in-progress: false` — a CloudFormation stack deployment in progress must complete (or fail) before the next one starts. Cancelling mid-deploy leaves CloudFormation in a `ROLLBACK_IN_PROGRESS` state that requires manual intervention.

### 11.4 Pinned Action Versions

Every `uses:` reference in the codebase uses a pinned commit SHA, not a floating tag:
```yaml
uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2
uses: actions/cache/save@cdf6c1fa76f9f475f3d7449005a359c84ca0f306 # v5.0.3
```

**Why**: GitHub Actions published to the marketplace are mutable by their authors. A malicious or negligent action update to `v6` could compromise all pipelines that use `@v6`. Pinning to a commit SHA freezes the exact code being executed, making the pipeline immune to supply-chain attacks on upstream action dependencies. The `# v6.0.2` comment preserves human readability.

### 11.5 GitHub Step Summaries

Every significant job writes a structured Markdown report to `$GITHUB_STEP_SUMMARY`. These appear as rich reports directly on the GitHub Actions run page, eliminating the need to parse log files to understand deployment outcomes.

Examples:
- `deploy-admin-api` writes: SSM parameter name, image tag.
- `promote-site` writes: Rollout name, namespace, promotion status.
- `verify-data-stack` writes: DynamoDB table status, S3 bucket status, SSM parameters found.
- `day-1-orchestration` writes: A full phase-by-phase table with `success`/`skipped`/`failure` for every job.

---

## 12. Security Posture Summary

| Control | Implementation | Strength |
|---------|---------------|----------|
| Keyless authentication | OIDC (`id-token: write`) | ✅ Industry standard |
| IAM identity masking | Custom `configure-aws` action (AROA mask) | ✅ Above standard |
| Environment secret scoping | GitHub Environments | ✅ Standard |
| EC2 instance ID masking | `::add-mask::` per pipeline | ✅ Above standard |
| No K8s API public exposure | SSM proxy for all kubectl | ✅ Best practice |
| Secret-free GitOps | `deploy.py` + SSM SecureString | ✅ Best practice |
| Immutable image tags | `sha-rAttempt` composite | ✅ Best practice |
| Pinned action versions | Commit SHA on all actions | ✅ Supply chain hardened |
| IaC security scanning | Checkov (soft_fail) | ⚠️ Soft fail (not blocking) |
| Cross-repo minimal access | Sparse checkout for articles | ✅ Least privilege |
| Root account deployment gate | `"DEPLOY-ORG"` typed confirmation | ✅ High friction by design |
| Day-1 deployment gate | `"DEPLOY-DAY1"` confirmation | ✅ High friction by design |

---

## 13. DevOps Best Practices Applied

| Practice | Where Applied |
|----------|---------------|
| **Infrastructure as Code** | All AWS resources via CDK TypeScript |
| **GitOps** | ArgoCD manages all K8s state from this Git repo |
| **Immutable infrastructure** | EC2 nodes are never patched; replaced via ASG with new Golden AMI |
| **Separation of duties** | Infrastructure pipelines vs. application pipelines are independent |
| **Monorepo orchestration** | `dorny/paths-filter` + separate concurrency groups per component |
| **Shift-left security** | Checkov + cfn-lint + unit tests run before any deployment |
| **Runbook codification** | All operational procedures captured as `just` recipes |
| **Idempotency** | All deploy scripts (`deploy.py`, article migration) are safe to re-run |
| **Observability** | Step summaries on every job; failure alert job for production |
| **Blast radius control** | Separate environments, separate OIDC roles, minimal IAM policies |
| **Progressive delivery** | Argo Rollouts Blue/Green for frontend applications |
| **Continuous verification** | Integration test gates between every CDK stack deployment |

---

## 14. Known Gaps & Future Improvements

| Gap | Current State | Suggested Improvement |
|-----|--------------|----------------------|
| Checkov soft-fail | Findings are visible but non-blocking | Harden specific checks to `hard_fail` as false-positives are triaged |
| `gitops-k8s.yml` push trigger | Commented out | Re-enable with `paths-filter` gating once Day-1 is stable |
| `deploy-bedrock.yml` push trigger | Commented out | Enable when Bedrock stack is mature enough for automated deploys |
| ArgoCD Image Updater latency | ~2 min polling + force-sync workaround | Investigate ArgoCD webhook trigger for immediate sync |
| Manual article migration | Runs on every frontend deploy | Move to event-driven trigger from the Bedrock pipeline |
| No staging environment | `development` serves as production | Implement `staging` environment with separate CDK context before going fully public |
| Bootstrap re-entrancy | Re-running Day-1 on a live cluster is risky | Add idempotency checks to bootstrap scripts (check if `kubeadm init` already ran) |

---

## 15. TypeScript CI Scripting Layer (`infra/scripts/ci/`)

> **The Core Idea**: This project replaces inline Bash in GitHub Actions `run:` blocks with typed, documented, testable TypeScript scripts. Each script is a self-contained executable with structured argument parsing, validated inputs, masked outputs, and deterministic exit codes. The pipelines call them via `just` recipes, ensuring identical behaviour locally and in CI.

The `@repo/script-utils` shared package provides all scripts with a common foundation:
- `logger.ts` — Structured logging with `header`, `keyValue`, `table`, `success`, `warn`, `error`, and `step` formatters.
- `github.ts` — `setOutput`, `writeSummary`, `emitAnnotation`, `maskSecret` — abstractions over GitHub Actions protocol commands.
- `aws.ts` — `parseArgs`, `buildAwsConfig` — standardised argument parsing and AWS credential resolution.
- `cdk.ts` — `readStackOutputs` — parse CloudFormation outputs JSON from `cdk.out`.
- `exec.ts` — `runCommand`, `runCdk`, `buildCdkArgs` — subprocess execution with exit code capture.

---

### 15.1 `pipeline-setup.ts` — Pre-flight Configuration Resolution

**Called by**: `just ci-pipeline-setup` (used in `_deploy-kubernetes.yml` setup job).

**What it solves**: Before this script existed, every pipeline had ~30 lines of inline Bash that:
1. Ran `git log` to extract the commit SHA and message.
2. Called `aws sts get-caller-identity` to confirm the correct AWS account.
3. Read multiple SSM parameters to resolve the CloudFront edge configuration.
4. Assembled a config summary string and echoed it to `$GITHUB_OUTPUT`.

The Bash approach had three problems: (a) shell quoting edge cases with special characters in commit messages, (b) no validation — a missing SSM parameter produced an empty string that cascaded silently into downstream jobs, (c) no secret masking — account IDs and instance IDs appeared in raw log output.

**How it works**:
```
pipeline-setup.ts
  │
  ├── 1. Extract commit metadata
  │     git log -1 --pretty=format:... → commitSha, shortSha, commitMessage, commitAuthor
  │     maskSecret(commitSha)           → prevents SHA from appearing in log context lines
  │
  ├── 2. Validate AWS account
  │     sts.GetCallerIdentity() → confirms credentials are valid
  │     if currentAccount ≠ expectedAccount → emitAnnotation + FAIL
  │
  ├── 3. Resolve edge configuration (CloudFront WAF)
  │     SSM: /nextjs/{env}/cloudfront/distribution-id
  │     SSM: /nextjs/{env}/cloudfront/domain
  │     Build CDK context: restrict-access flag + WAF IP allowlist
  │
  └── 4. Emit outputs
        setOutput('commit-sha', shortSha)
        setOutput('commit-message', commitMessage)
        setOutput('edge-config', JSON.stringify(edgeConfig))
        writeSummary(markdownTable)
```

**TypeScript advantage**: The `commitMessage` is passed through `JSON.stringify` before writing to `$GITHUB_OUTPUT`. In Bash this is notoriously fragile — a commit message containing double quotes, colons, or newlines breaks the output. In TypeScript, JSON serialisation handles all edge cases correctly.

**Security**: All account IDs are masked immediately via `maskSecret(accountId)`, so they never appear in subsequent log lines, even in error output.

---

### 15.2 `preflight-checks.ts` — Input & Credential Validation

**Called by**: `just ci-preflight` (invoked in `_deploy-stack.yml` before every CDK deploy).

**What it solves**: CDK deployments can fail in confusing ways if given invalid inputs — wrong region format, non-existent account, or an environment name that isn't mapped to CDK context. Catching these before CloudFormation is invoked saves ~3 minutes per failed run and produces a clear error message instead of a cryptic CDK or API error.

**Three sequential checks**:

1. **Input Validation** (synchronous, exits immediately on first failure):
   - `stackName` — must be provided
   - `environment` — must be one of `development | staging | production | management`
   - `accountId` — must match `/^\d{12}$/` (12-digit number, no letters, no dashes)
   - `region` — must match `/^[a-z]{2}-[a-z]+-\d{1}$/` (e.g. `eu-west-1`)
   - `requireApproval` — must be one of `never | any-change | broadening`

   ```typescript
   // Account ID format check — catches copy-paste errors like 'eu-west-1'
   if (!/^\d{12}$/.test(accountId)) {
     logger.error(`Invalid AWS account ID format: ${accountId}`);
     process.exit(1);
   }
   ```

2. **AWS Credential Verification** (async):
   - Calls `sts:GetCallerIdentity` to confirm credentials are valid and unexpired.
   - If the authenticated account differs from `--account-id`, emits a **warning** (not an error) — this is expected for cross-account deployments where the IAM role assumes into the target account.

3. **CDK Bootstrap Verification** (async, gated by `--verify-bootstrap` flag):
   - Calls `cloudformation:DescribeStacks` on `CDKToolkit`.
   - Confirms the bootstrap stack status contains `COMPLETE` (not `ROLLBACK_COMPLETE`, `DELETE_COMPLETE`, etc.).
   - If missing entirely, prints the exact `cdk bootstrap aws://{account}/{region}` command to run.
   - Only invoked for environments where bootstrap is expected to be pre-existing (not for the initial Day-0 run).

**Masking pattern**:
```typescript
function mask(value: string): string {
  if (value.length <= 4) return value;
  return `***${value.slice(-4)}`;
}
```
Account IDs are displayed as `***6789` in all log output — enough to confirm "this is the right account" without leaking sensitive identifiers to anyone viewing the build log. This is defence-in-depth: even public repositories on GitHub have build logs visible to contributors.

---

### 15.3 `synthesize.ts` — CDK Synthesis & Stack Name Extraction

**Called by**: `just ci-synth {project} {environment}` (setup jobs in all deployment pipelines).

**The problem this eliminates**: Previously, every deployment pipeline synthesised CDK twice — once in the CI job to validate templates, and once in each deploy job before running `cdk deploy`. This was both slow (~2 min per synth) and wasteful. Now `synthesize.ts` runs once, caches `cdk.out/` as a GitHub Actions artifact, and all parallel deploy jobs restore the cache.

**Three outputs**:

1. **CDK synth** (`cdk synth --all --quiet`): Writes all CloudFormation templates to `infra/cdk.out/`. The `--quiet` flag suppresses warning banners that would pollute `$GITHUB_OUTPUT` parsing.

2. **synthesis-metadata.json**: Written to `infra/cdk.out/synthesis-metadata.json`, contains:
   ```json
   {
     "commitSha": "abc123...",
     "shortSha": "abc123",
     "timestamp": "2026-04-14T12-30-00",
     "environment": "development",
     "region": "eu-west-1",
     "project": "kubernetes",
     "stackCount": 10,
     "architecture": "consolidated-10-stack"
   }
   ```
   This metadata appears in the deploy summary so any viewer can correlate a deployment to the exact git commit and timestamp.

3. **Stack name outputs**: For each stack in the project's `stacks[]` array, calls `setOutput(stack.id, stack.getStackName(environment))`. Example:
   ```
   Output: data → CDKMonitoring-Kubernetes-Data-development
   Output: base → CDKMonitoring-Kubernetes-Base-development
   Output: control-plane → CDKMonitoring-Kubernetes-ControlPlane-development
   ```
   These outputs are consumed by all downstream deploy jobs as `needs.setup.outputs.data`, `needs.setup.outputs.base`, etc. This is how `_deploy-kubernetes.yml` knows the exact CloudFormation stack name to deploy without hard-coding it.

**Typed project registry (`stacks.ts`)**: The `projectsMap` is a statically typed registry:
```typescript
const projectsMap: Record<string, ProjectConfig> = {
  'kubernetes': { stacks: [...10 StackConfig objects...] },
  'bedrock':    { stacks: [...8 StackConfig objects...] },
  'shared':     { stacks: [...3 StackConfig objects...] },
};
```
`getProject(projectId)` validates the project ID at runtime and returns `undefined` for unknown projects, triggering a clean error rather than a cryptic CDK context error.

---

### 15.4 `security-scan.ts` — Checkov Orchestration & Severity Parsing

**Called by**: `just ci-security-scan` (from `ci.yml` `security-scan` job).

**What it adds beyond the raw Checkov CLI**: The `bridgecrewio/checkov-action` marketplace action simply runs Checkov and exits. `security-scan.ts` does substantially more:

1. **Template discovery**: Counts `.template.json` files in `infra/cdk.out/`. If zero templates are found (e.g. synth was skipped for this scope), emits `findings-count=0` and exits 0 gracefully — no phantom failures.

2. **Multi-format output**: Runs Checkov with `-o cli -o json -o sarif` simultaneously, writing all three formats to `security-reports/`. The CLI format goes to the log; JSON is parsed programmatically; SARIF is available for upload to GitHub Code Scanning.

3. **Config pick-up**: If `.checkov/config.yaml` exists, appends `--config-file .checkov/config.yaml`. This wires the custom checks and skip rules into the scan without duplicating them in the workflow.

4. **Severity parsing**: `parseCheckovResults()` reads `security-reports/results_json.json` and counts findings by severity:
   ```typescript
   criticalCount = countBySeverity(failedChecks, 'CRITICAL');
   highCount     = countBySeverity(failedChecks, 'HIGH');
   mediumCount   = countBySeverity(failedChecks, 'MEDIUM');
   lowCount      = countBySeverity(failedChecks, 'LOW');
   ```

5. **Gated blocking**: Only `CRITICAL` and `HIGH` findings block the pipeline:
   ```typescript
   const hasBlockingFindings = criticalCount > 0 || highCount > 0;
   if (hasBlockingFindings && !softFail) { process.exit(1); }
   ```
   `MEDIUM` and `LOW` produce a `⚠️ Non-Blocking Findings` step summary entry but don't fail the job. The `--soft-fail` flag (used in CI today) demotes all findings to non-blocking — enabling visibility without blocking active development.

6. **GitHub outputs**: Sets `scan-passed`, `findings-count`, `critical-count`, `high-count` as outputs for downstream jobs to consume in gating logic.

7. **Rich step summary**: Writes a Markdown table directly to `$GITHUB_STEP_SUMMARY`, visible on the GitHub Actions run page without needing to download report artifacts.

8. **Error annotation**: `emitAnnotation('error', ...)` writes a GitHub Actions error annotation that appears as a red banner on the PR/commit, not just in the log.

---

## 16. TypeScript CD Scripting Layer (`infra/scripts/cd/`)

> **The Core Idea**: CD scripts execute *after* a deployment event — they verify, finalise, and integrate. They are the typed, observable bridge between the YAML pipeline orchestration and the actual AWS/Kubernetes state. Each script is idempotent and communicates entirely via structured exit codes, `$GITHUB_OUTPUT`, and `$GITHUB_STEP_SUMMARY`.

---

### 16.1 `finalize.ts` — Post-Deploy Summary & Stack Verification

**Called by**: `just ci-finalize {stack} --mode stack-outputs` (per-stack) and `just ci-summary {project} {env} --mode pipeline-summary` (project-wide).

**Two operational modes** (single script, `--mode` flag switches behaviour):

#### Mode 1: `stack-outputs`

Runs once per CDK stack after its deploy job completes.

**Steps**:
1. Read CDK outputs from `cdk.out/cdk-outputs.json` using `readStackOutputs(stackName)`.
2. Emit each output key-value pair to `$GITHUB_OUTPUT` — but **mask the values** in the log:
   ```typescript
   // Log only keys — values contain infrastructure identifiers
   // that must not appear in public workflow logs.
   logger.keyValue(o.OutputKey, maskValue(o.OutputValue));
   ```
   Full values remain in `$GITHUB_OUTPUT` for downstream steps, but `:::` the log shows `***1234`.
3. Build a per-stack Markdown step summary including deploy status, duration, region, and masked output values.
4. Save outputs to an artifact file for cross-workflow consumption (`{stack-name}-outputs.json`).

This mode **never exits with code 1** — it is purely informational. A finalisation failure should not mask the actual deployment failure.

#### Mode 2: `pipeline-summary`

Runs once at the end of the entire deployment pipeline, after all stacks have been deployed.

**Steps**:
1. Calls `verifyStack()` for every stack in the project in parallel using `Promise.all()`:
   ```typescript
   const results = await Promise.all(
     project.stacks.map(stack => verifyStack(cfn, stack, env, region))
   );
   ```
   Each `verifyStack()` calls `cloudformation:DescribeStacks` and confirms the stack status contains `COMPLETE` and does not contain `ROLLBACK`.

2. Handles optional stacks: stacks with `optional: true` are healthy when `NOT_FOUND` (e.g. an API stack that hasn't been deployed yet).

3. Handles cross-region stacks: the `deploy-edge` stack deploys to `us-east-1` (CloudFront requirement). `verifyStack()` creates a new `CloudFormationClient({ region: 'us-east-1' })` for that stack only, while all others use the default region client.

4. Generates per-deployment-result rows from environment variables (`DEPLOY_{STACK_ID}_RESULT`) — these are set by upstream matrix jobs and collected here:
   ```typescript
   const result = process.env[`DEPLOY_${stack.id.toUpperCase()}_RESULT`] ?? 'skipped';
   ```

5. Writes an SSM port-forwarding cheat-sheet to the log (verbose mode only) listing the exact `aws ssm start-session` commands for Grafana (3000), Prometheus (9090), and Loki (3100) with the live EC2 instance ID — ready to copy-paste after a deploy.

6. Exits with code 1 if any non-optional stack failed verification, making the pipeline fail visibly.

---

### 16.2 `observe-bootstrap.ts` — SSM Automation Real-Time Observer

**Called by**: `just ci-observe-bootstrap --execution-id {id}` (from `_deploy-ssm-automation.yml` `observe-control-plane` job).

**The problem**: Kubernetes cluster bootstrap is a long (~20 minute) process. Previously the pipeline triggered an SSM Automation document and then polled a single `GetAutomationExecution` call every 15 seconds. Developers had no visibility into *which step* was running or *why* a step failed until the automation completed.

**How it works**:

1. **Guard**: If `--execution-id` is empty (the Day-0 scenario where the control plane hasn't launched yet), emits a `warning` annotation and exits 0 — no phantom failures during first-time setup.

2. **Poll loop** (configurable, defaults: 15s interval, 80 max polls = 20 minutes):
   ```typescript
   for (let i = 1; i <= maxPolls; i++) {
     const result = await ssm.GetAutomationExecution(executionId);
     status = result.AutomationExecutionStatus;
     steps  = result.StepExecutions;
     ...
   }
   ```

3. **Step-level progress** rendered per poll as a GitHub Actions `::group::` block:
   ```
   ::group::SSM Bootstrap Steps (Status: InProgress, poll 3)
     [PASS] ValidateInstance
     [PASS] FetchBootstrapScripts
     [RUN]  RunKubeadmInit
     [WAIT] ConfigureKubernetesNetworking
   ::endgroup::
   ```
   This appears as a collapsible section in the GitHub Actions log, keeping the UI clean whilst exposing full detail on demand.

4. **Dual CloudWatch log streaming**: On every poll, fetches recent events from two log groups:
   - `/ssm/k8s/{env}/bootstrap` — the SSM Automation's own structured log output.
   - `/ec2/k8s-{env}/instances` — the EC2 instance's `cloud-init` output and `kubelet` journal, forwarded to CloudWatch by the CloudWatch Agent installed during user-data.

   This dual streaming means a developer watching a bootstrap can see the raw EC2 boot output (e.g., `kubeadm init` progress) in near real-time without needing SSH or SSM Session Manager access.

5. **Failure diagnostics**: On a terminal `Failed` status:
   - Finds the failed step in `StepExecutions`.
   - Extracts `RunCommand.CommandId` from `step.Outputs`.
   - Calls `ssm:GetCommandInvocation` to retrieve `StandardOutputContent` and `StandardErrorContent` from that specific `RunShellScript` invocation.
   - Dumps both to the GitHub Actions log inside a `::group::RunCommand Output` block.

   Without this, diagnosing a failed bootstrap step required navigating to the AWS Console, finding the SSM Automation, clicking through to the failed step, clicking through again to the RunCommand output. Now the full failure reason appears directly in the pipeline log.

6. **Rich step summary**: Constructs a summary table showing environment, execution ID, poll count, and final outcome (`✅ Success`, `❌ Failed`, `⏭️ Skipped`, `⏱️ Timed out`) written to `$GITHUB_STEP_SUMMARY`.

---

### 16.3 `deploy-nextjs-secrets.ts` — Kubernetes Secrets via SSM Automation

**Called by**: `just ci-deploy-nextjs-secrets --environment {env}` (from `_post-bootstrap-config.yml`).

**Purpose**: Inject the `nextjs-secrets` Kubernetes Secret and `nextjs-config` ConfigMap into the cluster by triggering the SSM Automation document that runs `deploy.py` on the control-plane node. This is one instance of the broader **SSM-as-a-proxy** pattern used throughout all application secret injection.

**Five-step flow**:

1. **Resolve control-plane instance ID** via EC2 tag lookup (`k8s:bootstrap-role=control-plane`, state=running). This is done via EC2 `DescribeInstances` rather than reading an SSM parameter because ASG instance replacements mean the SSM parameter can be stale. The live EC2 tag query always returns the *currently running* instance.

2. **Resolve SSM Automation document name** from SSM parameter `/k8s/{env}/deploy/secrets-doc-name`. The document name is written by the CDK `SsmAutomationStack` at deploy time — the TypeScript script reads it dynamically rather than hard-coding it, decoupling the script from CDK naming conventions.

3. **Resolve S3 bucket** from `/k8s/{env}/scripts-bucket` — the bucket containing the versioned `deploy.py` and related scripts. Passing this into the automation document ensures the exact script version matching the current deployment is used.

4. **Start SSM Automation** with parameters: `InstanceId`, `SsmPrefix`, `S3Bucket`, `Region`. The automation fetches `deploy.py` from S3, runs it on the control-plane, which in turn reads all `nextjs/*` SSM parameters and applies the Kubernetes objects.

5. **Poll until terminal state** with step-level progress logging:
   ```typescript
   for (const step of steps) {
     if (status === 'Success')   logger.info(`[PASS] ${name}`);
     if (status === 'Failed')    logger.warn(`[FAIL] ${name}: ${failure}`);
     if (status === 'InProgress') logger.info(`[RUN]  ${name}`);
   }
   ```
   On failure, dumps the full step breakdown with outputs and exits 1 — blocking the rest of the post-bootstrap pipeline from proceeding with a broken secrets state.

**Error handling**: Uses `emitAnnotation('error', ...)` on every failure path. These annotations appear as red banners on the Pull Request or commit status page, not just buried in the log.

---

### 16.4 `verify-argocd-sync.ts` — GitOps Health Polling (via SSM)

**Called by**: `just ci-verify-argocd --mode sync` (from `gitops-k8s.yml`) and `--mode health` (from `_deploy-ssm-automation.yml`).

**The fundamental constraint**: The ArgoCD API server runs inside the Kubernetes cluster on a ClusterIP service. There is no public NodePort or LoadBalancer — by design. The GitHub-hosted runner has no network route to the cluster's private subnet. **Every ArgoCD API call is proxied via SSM send-command** to the control-plane node, which then runs `curl` on localhost against the ClusterIP.

**Two verification modes**:

#### Mode: `health` (used after SSM bootstrap completes)

Does NOT use the ArgoCD HTTP API. Instead, polls Kubernetes pod readiness directly:
```bash
# Runs via SSM on the control-plane node:
export KUBECONFIG=/etc/kubernetes/admin.conf
kubectl wait deployment/argocd-server deployment/argocd-repo-server \
  deployment/argocd-dex-server deployment/argocd-redis \
  -n argocd --for=condition=Available --timeout=30s
kubectl rollout status statefulset/argocd-application-controller -n argocd --timeout=30s
```

**Why not HTTP in health mode?** Just after bootstrap, ArgoCD pods may be `Running` but the HTTP API layer may not yet be accepting requests. `kubectl wait --for=condition=Available` asks Kubernetes directly (via the API server, which is on the same node) whether the Deployment's replicas are ready-counted. This is the most reliable signal for "is ArgoCD alive?".

#### Mode: `sync` (used after Git push / full GitOps validation)

Polls the ArgoCD HTTP API for all 10 expected applications:
```typescript
const EXPECTED_APPS = [
  'cert-manager', 'cert-manager-config', 'traefik',
  'nextjs', 'monitoring', 'metrics-server',
  'local-path-provisioner', 'ecr-token-refresh',
  'argocd-image-updater', 'argocd-notifications',
];
```

**The SSM-curl architecture**: For each app, constructs a shell command that:
1. Exports `KUBECONFIG=/etc/kubernetes/admin.conf`.
2. Dynamically resolves the ArgoCD ClusterIP via `kubectl get svc argocd-server -n argocd -o jsonpath='{.spec.clusterIP}'`.
3. Executes `curl -s http://{ClusterIP}/argocd/api/v1/applications/{app}` with a Bearer token.
4. Pipes the response through a **single-line Python filter** to extract only `sync` and `health` status:
   ```python
   # Inline in the shell command — SSM doesn't preserve newlines:
   import json,sys;d=json.loads(sys.stdin.read());print(json.dumps({"sync":d.get("status",{}).get("sync",{}).get("status","Unknown"),"health":...}))
   ```
   **Why Python filter inline?** The full ArgoCD application JSON for the `monitoring` app (containing Prometheus dashboards config) exceeds 24KB — larger than SSM send-command's 24,576 byte stdout limit. Without the Python filter the output would be truncated and JSON parsing would fail. Filtering server-side to a tiny status JSON avoids the truncation entirely.

**Self-healing token refresh**: If the diagnostic probe returns HTTP 401 or 403 (expired bot token):
1. Fetches the ArgoCD admin password from SSM or `argocd-initial-admin-secret`.
2. POSTs to `/argocd/api/v1/session` to obtain a short-lived admin session token.
3. POSTs to `/argocd/api/v1/account/ci-bot/token` to generate a new non-expiring API key.
4. Validates the new token (HTTP 200 on `/api/v1/applications`).
5. Stores the refreshed token in Secrets Manager (`k8s/{env}/argocd-ci-token`).
6. **Continues the sync poll with the fresh token** — no manual intervention needed.

This closed-loop token management prevents the class of "ArgoCD verification failed because the bot token expired" failures that would otherwise require a manual `just argocd-ci-token` runbook execution.

**Grace period**: Newly added ArgoCD Applications (from a new `app-of-apps` entry) may not exist in ArgoCD immediately after a push — ArgoCD takes up to 3 minutes to reconcile the root App-of-Apps. During the first 3 polls (~90s), `permission denied` responses (ArgoCD returns 403 for non-existent apps) are treated as "pending discovery" rather than errors. After the grace period, `permission denied` is treated as a real failure.

---

## 17. Checkov IaC Security Framework

> **Concept**: Checkov is a static analysis tool that scans Infrastructure as Code (CloudFormation, Terraform, CDK-synthesised templates) against a library of security and compliance checks. It can be thought of as a "linter for security misconfigurations" — catching issues like unencrypted S3 buckets or permissive Security Groups *before* they are deployed.

---

### 17.1 Configuration Architecture (`.checkov/config.yaml`)

The `.checkov/config.yaml` file configures Checkov's scan behaviour across three dimensions:

**1. Framework scope**:
```yaml
framework: cloudformation
directory: "infra/cdk.out"
```
Scans only CDK-synthesised CloudFormation templates, not raw Terraform or Kubernetes manifests. This ensures checks are relevant to the actual deployment artefacts.

**2. Custom check registration**:
```yaml
external_checks_dir:
  - ".checkov/custom_checks"
```
Loads all Python files in `.checkov/custom_checks/` as additional Checkov checks. This is Checkov's extension mechanism — custom checks are first-class citizens, not workarounds.

**3. Contextual skip rules**: The config contains a curated list of `skip-check` entries with commented justifications. Examples:

| Check | Why Skipped |
|-------|-------------|
| `CKV_AWS_117` (Lambda VPC) | Lambda functions are intentionally VPC-agnostic (Bedrock Lambdas call external Bedrock API endpoints) |
| `CKV_AWS_115` (Lambda concurrency) | Solo-developer project; reserved concurrency limits add cost without benefit |
| `CKV_AWS_116` (Lambda DLQ) | Specific Lambdas have DLQs by design; blanket requirement is too broad |
| `CKV_AWS_76` (CloudFront geo-restriction) | Portfolio is intentionally global — geo-restriction would exclude legitimate visitors |
| `CKV2_AWS_5` (SG not attached) | CDK synthesises temporary SGs during synthesis; they are always attached in the deployed stack |

**Skip philosophy**: Each skip is a **documented decision**, not a shortcut. The comments in `config.yaml` explain *why* the check doesn't apply, making the security posture auditable. A future reviewer can see exactly which checks were bypassed and the reasoning, rather than seeing an unexplained security suppression.

---

### 17.2 Custom IAM Checks (`iam_rules.py`)

Five custom checks enforcing IAM hygiene beyond Checkov's built-in rules:

#### `CKV_CUSTOM_IAM_1` — Permissions Boundary Required

**What it checks**: Every `AWS::IAM::Role` must have a `PermissionsBoundary` configured.

**Why**: A permissions boundary is an IAM policy that acts as a ceiling — even if an inline policy grants `*`, the boundary limits effective permissions. This is a defence-in-depth control: if an attacker escalates privileges within a role, they still cannot exceed the boundary.

**Exception**: Service-linked roles (roles trusted by AWS services like EMR or Auto Scaling) are exempt — they are managed by AWS and cannot accept boundaries.

```python
def _is_service_linked_role(self, assume_doc: dict) -> bool:
    # Check trust policy principal for aws.amazonaws.com patterns
    # autoscaling.amazonaws.com, emr.amazonaws.com etc. → skip boundary check
```

**Current state**: This check is in `skip-check` in `config.yaml` because CDK-generated roles don't automatically attach boundaries — adding boundaries to all 40+ IAM roles in the project is a future hardening task.

#### `CKV_CUSTOM_IAM_2` — No Hardcoded Account IDs in ARNs

**What it checks**: IAM policy resource ARNs must not contain literal 12-digit account numbers.

**Why**: Hardcoded account IDs create cross-account portability issues and reveal infrastructure topology in policy documents. CloudFormation provides `!Sub "arn:aws:s3:::${AWS::AccountId}:..."` as the correct approach.

**Implementation**: Regex `:(\d{12}):` scanned against every `Resource` ARN in every policy statement. Wildcards (`*`) are exempt.

#### `CKV_CUSTOM_IAM_3` — No Static Role Names

**What it checks**: `AWS::IAM::Role` resources should not have a static string `RoleName`.

**Why**: When CloudFormation needs to replace an IAM Role (e.g., if the trust policy changes in a way that requires replacement), a static `RoleName` causes a naming conflict. The new role cannot be created with the same name while the old role still exists. CDK generates unique names by default using a deterministic hash — the check catches cases where a developer overrides this with a hard-coded string.

**Exception**: If `RoleName` is set to a CloudFormation intrinsic function (e.g., `Fn::Sub`, `Fn::Join`, `!Ref`), the name is dynamic and the check passes. Only raw string literals fail.

#### `CKV_CUSTOM_IAM_4` — Limit AWS Managed Policies (≤3)

**What it checks**: Each IAM role may attach at most 3 AWS managed policies (e.g., `arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore`).

**Why**: AWS managed policies are broad by design — `AmazonEC2FullAccess` grants far more than most workloads need. Limiting their count encourages least-privilege inline policies. The threshold of 3 was chosen based on the legitimate maximum for EC2 instance roles: ECS agent (`AmazonEC2ContainerServiceforEC2Role`) + SSM (`AmazonSSMManagedInstanceCore`) + CloudWatch (`CloudWatchAgentServerPolicy`).

#### `CKV_CUSTOM_IAM_5` — Role Must Have at Least One Policy

**What it checks**: Every IAM Role must have at least one managed policy or inline policy attached.

**Why**: An empty role is either a misconfiguration (missing grants that will cause runtime failures) or an orphaned resource. This check is a reminder to verify intentional empty roles rather than allowing them to accumulate silently.

---

### 17.3 Custom Security Group Checks (`sg_rules.py`)

Five custom checks enforcing network security beyond Checkov's built-in rules:

#### `CKV_CUSTOM_SG_1` — No SSH Ingress (Port 22)

**What it checks**: No Security Group ingress rule may open port 22 (SSH) from any source.

**Why**: This project uses **SSM Session Manager** for all instance access. SSM provides auditable, MFA-protected shell sessions without any open inbound ports. Port 22 open on a public-facing instance is one of the most common attack vectors on the internet. This check codifies the project's architectural decision (no SSH) as an automated enforcement rule.

**Implementation**: Checks `FromPort <= 22 <= ToPort` — catches rules like `0-65535` that incidentally include port 22.

#### `CKV_CUSTOM_SG_2` — No Unrestricted All-Protocol Egress

**What it checks**: No Security Group egress rule may use `0.0.0.0/0` with protocol `-1` (all protocols).

**Why**: While egress filtering has less blast radius than ingress, unrestricted egress allows a compromised instance to exfiltrate data to any destination on any protocol, including unusual protocols used for covert channels. This check blocks the CDK default of `addEgressRule(Peer.anyIpv4(), Port.allTraffic())` unless explicitly justified.

**Note**: The project's SGs use specific egress rules (e.g., HTTPS to ECR CIDR ranges, UDP 8472 for VXLAN), not catch-all rules.

#### `CKV_CUSTOM_SG_3` — No Full Port Range Ingress

**What it checks**: No ingress rule may span 1,000 or more consecutive ports (e.g., `1-65535` or `1024-32767`).

**Why**: Port ranges exceeding 1,000 almost always indicate a misconfiguration or an overly permissive rule written to avoid debugging which specific port is needed. The threshold of 1,000 accommodates legitimate ephemeral port ranges (e.g., `1024-2047` for specific UDP protocols) while blocking catch-all rules.

#### `CKV_CUSTOM_SG_4` — Metrics Ports Not Externally Accessible

**What it checks**: Ports 9090 (Prometheus) and 9100 (Node Exporter) must not be reachable from external CIDR sources.

**Why**: Prometheus's `/metrics` endpoint exposes detailed system information — CPU usage patterns, memory statistics, process names — that constitutes sensitive operational intelligence. Node Exporter is even more verbose. Both must only be accessible within the cluster's Security Group via SG-to-SG rules.

**Implementation**:
```python
INTERNAL_ONLY_PORTS = {3000, 9090, 9100}

def _has_external_cidr(rule: dict) -> bool:
    # Returns True if rule uses CidrIp/CidrIpv6 (external)
    # Returns False if rule uses SourceSecurityGroupId (internal SG-to-SG)
```

#### `CKV_CUSTOM_SG_5` — Grafana Not Directly Exposed

**What it checks**: Port 3000 (Grafana) must not be accessible from external CIDR sources.

**Why**: Grafana dashboards expose infrastructure topology, service health, and performance baselines. This information is useful for attackers profiling a target. Additionally, Grafana default installations have historically had authentication bypass vulnerabilities. The project's access model is: developers use `aws ssm start-session` port-forwarding (`portNumber=3000, localPortNumber=3000`) — no public port required.

This check is directly enforcing the SSM port-forwarding access model at the IaC level. It's an example of **security policy expressed as code** — the architectural decision ("Grafana via SSM only") is now automatically verified on every CI run.

---

### 17.4 The Extended Security Model: Custom Checks as Policy-as-Code

Taken together, the 10 custom Checkov rules implement a machine-checkable security policy:

| Security Principle | Enforced By |
|-------------------|-------------|
| No direct shell access | `CKV_CUSTOM_SG_1` (no SSH) |
| Metrics never public | `CKV_CUSTOM_SG_4`, `CKV_CUSTOM_SG_5` |
| Egress controlled | `CKV_CUSTOM_SG_2` |
| No catch-all port rules | `CKV_CUSTOM_SG_3` |
| IAM least-privilege | `CKV_CUSTOM_IAM_1`, `CKV_CUSTOM_IAM_4` |
| No hardcoded identifiers | `CKV_CUSTOM_IAM_2` |
| Safe CFN updates | `CKV_CUSTOM_IAM_3` |
| No empty roles | `CKV_CUSTOM_IAM_5` |

Each rule enforces a decision made at the architecture level — the rules exist because the project committed to these patterns in code and infrastructure. Custom checks are the automated audit trail proving those commitments are maintained with every deployment.

---

## 12. Security Posture Summary *(updated)*

| Control | Implementation | Strength |
|---------|---------------|----------|
| Keyless authentication | OIDC (`id-token: write`) | ✅ Industry standard |
| IAM identity masking | Custom `configure-aws` action (AROA mask) | ✅ Above standard |
| Environment secret scoping | GitHub Environments | ✅ Standard |
| EC2 instance ID masking | `::add-mask::` per pipeline | ✅ Above standard |
| No K8s API public exposure | SSM proxy for all kubectl | ✅ Best practice |
| Secret-free GitOps | `deploy.py` + SSM SecureString | ✅ Best practice |
| Immutable image tags | `sha-rAttempt` composite | ✅ Best practice |
| Pinned action versions | Commit SHA on all actions | ✅ Supply chain hardened |
| IaC security scanning | Checkov + 10 custom rules | ⚠️ Soft fail today (future: hard) |
| Custom network controls | `CKV_CUSTOM_SG_1 → SG_5` | ✅ Policy-as-code |
| Custom IAM controls | `CKV_CUSTOM_IAM_1 → IAM_5` | ✅ Policy-as-code |
| Cross-repo minimal access | Sparse checkout for articles | ✅ Least privilege |
| Root account deployment gate | `"DEPLOY-ORG"` typed confirmation | ✅ High friction by design |
| Day-1 deployment gate | `"DEPLOY-DAY1"` confirmation | ✅ High friction by design |
| CI scripting type safety | TypeScript (`strict: true`) in all scripts | ✅ No runtime type errors |
| Input validation coverage | `preflight-checks.ts` validates all deploys | ✅ Catch errors before CloudFormation |
| Sensitive output masking | `maskValue()` in all finalise/summary scripts | ✅ Defence-in-depth |

---

*Document generated from full code review of all 26 `.github/` workflow files, 4 CI scripts, 5+ CD scripts, and 10 custom Checkov checks.*
*Lines reviewed: ~12,000 YAML (workflows) + ~3,500 TypeScript (scripts) + ~550 Python (checkov).*
