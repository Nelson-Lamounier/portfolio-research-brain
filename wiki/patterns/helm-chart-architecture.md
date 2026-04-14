---
title: Helm Chart Architecture (Golden-Path Pattern)
type: pattern
tags: [kubernetes, helm, argocd, patterns, gitops, templates]
sources: [raw/kubernetes_app_review.md]
created: 2026-04-14
updated: 2026-04-14
---

# Helm Chart Architecture (Golden-Path Pattern)

The Helm chart design pattern used across all workloads in the [[k8s-bootstrap-pipeline]] project. A **golden-path service template** defines all production defaults once; individual services extend it via values files. Combined with ArgoCD's ApplicationSet, adding a new service to the cluster requires only creating a chart directory.

## Chart Layout

Every workload follows an identical layout:

```
workloads/charts/<service>/
├── chart/
│   ├── Chart.yaml
│   ├── values.yaml              # base defaults (committed, safe to share)
│   ├── templates/
│   │   ├── _helpers.tpl         # named templates (labels, selectors)
│   │   ├── rollout.yaml         # Argo Rollout (or deployment.yaml)
│   │   ├── service.yaml
│   │   ├── ingressroute.yaml    # Traefik CRD (may be disabled via flag)
│   │   ├── hpa.yaml
│   │   ├── pdb.yaml
│   │   ├── network-policy.yaml
│   │   ├── resource-quota.yaml
│   │   └── analysis-template.yaml
└── <service>-values.yaml        # runtime overrides (image tag, resource sizing)
```

The `values.yaml` / `<service>-values.yaml` split maps to the ArgoCD source:

```yaml
source:
  helm:
    valueFiles:
      - ../nextjs-values.yaml    # sits one level above chart/
```

## Feature Flags

Every optional Kubernetes resource is guarded by a feature flag in `values.yaml`:

```yaml
{{- if .Values.hpa.enabled }}
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
...
{{- end }}
```

| Flag | Resource guarded |
|---|---|
| `hpa.enabled` | HorizontalPodAutoscaler |
| `pdb.enabled` | PodDisruptionBudget |
| `networkPolicy.enabled` | NetworkPolicy |
| `ingress.enabled` | Traefik IngressRoute |
| `serviceMonitor.enabled` | Prometheus ServiceMonitor |
| `crossplane.bucket.enabled` | Crossplane `EncryptedBucket` claim |
| `crossplane.queue.enabled` | Crossplane `MonitoredQueue` claim |

A staging environment with no HPA sets `hpa.enabled: false` — no chart fork needed.

## Named Templates — `selectorLabels` vs `fullLabels`

Charts share label logic via named templates in `_helpers.tpl`:

```
{{- define "nextjs.selectorLabels" -}}
app: nextjs
{{- end }}

{{- define "nextjs.fullLabels" -}}
{{ include "nextjs.selectorLabels" . }}
app.kubernetes.io/name: nextjs
app.kubernetes.io/version: {{ .Values.image.tag | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}
```

**Why the separation:**
- `selectorLabels` is used in `matchLabels` — this is **immutable** on Deployments and StatefulSets. Changing it after deployment requires deleting the resource.
- `fullLabels` is used in `metadata.labels` — can change freely (e.g., version label updates on every deploy).

Using both in the wrong place is a common Helm mistake that causes `kubectl apply` to fail with "field is immutable".

## Golden-Path Service Template

`workloads/charts/golden-path-service/` is excluded from the ApplicationSet and exists as a **copy template** only. It demonstrates all production defaults a new service should inherit:

| Default | Value |
|---|---|
| Health probes | Three-probe model: startup + readiness + liveness |
| Graceful shutdown | `preStop: sleep 5` lifecycle hook for connection draining |
| Crossplane | XRD claims (`EncryptedBucket`, `MonitoredQueue`) with `enabled: false` guards |
| NetworkPolicy | Default-deny + Traefik allow (VPC CIDR + pod CIDR ipBlocks) |
| ServiceMonitor | Prometheus scraping configured |
| HPA | CPU-based, `minReplicas: 2`, `maxReplicas: 5` |
| PodDisruptionBudget | `minAvailable: 1` |

To bootstrap a new service:
1. Copy `golden-path-service/` to `workloads/charts/my-service/`
2. Fill in `image.repository`
3. Commit and push to `develop`

The [[argocd]] ApplicationSet detects the new directory and creates the Application automatically — no manual ArgoCD configuration.

## Secrets vs ConfigMap Classification

`deploy.py` enforces an explicit split of every environment variable:

```python
_NEXTJS_SECRET_KEYS = [
    "NEXTAUTH_SECRET", "NEXTAUTH_URL",
    "AUTH_COGNITO_USER_POOL_ID", "AUTH_COGNITO_ID",
    "BEDROCK_AGENT_API_KEY", "REVALIDATION_SECRET",
]

_NEXTJS_CONFIG_KEYS = [
    "DYNAMODB_TABLE_NAME", "DYNAMODB_GSI1_NAME",
    "ASSETS_BUCKET_NAME", "AWS_DEFAULT_REGION",
]
```

Sensitive values → `Opaque` Kubernetes Secret (`nextjs-secrets`). Non-sensitive infrastructure references → `ConfigMap` (`nextjs-config`). The Rollout template mounts both via `envFrom` so the container sees a flat environment.

AWS credentials appear in **neither** — they come from the EC2 Instance Profile via IMDS.

## Ownership Boundary

A clear boundary exists between what ArgoCD/Helm manages and what `deploy.py` manages:

| Resource | Owner | Why |
|---|---|---|
| Rollout, Service, HPA, PDB, NetworkPolicy, ResourceQuota | **ArgoCD (Helm)** | Fully declarative, no runtime secrets |
| Traefik IngressRoute (nextjs, preview) | **deploy.py** | Contains SSM-sourced CloudFront origin secret |
| K8s Secret (nextjs-secrets, start-admin-secrets) | **deploy.py** | SSM-sourced values; committing to git is a security violation |
| ConfigMap (nextjs-config) | **deploy.py** | SSM-sourced; updated at every deploy |
| Traefik IngressRoute (ArgoCD UI) | **bootstrap_argocd.py** | Seeded once; Traefik CRDs may not exist at ArgoCD install time |
| cert-manager ClusterIssuer | **bootstrap_argocd.py** | Route 53 zone ID + cross-account role ARN from SSM |
| Image tag in `.argocd-source-*.yaml` | **ArgoCD Image Updater** | ECR polling → git write-back |

## Multi-Source Applications

Two platform Applications separate chart and values sources:

```yaml
spec:
  sources:
    # Source 1 — values from the monorepo (pinned to develop)
    - repoURL: git@github.com:Nelson-Lamounier/cdk-monitoring.git
      targetRevision: develop
      ref: values

    # Source 2 — chart from upstream Helm registry (pinned to minor range)
    - repoURL: https://traefik.github.io/charts
      chart: traefik
      targetRevision: "36.*"
      helm:
        valueFiles:
          - $values/kubernetes-app/k8s-bootstrap/system/traefik/traefik-values.yaml
```

A single PR can bump both the application code and its infrastructure configuration atomically. The chart is pinned to `36.*` (SemVer minor range) — receives patch releases automatically but is protected against breaking major changes.

## Related Pages

- [[argocd]] — ApplicationSet, sync waves, selfHeal, Image Updater
- [[argo-rollouts]] — blue/green Rollout replacing Deployment
- [[traefik]] — IngressRoute ownership boundary; secret rotation pattern
- [[crossplane]] — XRD claims in the golden-path template
- [[calico]] — NetworkPolicy enforcement (default-deny + dual ipBlock)
- [[k8s-bootstrap-pipeline]] — project context
