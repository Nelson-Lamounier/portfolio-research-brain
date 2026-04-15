---
title: ArgoCD
type: tool
tags: [kubernetes, gitops, argocd, continuous-delivery]
sources: [raw/step-function-runtime-logging.md, raw/kubernetes_system_design_review.md, raw/base-stack-review.md, raw/kubernetes_app_review.md, raw/notification_implementation_review.md]
created: 2026-04-13
updated: 2026-04-15
---

# ArgoCD

GitOps controller installed as Step 8 of the [[k8s-bootstrap-pipeline]] control plane bootstrap. Manages all cluster workloads declaratively from Git after the infrastructure layer is bootstrapped.

## Role in the Architecture

After the cluster infrastructure is bootstrapped (kubeadm, [[calico]], [[aws-ccm]]), ArgoCD takes over complete ownership of cluster state:

- Syncs all platform components: [[traefik]] (ingress), cert-manager (TLS), [[observability-stack]] (Prometheus, Loki, Tempo, Grafana), Descheduler, Calico PDBs, priority classes
- Syncs all workloads: Next.js, start-admin, [[hono|public-api]], [[hono|admin-api]]
- Any Git commit auto-deploys
- Adopts Helm releases created during bootstrap (CCM, Calico) and manages future upgrades

## App-of-Apps Structure

Two root applications are seeded imperatively by `bootstrap_argocd.py` and never touched again — all subsequent changes go through git commits:

```
argocd namespace
│
├── platform-root  (sync-wave: 0)  → platform/argocd-apps/   (14 child Applications)
└── workloads-root (sync-wave: 1)  → workloads/argocd-apps/  (ApplicationSet + manual apps)
```

| Root App | Manages |
|---|---|
| `platform-root-app.yaml` | [[traefik]], cert-manager, [[aws-ebs-csi\|EBS CSI]], [[observability-stack\|monitoring]], Descheduler, Calico PDBs, [[crossplane]], metrics-server |
| `workloads-root-app.yaml` | Next.js, start-admin, [[hono\|public-api]], [[hono\|admin-api]], crossplane workloads |

`platform-root` (wave 0) is fully synced before ArgoCD evaluates `workloads-root` (wave 1). Both use `automated.selfHeal: true` — any manual `kubectl edit` on a child manifest is reverted within seconds.

## Sync Waves — Full Wave Map

ArgoCD applies manifests in ascending wave order within a sync operation:

| Wave | What deploys | Why this order |
|---|---|---|
| `0` | cert-manager, platform-root itself | CRDs must exist before any Certificate resources |
| `1` | cluster-autoscaler, cert-manager-config, workloads-root | infra before workloads |
| `2` | [[traefik]] DaemonSet | must be running before ArgoCD ingress is applied |
| `3` | metrics-server, [[observability-stack\|monitoring stack]] | metrics-server required for HPA; monitoring before business apps |
| `4` | argo-rollouts, [[aws-ebs-csi]], [[crossplane]], descheduler, ecr-token-refresh | storage + delivery before app workloads |
| `5` | Next.js, start-admin, public-api, admin-api, crossplane-providers | business apps |
| `6` | crossplane-xrds | XRDs require providers from wave 5 |

## ApplicationSet — Self-Service Workload Registration

The `workloads-root` uses a **Git Directory Generator ApplicationSet** that scans `workloads/charts/*/` and creates one ArgoCD Application per directory:

```yaml
generators:
  - git:
      directories:
        - path: kubernetes-app/workloads/charts/*
        - path: kubernetes-app/workloads/charts/golden-path-service
          exclude: true   # template only, not deployed
        - path: kubernetes-app/workloads/charts/nextjs
          exclude: true   # manual app — needs Image Updater annotations
        - path: kubernetes-app/workloads/charts/start-admin
          exclude: true   # same
```

Adding a new service = create `workloads/charts/my-service/chart/` + `my-service-values.yaml` → commit → ArgoCD creates the Application automatically. See [[helm-chart-architecture]] for the chart template design.

## Standard Sync Options

All Applications share:

| Option | Purpose |
|---|---|
| `CreateNamespace=true` | ArgoCD creates the target namespace if absent |
| `PruneLast=true` | Resource deletion happens after creation — prevents ordering issues during upgrades |
| `ServerSideApply=true` | Uses Kubernetes Server-Side Apply; avoids last-applied annotation conflicts with Helm |
| `ApplyOutOfSyncOnly=true` | Only applies resources that differ — reduces API server load on large syncs |

And retry with exponential back-off on every Application:

```yaml
retry:
  limit: 3
  backoff:
    duration: 5s
    factor: 2
    maxDuration: 3m
```

## `selfHeal` vs `ignoreDifferences`

`workloads-root` uses `ignoreDifferences` to protect runtime-patched Helm parameters from being overwritten by `selfHeal`:

```yaml
ignoreDifferences:
  - group: argoproj.io
    kind: Application
    jsonPointers:
      - /spec/source/helm/parameters
```

During bootstrap, `inject_monitoring_helm_params` patches live Helm parameters (IP allowlist CIDRs from SSM) directly into running Applications via the ArgoCD API. These values are not in Git. Without `ignoreDifferences`, every 3-minute self-heal cycle would overwrite them with the placeholder values, breaking Traefik rate-limit middleware.

## ArgoCD Bootstrap Sequence (`bootstrap_argocd.py`)

The Python orchestrator (`bootstrap_argocd.py`) is the Day-0 imperative layer. Once it completes, ArgoCD takes over declaratively — all subsequent changes go through git.

| Step | Function | Detail |
|---|---|---|
| 1 | `create_namespace` | `kubectl apply -f namespace.yaml` |
| 2 | `resolve_deploy_key` | SSH private key from SSM SecureString |
| 3 | `create_repo_secret` | Creates `argocd/repo-cdk-monitoring` K8s Secret (type: `repository`) |
| 4 | `preserve_argocd_jwt_key` | Read JWT signing key from SSM before install — prevents session invalidation on rebuild |
| 5 | `install_argocd` | `kubectl apply -f install.yaml` (vendored manifest) |
| 6 | `create_default_project` | Required for ArgoCD v3.x — default project no longer auto-created |
| 7 | `configure_argocd_server` | Patches `argocd-cmd-params-cm`: `rootpath=/argocd`, `insecure=true` (TLS terminated by Traefik) |
| 8 | `configure_health_checks` | Adds custom health check logic for Argo Rollout resources to `argocd-cm` |
| 9 | `apply_root_app` | Seeds `platform-root` + `workloads-root` → ArgoCD takes over from here |
| 10 | `inject_monitoring_helm_params` | Patches IP allowlist CIDRs into live Applications via ArgoCD API |
| 11 | `seed_ecr_credentials` | Creates `ecr-token-refresh` Secret with initial valid token (CronJob hasn't fired yet) |
| 12 | `provision_crossplane_credentials` | Creates `crossplane-aws-creds` Secret from AWS Secrets Manager |
| 13 | `restore_tls_cert` | Restores Let's Encrypt cert from SSM — avoids rate-limit reissuance on rebuild |
| 14 | `restore_argocd_jwt_key` | Restores JWT signing key preserved in step 4 |
| 15 | `wait_for_argocd` | Polls `/healthz` until ArgoCD server responds |
| 16 | `apply_ingress` | Creates Traefik `IngressRoute` for ArgoCD UI — non-fatal if Traefik CRDs aren't ready yet |
| — | `create_ci_bot` / `generate_ci_token` | ArgoCD service account for CI; token → AWS Secrets Manager |
| — | `set_admin_password` | Read from SSM |
| — | `backup_tls_cert` / `backup_argocd_secret_key` | DR backup to SSM SecureString |

**Non-fatal steps:** `apply_cert_manager_issuer` and `apply_ingress` are wrapped in `try/except` — Traefik and cert-manager CRDs may not be ready during first bootstrap (ArgoCD is still syncing). SM-B (`deploy.py`) retries these idempotently.

## JWT Key Continuity

On every cluster rebuild, ArgoCD generates a new JWT signing key if one is not explicitly set — invalidating all active admin sessions. The bootstrap script:

1. Reads the existing JWT key from SSM SecureString before installing ArgoCD
2. Restores it after installation completes

This means operators do not need to re-authenticate after a control-plane replacement.

## Image Updater

`nextjs`, `start-admin`, and `public-api` use ArgoCD Image Updater for continuous delivery:

```yaml
annotations:
  argocd-image-updater.argoproj.io/nextjs.update-strategy: newest-build
  argocd-image-updater.argoproj.io/nextjs.allow-tags: "regexp:^[0-9a-f]{7,40}(-r[0-9]+)?$"
  argocd-image-updater.argoproj.io/write-back-method: "git:secret:argocd/repo-cdk-monitoring"
  argocd-image-updater.argoproj.io/git-branch: develop
```

CI pushes a new SHA-tagged image. Image Updater detects it via ECR API polling, commits the new tag to `.argocd-source-nextjs.yaml` in `develop`, and ArgoCD's `selfHeal` loop picks up the git change and triggers a new Rollout revision.

The **`-rN` retry suffix** (`a3f72bc-r2` vs `a3f72bc-r1`) prevents tag overwrites on pipeline retries. The **`newest-build`** strategy selects by build timestamp rather than semver — correct for SHA-tagged images with no semantic version ordering.

`nextjs` and `start-admin` are excluded from the ApplicationSet because Image Updater annotations cannot be injected by the generic template — they have manually committed Application manifests.

## `ignoreDifferences` for Bootstrap-Injected Secrets

The monitoring stack ArgoCD application uses `ignoreDifferences` for:

- SNS topic ARN (injected into Helm params during bootstrap)
- Prometheus credentials

Without this, ArgoCD would revert these runtime-injected values on every sync, breaking the monitoring stack.

## Two Execution Paths

| Path | What runs | When to use |
|---|---|---|
| `just bootstrap-run $INSTANCE_ID` | `bootstrap_argocd.py` only | Day-2 ops: config drift, secret rotation, pod restart |
| SM-A (Step Functions) | Full `control_plane.py` including ArgoCD | New instance, full cluster rebuild |

`bootstrap-run` uses `AWS-RunShellScript` directly — it does **not** trigger EventBridge or SM-B. Use SM-A for anything requiring kubeadm, worker rejoin, or the self-healing chain.

## ArgoCD Notifications

The notifications controller (bundled with ArgoCD ≥2.6) is deployed at sync-wave 4 as a self-managing application. It posts **GitHub commit status updates** for every application sync and health event, providing deployment traceability directly in the Git repository.

**Authentication**: GitHub App (not a PAT token) — credentials stored as SSM SecureStrings and injected into the `argocd-notifications-secret` Kubernetes Secret by bootstrap Step 5e (`provision_argocd_notifications_secret` in `steps/apps.py`).

**`defaultTriggers`** applies to all ArgoCD Applications without per-application annotation:
- `on-sync-succeeded` → GitHub `success` status
- `on-sync-failed` → GitHub `failure` status
- `on-health-degraded` → GitHub `failure` status

Status label: `argocd/<app-name>` — visible in GitHub PR merge protection rules for all 10 applications.

**Bootstrap Step 5e is non-fatal**: if the SSM parameters are not yet populated, bootstrap continues with a warning. Re-running `bootstrap_argocd.py` after storing credentials completes the setup.

See [[notification-architecture]] for the full notifications architecture including the 5 SNS topics and 12 Grafana alert rules.

## Related Pages

- [[k8s-bootstrap-pipeline]] — project context
- [[self-hosted-kubernetes]] — where ArgoCD fits in the bootstrap sequence
- [[helm-chart-architecture]] — Helm chart design, ApplicationSet, golden-path template
- [[notification-architecture]] — ArgoCD Notifications details + 3 notification planes + 12 Grafana alert rules
- [[aws-ebs-csi]] — EBS CSI Driver deployed at Sync Wave 4
- [[crossplane]] — Crossplane managed at waves 4/5/6
- [[event-driven-orchestration]] — SM-A → EventBridge → SM-B pattern
- [[github-actions]] — CI/CD pipeline that deploys to the cluster ArgoCD manages
- [[argo-rollouts]] — progressive delivery controller managed by ArgoCD
- [[traefik]] — platform component; IngressRoute ownership boundary
- [[observability-stack]] — monitoring Helm releases managed by ArgoCD
- [[disaster-recovery]] — JWT key and TLS cert backup/restore in bootstrap
