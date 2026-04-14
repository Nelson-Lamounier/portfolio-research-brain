---
title: ArgoCD
type: tool
tags: [kubernetes, gitops, argocd, continuous-delivery]
sources: [raw/step-function-runtime-logging.md, raw/kubernetes_system_design_review.md]
created: 2026-04-13
updated: 2026-04-14
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

Two root applications are applied by `bootstrap_argocd.py`:

| Root App | Manages |
|---|---|
| `platform-root-app.yaml` | Traefik, cert-manager, monitoring stack, Descheduler, Calico PDBs, priority classes |
| `workloads-root-app.yaml` | Next.js, start-admin, public-api, admin-api |

**Sync waves** enforce dependency ordering: infrastructure platform components (wave 1) sync before application workloads (wave 2).

## ArgoCD Bootstrap Sequence (41 steps via `bootstrap_argocd.py`)

| Phase | Key steps |
|---|---|
| Namespace + credentials | Create `argocd` namespace, resolve SSH deploy key from SSM, create repo secret |
| JWT key continuity | **Preserve** ArgoCD JWT signing key before install → **restore** after (prevents session invalidation on cluster rebuild) |
| Installation | `kubectl apply` ArgoCD install manifest |
| App-of-Apps | Apply `platform-root-app.yaml` and `workloads-root-app.yaml` |
| Monitoring injection | Inject SNS topic ARN and Prometheus credentials into Helm params |
| ECR seeding | Day-1 ECR credential seed (before the ECR refresh CronJob fires) |
| TLS | Restore TLS cert from SSM; apply cert-manager `ClusterIssuer` |
| Networking | Wait for ArgoCD; apply Traefik `IngressRoute`; create IP allowlist middleware |
| Auth hardening | Set admin password from SSM; generate CI bot token → Secrets Manager |
| DR backup | Backup TLS cert and ArgoCD JWT key to SSM |

**Non-fatal steps:** `apply_cert_manager_issuer` and `apply_ingress` are wrapped in `try/except` because Traefik and cert-manager CRDs may not be ready during first bootstrap (ArgoCD is still syncing). SM-B (`deploy.py`) retries these idempotently.

## JWT Key Continuity

On every cluster rebuild, ArgoCD generates a new JWT signing key if one is not explicitly set — invalidating all active admin sessions. The bootstrap script:

1. Reads the existing JWT key from SSM SecureString before installing ArgoCD
2. Restores it after installation completes

This means operators do not need to re-authenticate after a control-plane replacement.

## Image Updater

ArgoCD Image Updater monitors ECR image tags. The **`-rN` retry suffix** in the tag format is an Image Updater convention to force a re-tag event when the underlying image digest changes without a version bump — ensuring Image Updater always detects a new build even if the semantic version tag is unchanged.

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

## Related Pages

- [[k8s-bootstrap-pipeline]] — project context
- [[self-hosted-kubernetes]] — where ArgoCD fits in the bootstrap sequence
- [[event-driven-orchestration]] — SM-A → EventBridge → SM-B pattern
- [[github-actions]] — CI/CD pipeline that deploys to the cluster ArgoCD manages
- [[argo-rollouts]] — progressive delivery controller managed by ArgoCD
- [[traefik]] — platform component managed by ArgoCD App-of-Apps
- [[observability-stack]] — monitoring Helm releases managed by ArgoCD
- [[disaster-recovery]] — JWT key and TLS cert backup/restore in bootstrap
