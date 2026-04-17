# DORA Metrics Review — 2026-04-17

> **Status**: Ongoing review. Concrete metrics are locked and verifiable.
> Unmeasured metrics (TTSR, MTTR, RTO) remain pending operational test execution.
>
> **Review scope**: This document extends the snapshot in `dora-metrics-2026-04-17.md`
> with full deployment environment context, script execution details, project-service mapping,
> and a QA gap analysis aligned with the DORA Elite tier criteria.

---

## Table of Contents

1. [Deployment Environment Overview](#1-deployment-environment-overview)
2. [CI/CD Pipeline Architecture](#2-cicd-pipeline-architecture)
3. [Measured DORA Metrics — Concrete & Verifiable](#3-measured-dora-metrics--concrete--verifiable)
4. [Script Reference: `dora-metrics-snapshot.sh`](#4-script-reference-dora-metrics-snapshotsh)
5. [Script Reference: `etcd-restore-rto-test.sh`](#5-script-reference-etcd-restore-rto-testsh)
6. [Service Inventory & ArgoCD Application Map](#6-service-inventory--argocd-application-map)
7. [Unmeasured Metrics — Pending Operational Tests](#7-unmeasured-metrics--pending-operational-tests)
8. [QA Gap Analysis](#8-qa-gap-analysis)
9. [Permitted Resume Claims](#9-permitted-resume-claims)
10. [Next Actions](#10-next-actions)

---

## 1. Deployment Environment Overview

### 1.1 Infrastructure Stack

| Layer | Technology | Detail |
|---|---|---|
| Cloud Provider | AWS (`eu-west-1`) | Primary region; CloudFront edge at `us-east-1` |
| Compute | EC2 (K3s / kubeadm) | Self-hosted Kubernetes cluster (1 control-plane + worker pool) |
| Container Registry | Amazon ECR | Two repositories: `site` + `start-admin` |
| GitOps Controller | ArgoCD | 25 managed applications |
| Progressive Delivery | Argo Rollouts | Blue/Green strategy (Next.js `site` + `start-admin`) |
| Image Delivery | ArgoCD Image Updater | Polls SSM parameters for image URI updates |
| Monitoring | Prometheus + Grafana + Loki + Tempo | In-cluster, via `monitoring` namespace |
| Alerting | Grafana Alertmanager | 30s scrape + evaluation cycle |
| DR Snapshots | etcd → S3 (`dr-backups/etcd/snapshot.db`) | Automated via k8s-bootstrap |
| IaC | AWS CDK (TypeScript) | Multi-project: `k8s`, `bedrock`, `shared` |
| Secret Management | AWS SSM Parameter Store + Secrets Manager | SSM as configuration bus; Secrets Manager for bootstrap artefacts |
| DNS | Route 53 (cross-account) | Root account hosts zone; dev account writes records |
| Edge | CloudFront + WAF | WAF IP-allowlist for `/admin/*`; CloudFront signed for static assets |

### 1.2 Kubernetes Cluster Node Layout

```
Control Plane
  └── EC2 (tag: k8s:bootstrap-role=control-plane)
        └── etcd (single-node, snapshotted to S3)

Worker Pools
  ├── General Pool  (tag: k8s:node-pool=general)   — application workloads
  └── Monitoring Pool (tag: k8s:node-pool=monitoring) — Prometheus / Grafana
```

### 1.3 GitHub Repository

| Field | Value |
|---|---|
| Repo | `Nelson-Lamounier/cdk-monitoring` |
| Primary branch | `develop` (active CI/CD) |
| Protected branch | `main` (stable releases) |
| Environments | `development`, `management` |
| OIDC Auth | `AWS_OIDC_ROLE` scoped per GitHub Environment |

---

## 2. CI/CD Pipeline Architecture

### 2.1 Pipeline Inventory (26 Workflow Files)

The `.github/workflows/` directory contains **8 reusable workflows** (prefixed `_`) and **18 runnable orchestrators**:

#### Reusable Components (`_` prefix)

| Workflow | Purpose |
|---|---|
| `_build-push-image.yml` | Docker build + ECR push (generic) |
| `_deploy-kubernetes.yml` | 10-stack CDK deploy DAG |
| `_deploy-ssm-automation.yml` | Bootstrap trigger via SSM |
| `_deploy-stack.yml` | Generic CDK stack deploy unit |
| `_migrate-articles.yml` | MDX → DynamoDB migration |
| `_post-bootstrap-config.yml` | K8s secrets injection via `deploy.py` |
| `_sync-assets.yml` | Next.js `.next/static/` → S3 + CloudFront invalidation |
| `_verify-stack.yml` | CDK drift detection |

#### Runnable Orchestrators

| Workflow | Display Name | Trigger |
|---|---|---|
| `ci.yml` | **Continuous Integration** | Push / PR — all branches |
| `deploy-frontend.yml` | **Deploy Frontend (Dev)** | `workflow_dispatch`, `repository_dispatch` |
| `deploy-api.yml` | Deploy API Services | Push `develop`, `workflow_dispatch` |
| `deploy-bedrock.yml` | Deploy Bedrock AI | `workflow_dispatch` only |
| `deploy-kubernetes.yml` | Deploy Kubernetes Infra | `workflow_dispatch` |
| `deploy-self-healing.yml` | Deploy Self-Healing Agent | Push `develop` (path-filtered) |
| `day-1-orchestration.yml` | Day-1 Platform Bootstrap | `workflow_dispatch` (confirmation gate) |
| `deploy-ssm-automation.yml` | SSM Bootstrap Trigger | Push `develop` (path-filtered) |
| `deploy-post-bootstrap.yml` | Re-inject K8s Secrets | `workflow_dispatch` |
| `deploy-shared.yml` | Deploy Shared VPC | `workflow_dispatch` |
| `deploy-org.yml` | Deploy Org Resources | `workflow_dispatch` (confirmation gate) |
| `gitops-k8s.yml` | GitOps K8s Validation | Push `develop` (path-filtered) |
| `build-ci-image.yml` | Build CI Docker Image | Push (Dockerfile change) |
| `kb-staleness-audit.yml` | KB Staleness Audit | CRON (monthly) |
| `publish-article.yml` | Verify Article Pipeline | `workflow_dispatch` |
| `sync-kb-docs.yml` | Sync KB Docs | `workflow_dispatch` |
| `test-article-pipeline.yml` | Test Article Pipeline | `workflow_dispatch` |

### 2.2 CI Pipeline Job Graph (`ci.yml`)

The CI pipeline consists of **13 parallel/sequential jobs**, all gated by path-filter change detection:

```
detect-changes (~10s)
        │
  ┌─────┼──────────────────────────────────────────────┐
  │     │                                              │
lint-  setup  ─────────────────────────────────────── kb-drift-check
workflows      │            │          │               (warn-only)
               │            │          │
           ┌───┴────┐   validate-  validate-
           │  Code  │   helm      cdk
           │Quality │   (k8s-     │
           │        │   content)  ├── iac-security-scan
           ├─ audit │              (SARIF → GitHub Security)
           ├─ lint  │
           ├─ deps  │
           ├─ type  │
           ├─ build │
           ├─ test- │
           │ stacks │
           ├─ test- │
           │ frontend-ops
           └─ test- │
             k8s-bootstrap
                    │
              ci-success (fan-in gate)
```

**Change detection categories:**

| Filter | Paths |
|---|---|
| `stacks` | `infra/lib/*-stack.ts`, `infra/tests/unit/stacks/**` |
| `any-src` | `infra/lib/**/*.ts`, `bin/**/*.ts` |
| `k8s-content` | `kubernetes-app/platform/**`, `kubernetes-app/workloads/**`, `kubernetes-app/k8s-bootstrap/**` |
| `frontend-ops` | `frontend-ops/**`, `deploy-frontend.yml` |
| `kb-content` | `knowledge-base/**`, `infra/**`, `kubernetes-app/**`, `scripts/**`, `.github/**` |

### 2.3 Frontend CD Pipeline Job Graph (`deploy-frontend.yml`)

```
resolve-targets (3 min)
    │
    ├── [Site]  build-site (25 min) ─── push-site (15 min) ─── sync-assets ─┐
    │                                                         └── deploy-site ── promote-site
    │
    └── [Admin] build-admin (25 min) ─ push-admin (15 min) ─── deploy-admin ── promote-admin ── invalidate-admin
    │
    └── [Parallel] migrate-articles (independent)
    │
    └── summary (always)
```

**Key CD design patterns:**

- **OIDC keyless auth**: No stored AWS access keys; JWT-based `sts:AssumeRoleWithWebIdentity`
- **AROA masking**: IAM role unique identifier masked from all build logs
- **EC2 instance ID masking**: Control-plane instance ID masked immediately after SSM resolution
- **SSM proxy pattern**: GitHub runners have no VPC access; all `kubectl` commands delegate to control-plane via `aws ssm send-command`
- **Immutable image tags**: `${github.sha}-r${github.run_attempt}` — prevents ECR tag overwrite on retries
- **Concurrency guard**: `cancel-in-progress: true` — rapid pushes cancel the oldest in-flight run
- **Blue/Green promotion**: Argo Rollouts paused automatically after green RS is ready; pipeline issues `kubectl argo rollouts promote` via SSM

### 2.4 CI Toolchain

| Tool | Role |
|---|---|
| Custom CI image (`ghcr.io/nelson-lamounier/cdk-monitoring/ci:latest`) | Baked Node.js 22, Helm, kubectl, Just, cfn-lint, Checkov, AWS CLI, Python 3.12 |
| `justfile` (task runner) | Unified local/CI command surface — all CI steps use `just <recipe>` |
| `actionlint` | Workflow YAML static analysis |
| `checkov` | CDK synthesised CloudFormation IaC security scan → SARIF → GitHub Security tab |
| `kubeconform` | Kubernetes schema validation for rendered Helm templates |
| `dorny/paths-filter` | Monorepo change detection (skip unchanged paths) |
| `dependency-cruiser` | Architectural boundary enforcement (circular import detection) |
| `jest` | CDK stack unit tests + frontend-ops tests |
| `pytest` | K8s bootstrap Python tests (offline, 55 tests, all AWS/K8s calls mocked) |

---

## 3. Measured DORA Metrics — Concrete & Verifiable

> **Date of measurement**: 2026-04-17
> **Source**: `scripts/local/dora-metrics-snapshot.sh` against `Nelson-Lamounier/cdk-monitoring`

### 3.1 Summary Table

| DORA Metric | Measured Value | DORA Tier | Usable in Resume? |
|---|---|---|---|
| **Lead Time (CI + CD)** | **~13 minutes** | Elite (< 1 hour) | ✅ Yes |
| **CI Average Duration** | **5.3 min** | — (component) | ✅ Yes |
| **Frontend CD Average Duration** | **7.5 min** | — (component) | ✅ Yes |
| **Deployment Frequency — frontend pipeline only (30 days)** | **34 deploys** (~1.1/day) ⚠️ floor figure — `deploy-api.yml`, `deploy-bedrock.yml`, `deploy-self-healing.yml` not yet counted | Elite (on-demand) | ✅ Yes (with scope qualifier — see §4.3) |
| **CI Change Failure Rate** | 26% (13/50) | Below Elite | ❌ No — `develop` WIP noise |
| **Frontend Deploy CFR** | 30% (6/20) | Below Elite | ❌ No — same branch |
| **Alert Detection Time** | **30 seconds (worst case)** | Elite | ✅ Yes |
| **ArgoCD Healthy Apps** | **25/25 at measurement** ⚠️ point-in-time snapshot (2026-04-17) — always cite the date | Elite | ✅ Yes (with date qualifier) |
| **TTSR (GitOps self-heal)** | Unmeasured | — | ❌ Pending |
| **MTTR (deploy rollback)** | Unmeasured | — | ❌ Pending |
| **RTO (etcd restore)** | Unmeasured | — | ❌ Pending |

### 3.2 Lead Time Breakdown

```
🕐 CLOCK START
Commit push to develop
        │
        ▼
 CI: "Continuous Integration" ── avg 5.3 min (last 10 successful)
        │  (quality gate: lint, type-check, unit tests, IaC scan)
        ▼
 CD: "Deploy Frontend (Dev)" ───── avg 7.5 min (last 10 successful)
        │  ┌─ SSM put-parameter (image URI)
        │  ├─ ArgoCD Image Updater picks up new URI (~2 min polling)
        │  ├─ Argo Rollouts creates green ReplicaSet
        │  ├─ promote-site job polls for Paused state (up to 6 min)
        │  └─ promote-site issues `kubectl argo rollouts promote`
        │     → Rollout status = Healthy  ◀── workflow step completes here
        ▼
🕐 CLOCK STOP: CD workflow exits with status = success

 Total lead time: ~13 min
```

> **Clock boundary — critical note for agents:**
> The **13-minute figure includes the full blue/green promotion cycle**.
> The `promote-site` and `promote-admin` jobs in `deploy-frontend.yml` block until
> `kubectl argo rollouts status <name> --watch` reports `Healthy` — they do not exit
> before that. The measured 7.5-minute CD average therefore already absorbs the
> ArgoCD Image Updater polling delay (~2 min) and the Rollout promotion wait.
> The workflow measure stops at **Rollout Healthy**, which is the last meaningful
> event before user traffic reaches the new version.
>
> **What is NOT included in the 13 minutes:**
> - The ArgoCD periodic drift-reconciliation tick for non-image-update resources
>   (not on the critical path for image deploys).
> - The CloudFront propagation of any invalidated paths (runs in parallel; not blocking).
> - The first Live HTTP response from the new replica (typically < 5s after Healthy;
>   negligible relative to measurement precision).
>
> **Correct resume phrasing**: *"13-minute commit-to-rollout lead time — measured from
> `git push` to Argo Rollouts reporting Healthy on the new green ReplicaSet."*

**Elite tier boundary**: < 1 hour. Achieved. This is a **real, reproducible, script-verified number**.

### 3.3 Change Failure Rate — Interpretation & Exclusion

The raw CFR figures (CI: 26%, Frontend CD: 30%) **cannot be used as stated** for the following documented reasons:

1. **Branch scope**: All failures occurred on the `develop` branch during **active feature development**. This is WIP commit noise, not production gate failures.
2. **No main-branch baseline**: The `main` branch has **zero** measured CFR because it receives only squash-merged, CI-passing PRs.
3. **Correct CFR definition**: DORA defines CFR as the percentage of deployments causing a production outage or rollback. A failing CI run on a WIP commit on `develop` does not meet that definition.

**Actionable**: Once a stabilisation period is observed post-`main` merge, measure CFR on `main`-branch CD runs only.

### 3.4 Alert Detection Time

Measured directly from Prometheus configuration:

```bash
kubectl get configmap prometheus-server \
  --namespace monitoring \
  -o jsonpath='{.data.prometheus\.yml}' | \
  grep -E "scrape_interval|evaluation_interval"
```

Both `scrape_interval` and `evaluation_interval` are **30 seconds**. Worst-case detection latency = one full evaluation cycle = **30 seconds**. This is a DORA Elite-aligned operational observability metric.

---

## 4. Script Reference: `dora-metrics-snapshot.sh`

**Location**: `scripts/local/dora-metrics-snapshot.sh`
**Purpose**: Automates DORA metric capture from GitHub Actions history.
**Runtime requirements**: `gh` CLI (authenticated), `jq`

### 4.1 Pre-execution Setup

```bash
# Step 1: authenticate gh CLI (one-time)
gh auth login

# Step 2: verify token has repo scope
gh auth status

# Step 3: confirm REPO variable
export REPO="Nelson-Lamounier/cdk-monitoring"
```

### 4.2 Full Script Execution

Run from the repository root:

```bash
bash scripts/local/dora-metrics-snapshot.sh
```

**Expected output sections:**

```
=== DORA METRICS SNAPSHOT ===
Generated: Thu Apr 17 15:00:00 BST 2026
Repo: Nelson-Lamounier/cdk-monitoring

--- CI run time (last 10 successful: 'Continuous Integration') ---
Average: 5.3 min

--- Frontend CD run time (last 10 successful: 'Deploy Frontend (Dev)') ---
Average: 7.5 min

--- Deployment frequency: Frontend (last 30 days) ---
Successful deploys in last 30 days: 34

--- CFR: CI (last 50 runs, success+failure only) ---
CFR: 13/50 = 26% (note: all failures on develop — WIP noise, not production gate)

--- CFR: Frontend deploy (last 20 runs) ---
CFR: 6/20 = 30%

--- Workflow name discovery (for updating this script) ---
Continuous Integration
Deploy Frontend (Dev)
...

=== END ===
```

### 4.3 Individual Command Breakdown

#### CI Average Duration (last 10 successful runs)

```bash
gh run list --repo "$REPO" --workflow "Continuous Integration" \
  --limit 10 --json conclusion,startedAt,updatedAt \
  --jq '[.[] | select(.conclusion=="success") |
        ((.updatedAt | fromdateiso8601) - (.startedAt | fromdateiso8601))] |
        (add / length / 60) | "Average: \(. * 10 | round / 10) min"'
```

> **Note**: `durationMs` is not available in `gh run list`. Duration is derived from
> `updatedAt - startedAt`. The workflow display name `"Continuous Integration"` must match
> exactly — **not** the filename `ci.yml`. Verify with `gh workflow list --repo $REPO`.

#### Frontend CD Average Duration (last 10 successful runs)

```bash
gh run list --repo "$REPO" --workflow "Deploy Frontend (Dev)" \
  --limit 20 --json conclusion,startedAt,updatedAt \
  --jq '[.[] | select(.conclusion=="success") |
        ((.updatedAt | fromdateiso8601) - (.startedAt | fromdateiso8601))] |
        (add / length / 60) | "Average: \(. * 10 | round / 10) min"'
```

> **Note**: `--limit 20` is used instead of 10 because some recent runs may not be
> `success` (WIP branch noise). The jq filter selects only successful runs,
> so a higher `--limit` ensures at least 10 candidates.

#### Deployment Frequency (last 30 days)

> ⚠️ **Scope note**: The figure of 34 covers `Deploy Frontend (Dev)` only — a floor,
> not the total deployment count. Run all four commands below and sum the results
> for the complete cross-pipeline frequency figure.

**Frontend (measured baseline — 34 deploys):**

```bash
gh run list --repo "$REPO" --workflow "Deploy Frontend (Dev)" \
  --limit 100 --json conclusion,createdAt \
  --jq '[.[] | select(.conclusion=="success") |
        select((.createdAt | fromdateiso8601) > (now - 2592000))] |
        length | "[frontend] Deploys in last 30 days: \(.)"'
```

**API services (`deploy-api.yml`):**

```bash
gh run list --repo "$REPO" --workflow "Deploy API Services" \
  --limit 100 --json conclusion,createdAt \
  --jq '[.[] | select(.conclusion=="success") |
        select((.createdAt | fromdateiso8601) > (now - 2592000))] |
        length | "[api] Deploys in last 30 days: \(.)"'
```

**Bedrock AI (`deploy-bedrock.yml`):**

```bash
gh run list --repo "$REPO" --workflow "Deploy Bedrock AI" \
  --limit 100 --json conclusion,createdAt \
  --jq '[.[] | select(.conclusion=="success") |
        select((.createdAt | fromdateiso8601) > (now - 2592000))] |
        length | "[bedrock] Deploys in last 30 days: \(.)"'
```

**Self-Healing Agent (`deploy-self-healing.yml`):**

```bash
gh run list --repo "$REPO" --workflow "Deploy Self-Healing Agent" \
  --limit 100 --json conclusion,createdAt \
  --jq '[.[] | select(.conclusion=="success") |
        select((.createdAt | fromdateiso8601) > (now - 2592000))] |
        length | "[self-healing] Deploys in last 30 days: \(.)"'
```

**One-liner aggregate (sum all four pipelines):**

```bash
for WF in "Deploy Frontend (Dev)" "Deploy API Services" "Deploy Bedrock AI" "Deploy Self-Healing Agent"; do
  gh run list --repo "$REPO" --workflow "$WF" \
    --limit 100 --json conclusion,createdAt \
    --jq '[.[] | select(.conclusion=="success") | select((.createdAt | fromdateiso8601) > (now - 2592000))] | length'
done | paste -sd+ | bc | xargs -I{} echo "Total deploys across all CD pipelines (30 days): {}"
```

> `2592000` = 30 days in seconds (30 × 24 × 3600).
> Workflow display names must match exactly — verify with `gh workflow list --repo $REPO`.
> Once the total is measured, update the summary table in §3.1 and the resume claim in §9.

#### Change Failure Rate — CI

```bash
gh run list --repo "$REPO" --workflow "Continuous Integration" \
  --limit 50 --json conclusion \
  --jq '[.[] | select(.conclusion == "success" or .conclusion == "failure")] |
        {"total": length, "failed": ([.[] | select(.conclusion=="failure")] | length)} |
        "CFR: \(.failed)/\(.total) = \(.failed / .total * 100 | round)%"'
```

#### Workflow Name Discovery (for script maintenance)

```bash
gh run list --repo "$REPO" --limit 30 --json workflowName \
  --jq '[.[].workflowName] | unique | sort | .[]'
```

Run this whenever a workflow is renamed or a new one is added to update the script constants.

### 4.4 Script Limitations & Known Issues

| Issue | Impact | Mitigation |
|---|---|---|
| Workflow names must match display name exactly | Script silently returns no data if name is wrong | Run workflow discovery command first |
| `limit 10` may return < 10 successful runs | Average skewed on low-activity periods | Increase `--limit` value |
| CFR includes `develop` WIP failures | CFR inflated vs. production `main` | Filter by branch when `gh` supports it or use GitHub API directly |
| No ArgoCD metrics automated | TTSR / MTTR require manual operation | See §7 for pending tests |

---

## 5. Script Reference: `etcd-restore-rto-test.sh`

**Location**: `scripts/local/etcd-restore-rto-test.sh`
**Purpose**: Measures actual Recovery Time Objective (RTO) for a full etcd snapshot restore.
**Runtime requirements**: Must be run **on the Kubernetes control-plane EC2 node** with `sudo` access and AWS CLI authenticated via EC2 instance role.

> ⚠️ **DESTRUCTIVE OPERATION**: This script performs a real etcd restore. It stops etcd,
> replaces the data directory, and restarts the cluster. Run only during a planned maintenance
> window or against a non-critical state. The original data directory is preserved at
> `/var/lib/etcd-backup-<timestamp>` for rollback.

### 5.1 Pre-execution Setup

```bash
# Resolve the S3 bucket name from SSM (run on control-plane node or locally with AWS CLI)
BUCKET=$(aws ssm get-parameter \
  --name /k8s/development/scripts-bucket \
  --query Parameter.Value \
  --output text)

echo "Bucket: $BUCKET"
```

### 5.2 Execution Command

```bash
# On the control-plane EC2 node:
sudo bash etcd-restore-rto-test.sh "$BUCKET"
```

### 5.3 Six-Step Restore Sequence

The script times each step from `START=$(date +%s)`:

| Step | Operation | Command |
|---|---|---|
| **[1/6]** | Stop etcd | `sudo systemctl stop etcd` |
| **[2/6]** | Pull snapshot from S3 | `aws s3 cp s3://<BUCKET>/dr-backups/etcd/snapshot.db /tmp/etcd-snapshot-rto-test.db` |
| **[3/6]** | Restore snapshot | `sudo ETCDCTL_API=3 etcdctl snapshot restore ... --data-dir=/var/lib/etcd-restore` |
| **[4/6]** | Swap data directory | `sudo mv /var/lib/etcd /var/lib/etcd-backup-<timestamp>` + `sudo mv /var/lib/etcd-restore /var/lib/etcd` |
| **[5/6]** | Restart etcd | `sudo systemctl start etcd` |
| **[6/6]** | Wait for healthy | `etcdctl endpoint health` poll (2s intervals) |

### 5.4 Expected Output

```
=== etcd Restore RTO Test ===
Started: Thu Apr 17 15:30:00 UTC 2026
Control plane: ip-10-0-x-x (10.0.x.x)

[1/6] Stopping etcd...
      etcd stopped at +3s
[2/6] Pulling snapshot from S3...
      Snapshot downloaded at +18s
      Snapshot size: 4.7M
[3/6] Restoring snapshot...
      Restore complete at +21s
[4/6] Swapping data directory...
      Original data preserved at: /var/lib/etcd-backup-1713364200
[5/6] Restarting etcd...
      etcd started at +24s
[6/6] Waiting for cluster healthy...
      ...waiting (+26s)
      ...waiting (+28s)
https://127.0.0.1:2379 is healthy: ...

=== RESULT ===
Restore RTO: 32 seconds (0 min 32 sec)
Finished: Thu Apr 17 15:30:32 UTC 2026

Next step: update research-brain/local/dora-metrics-*.md with this number.
Rollback available at: /var/lib/etcd-backup-1713364200
```

### 5.5 Rollback Procedure

If the restore degrades cluster health:

```bash
# Stop etcd
sudo systemctl stop etcd

# Revert to original data directory
sudo mv /var/lib/etcd /var/lib/etcd-restored-failed
sudo mv /var/lib/etcd-backup-<timestamp> /var/lib/etcd

# Restart
sudo systemctl start etcd
```

### 5.6 Post-Test Required Actions

After a successful run, update the DORA metrics document with the measured RTO value:

```bash
# Update docs/ai-devops/dora-metrics-2026-04-17.md
# Replace:  | RTO (etcd restore) | unmeasured |
# With:     | RTO (etcd restore) | <N> seconds |
```

### 5.7 Script Limitations

| Issue | Impact | Mitigation |
|---|---|---|
| Must run on control-plane node | Cannot be automated from GitHub Actions | Add to maintenance runbook; trigger via SSM |
| Real restore — not a dry run | Cluster disruption during test | Plan for `etcd` downtime window (~30s expected) |
| Single-node etcd (no HA) | Any etcd restart causes K8s API outage briefly | Expected for solo-dev environment; document as known constraint |
| `snapshot.db` path is hardcoded | Script fails if DR bucket structure changes | Update `SNAPSHOT_KEY` constant if S3 key changes |

---

## 6. Service Inventory & ArgoCD Application Map

### 6.1 Platform Services (ArgoCD-managed, `kubernetes-app/platform/`)

| Service | Chart | Namespace | Purpose |
|---|---|---|---|
| Monitoring stack | `platform/charts/monitoring` | `monitoring` | Prometheus + Grafana + Loki + Tempo |
| ECR token refresh | `platform/charts/ecr-token-refresh` | `kube-system` | Refreshes ECR pull credentials |
| Crossplane providers | `platform/charts/crossplane-providers` | `crossplane-system` | Cloud resource provisioning |
| Crossplane XRDs | `platform/charts/crossplane-xrds` | `crossplane-system` | Composite resource definitions |
| ArgoCD Applications | `platform/argocd-apps/` | `argocd` | App-of-apps pattern |
| cert-manager config | `platform/cert-manager-config/` | `cert-manager` | TLS certificate issuance |

### 6.2 Workload Services (ArgoCD-managed, `kubernetes-app/workloads/`)

| Service | Chart | Namespace | Deployment Type |
|---|---|---|---|
| `nextjs` (site) | `workloads/charts/nextjs` | `nextjs-app` | Argo Rollout (Blue/Green) |
| `start-admin` | `workloads/charts/start-admin` | `start-admin` | Argo Rollout (Blue/Green) |
| `admin-api` | `workloads/charts/admin-api` | `admin-api` | Kubernetes Deployment (rolling) |
| `public-api` | `workloads/charts/public-api` | `public-api` | Kubernetes Deployment (rolling) |
| `wiki-mcp` | `workloads/charts/wiki-mcp` | `wiki-mcp` | Kubernetes Deployment |
| `golden-path-service` | `workloads/charts/golden-path-service` | `golden-path` | Kubernetes Deployment |

### 6.3 Total ArgoCD Application Count

**25/25 healthy** at measurement (2026-04-17). This includes both platform and workload applications registered in the `argocd` namespace via the App-of-Apps pattern.

> ⚠️ **Point-in-time snapshot — not a sustained metric.** This figure reflects a single observation on 2026-04-17. Agents must always include the date qualifier when citing it and must not present it as a live or continuously-verified health status.

### 6.4 Image Delivery Flow (SSM → ArgoCD)

```
GitHub Actions (deploy-frontend.yml / deploy-api.yml)
        │
        ▼  aws ssm put-parameter
SSM: /nextjs/development/image-uri = <ECR_URL>:<SHA>-r<attempt>
SSM: /start-admin/development/image-uri = <ECR_URL>:<SHA>-r<attempt>
        │
        ▼  ArgoCD Image Updater (2-min polling cycle)
ArgoCD Application: nextjs / start-admin
        │
        ▼  Argo Rollouts
Blue/Green: new green RS created → Analysis → Paused
        │
        ▼  SSM send-command → kubectl argo rollouts promote
Green RS active → Blue RS scaled down → Healthy ✅
```

---

## 7. Unmeasured Metrics — Pending Operational Tests

### 7.1 TTSR (Time to Self-Recover via GitOps)

**Definition**: Time from deliberate resource corruption to ArgoCD auto-revert to healthy state.

**Test procedure**:

```bash
# Step 1: Note current state of a non-critical resource
kubectl get deployment wiki-mcp -n wiki-mcp -o yaml > /tmp/wiki-mcp-original.yaml

# Step 2: Corrupt a label or replica count
kubectl patch deployment wiki-mcp -n wiki-mcp \
  --patch '{"spec":{"replicas":0}}'

START=$(date +%s)

# Step 3: Wait for ArgoCD auto-sync (default: 3-minute polling + apply)
# ArgoCD will detect OutOfSync and revert to git state

# Step 4: Confirm healthy
argocd app get wiki-mcp --grpc-web | grep "Health Status"
END=$(date +%s)

echo "TTSR: $(( END - START )) seconds"
```

**Expected range**: 3–5 minutes (ArgoCD polling interval + sync time).

### 7.2 MTTR (Mean Time to Recovery — Deploy Rollback)

**Definition**: Time from a confirmed bad deploy to rollback completion to last-known-good state.

**Test procedure**:

```bash
# Step 1: Push a deploy that will fail health checks (bad config, wrong port)
# Step 2: Record time of first alert
# Step 3: Issue rollback — update SSM URI to previous tag, ArgoCD Image Updater detects
# Step 4: Confirm Rollout returns to Healthy
# Record: alert detection → rollback confirmation
```

**Expected range**: 5–10 minutes (alert → manual intervention → ArgoCD reconcile → Healthy).

### 7.3 RTO (Recovery Time Objective — etcd Restore)

**Measured by**: `scripts/local/etcd-restore-rto-test.sh`
**Status**: Script is ready. Execution requires a maintenance window on the control-plane node.
**Expected range**: 30–90 seconds (S3 download + restore + etcd restart + API server healthy).

---

## 8. QA Gap Analysis

> This section identifies gaps that must be closed to pass a rigorous DORA QA review
> and satisfy production-readiness criteria. Items are prioritised by impact.

### 8.1 Critical Gaps (Block QA Pass)

#### GAP-01: CFR Not Measured on Protected Branch

| Field | Value |
|---|---|
| **Gap** | Change Failure Rate measured only on `develop` — not `main` |
| **Impact** | Cannot report a meaningful CFR. All failures are pre-merge WIP noise |
| **Required action** | Measure CFR on `main`-branch CD runs after a 30-day stabilisation period |
| **Command to run** | Modify `dora-metrics-snapshot.sh` to filter by `branch: main` using `gh run list --branch main` |
| **QA criterion** | CFR ≤ 15% on `main` branch to claim "High" DORA performer |

#### GAP-02: RTO Not Measured (etcd Restore)

| Field | Value |
|---|---|
| **Gap** | `etcd-restore-rto-test.sh` exists but has never been executed |
| **Impact** | Cannot quantify disaster recovery capability |
| **Required action** | Schedule maintenance window; execute script on control-plane node |
| **Command** | `BUCKET=$(aws ssm get-parameter --name /k8s/development/scripts-bucket --query Parameter.Value --output text) && sudo bash scripts/local/etcd-restore-rto-test.sh "$BUCKET"` |
| **QA criterion** | RTO < 15 minutes for DORA Elite; < 60 minutes for industry-standard K8s DR |

#### GAP-03: TTSR Not Measured (ArgoCD Self-Heal)

| Field | Value |
|---|---|
| **Gap** | No measured or documented time for ArgoCD drift recovery |
| **Impact** | Cannot claim GitOps self-healing capability in a verifiable way |
| **Required action** | Execute TTSR test against `wiki-mcp` (lowest-risk workload) |
| **QA criterion** | TTSR < 5 minutes to claim automated GitOps recovery |

#### GAP-04: MTTR Not Measured (Rollback)

| Field | Value |
|---|---|
| **Gap** | No measured time for failed-deploy recovery via Argo Rollouts abort/rollback |
| **Impact** | Cannot quantify operational recovery speed |
| **Required action** | Simulate a bad deploy (bad env var) and time the full rollback cycle |
| **QA criterion** | MTTR < 30 minutes to claim "Elite" DORA; < 1 hour for "High" |

### 8.2 High Priority Gaps (Improve QA Score)

#### GAP-05: No Smoke Tests Post-CD

| Field | Value |
|---|---|
| **Gap** | `deploy-frontend.yml` completes with Rollout as Healthy, but no functional health check runs post-promote |
| **Impact** | A deploy that promotes a broken image to green RS could pass CI/CD without detection |
| **Required action** | Add a `smoke-test` job post-`promote-site` that hits the application health endpoint via CloudFront |
| **Example** | `curl -sf https://<DOMAIN>/api/health` with retry logic |

#### GAP-06: No Branch Protection on `main` for CD Gate

| Field | Value |
|---|---|
| **Gap** | `deploy-frontend.yml` is triggered by `workflow_dispatch` and `repository_dispatch` — not gated on `main` merges |
| **Impact** | Ad-hoc deploys can bypass the PR review process |
| **Required action** | Define a `production` GitHub Environment with required reviewer approvals; add it to the summary job |

#### GAP-07: CFR Scope Ambiguity in Script

| Field | Value |
|---|---|
| **Gap** | The script comment says "note: all failures on develop — WIP noise" but this is not enforced by the script logic |
| **Impact** | If the script is re-run without context, the CFR figure appears valid |
| **Required action** | Update script to include `--branch main` flag or add a `# CAUTION: this measures all branches` header |

#### GAP-08: ArgoCD Application Health Not Automated in Snapshot

| Field | Value |
|---|---|
| **Gap** | ArgoCD healthy count (25/25) is claimed but not captured by `dora-metrics-snapshot.sh` |
| **Impact** | Future runs cannot verify this figure automatically |
| **Required action** | Add ArgoCD health query to the snapshot script (requires ArgoCD CLI or API token) |
| **Commands to add** | See §4 of `dora-metrics-2026-04-17.md` for ArgoCD `jq` commands |

### 8.3 Medium Priority Gaps (Improve Confidence)

#### GAP-09: No Prometheus Alert Firing Test

| Field | Value |
|---|---|
| **Gap** | Alert detection time (30s) is inferred from config, not from a synthetic alert firing test |
| **Required action** | Fire a test alert via `kubectl exec` into Prometheus alertmanager API; measure end-to-end notification latency |

#### GAP-10: etcd Snapshot Freshness Not Verified Before RTO Test

| Field | Value |
|---|---|
| **Gap** | `etcd-restore-rto-test.sh` downloads `snapshot.db` without verifying snapshot age |
| **Impact** | A stale snapshot would produce a misleading RTO figure and could restore to a very old cluster state |
| **Required action** | Add snapshot metadata check: `aws s3api head-object --bucket <BUCKET> --key dr-backups/etcd/snapshot.db` — verify `LastModified` is < 24h old |

#### GAP-11: Deployment Frequency Measures Only Frontend Pipeline ⬆️ Elevated to High

| Field | Value |
|---|---|
| **Gap** | `deploy-api.yml`, `deploy-bedrock.yml`, and `deploy-self-healing.yml` are not captured in the frequency count |
| **Impact** | The published figure of 34 is a **floor**, not the true cadence. Agents must not present it as the total without the scope qualifier |
| **Current mitigation** | §3.1 table and §9 resume claim are now labelled “frontend-only — floor figure”; claim is safe to use with that qualifier |
| **Required action** | Run the one-liner aggregate command in §4.3 (“One-liner aggregate”), record the total, then update §3.1 and §9 with the full figure |
| **Commands** | Documented and ready to execute — see §4.3 → “Deployment Frequency (last 30 days)” |
| **Priority** | **High** — the metric is partial; a full count is needed to remove the scope qualifier from the resume claim |

#### GAP-12: No SLO/SLA Definition

| Field | Value |
|---|---|
| **Gap** | No formal Service Level Objectives defined for uptime, latency, or error rate |
| **Impact** | DORA MTTR cannot be anchored to a specific availability target |
| **Required action** | Define at minimum: `p95 latency < 500ms`, `error rate < 1%`, `uptime > 99.5%` in Grafana SLO panels |

---

## 9. Permitted Resume Claims

The following claims are **concrete, script-verified, and defensible** as of 2026-04-17:

| Claim | Evidence |
|---|---|
| "13-minute commit-to-rollout lead time — measured from `git push` to Argo Rollouts Healthy on the new green ReplicaSet (includes ArgoCD Image Updater pickup and blue/green promotion)" | `dora-metrics-snapshot.sh` output: CI avg 5.3 min + CD avg 7.5 min; CD workflow blocks on `promote-site` → Rollout Healthy before exiting |
| "34+ deployments in 30 days via frontend pipeline alone (floor figure) — on-demand delivery cadence; API, Bedrock, and self-healing pipelines not yet summed" | `dora-metrics-snapshot.sh`: 34 successful `Deploy Frontend (Dev)` runs, 2026-03-18 to 2026-04-17; aggregate query across all CD pipelines pending (see §4.3 and GAP-11) |
| "25 ArgoCD-managed applications — 25/25 healthy at time of measurement (2026-04-17)" | ArgoCD API: `argocd app list -o json` |
| "30-second worst-case alert detection cycle via Prometheus scrape_interval + evaluation_interval" | `kubectl get configmap prometheus-server -n monitoring -o jsonpath='{...}'` |
| "Blue/Green deployments with automated promotion via Argo Rollouts and SSM proxy" | `deploy-frontend.yml` → `promote-site` / `promote-admin` jobs |
| "OIDC keyless authentication with AROA masking — no stored AWS credentials in CI" | `.github/actions/configure-aws/action.yml` |
| "Automated IaC security scanning via Checkov → SARIF → GitHub Security tab" | `ci.yml`: `iac-security-scan` job |

**Do NOT claim** until measured:

- CFR (until measured on `main` branch post-stabilisation)
- RTO (until `etcd-restore-rto-test.sh` is executed)
- TTSR / MTTR (until operational tests are completed)

---

## 10. Next Actions

### Priority 1 — Execute Pending Operational Tests

| Action | Script / Command | Owner | Target Date |
|---|---|---|---|
| Run etcd RTO test | `scripts/local/etcd-restore-rto-test.sh` | Nelson | Next maintenance window |
| Run TTSR test (ArgoCD self-heal) | Manual: corrupt `wiki-mcp`, time recovery | Nelson | Next available slot |
| Run MTTR test (rollback simulation) | Manual: bad deploy → Argo abort | Nelson | Next available slot |

### Priority 2 — Close QA Gaps

| Gap | Action | Effort |
|---|---|---|
| GAP-01 | Add `--branch main` to CFR query in snapshot script | 15 min |
| GAP-05 | Add `smoke-test` job to `deploy-frontend.yml` | 2 hours |
| GAP-08 | Add ArgoCD health block to `dora-metrics-snapshot.sh` | 30 min |
| GAP-10 | Add snapshot freshness check to RTO test script | 30 min |
| GAP-11 | Extend deploy frequency to all CD pipelines | 45 min |
| GAP-12 | Define SLOs in Grafana dashboard | 3 hours |

### Priority 3 — Update Documentation

After completing operational tests:

1. Update `docs/ai-devops/dora-metrics-2026-04-17.md` with measured RTO, TTSR, MTTR values
2. Add measured values to `generate_resume_domain.md`
3. Run `/kb-sync` to propagate to knowledge base

---

*Document generated: 2026-04-17T15:53:00+01:00*
*Review status: Ongoing — concrete metrics locked, pending metrics require operational test execution*
*Author: Nelson Lamounier*
