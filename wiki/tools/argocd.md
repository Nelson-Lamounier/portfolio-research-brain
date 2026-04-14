---
title: ArgoCD
type: tool
tags: [kubernetes, gitops, argocd, continuous-delivery]
sources: [raw/step-function-runtime-logging.md]
created: 2026-04-13
updated: 2026-04-13
---

# ArgoCD

GitOps controller installed as Step 8 of the [[k8s-bootstrap-pipeline]] control plane bootstrap. Manages all cluster workloads declaratively from Git.

## Role in the Architecture

After the cluster infrastructure is bootstrapped (kubeadm, [[calico]], [[aws-ccm]]), ArgoCD takes over:

- Syncs all applications from Git: Traefik (ingress), cert-manager (TLS), Next.js, admin-api, public-api, start-admin, Prometheus + Loki + Grafana (observability)
- Any Git commit auto-deploys
- Adopts Helm releases created during bootstrap (e.g., CCM, Calico) and manages future upgrades

## Installation

The `argocd.py` step:

1. Installs ArgoCD from a vendored Helm chart
2. Applies the **App-of-Apps** root application
3. From this point, ArgoCD owns the declarative state of all cluster workloads

## Two Execution Paths

| Path | What runs | When to use |
|------|-----------|-------------|
| `just bootstrap-run $INSTANCE_ID` | `bootstrap_argocd.py` only (ArgoCD steps) | Day-2 ops: config drift, secret rotation, pod restart |
| SM-A (Step Functions) | Full `control_plane.py` including ArgoCD | New instance, full cluster rebuild |

`bootstrap-run` uses `AWS-RunShellScript` directly — it does **not** trigger EventBridge or SM-B. Use SM-A for anything requiring kubeadm, worker rejoin, or self-healing chain.

## Related Pages

- [[k8s-bootstrap-pipeline]] — project context
- [[self-hosted-kubernetes]] — where ArgoCD fits in the bootstrap sequence
- [[event-driven-orchestration]] — SM-A → EventBridge → SM-B pattern
- [[github-actions]] — CI/CD pipeline that deploys to the cluster ArgoCD manages
