# kubernetes-app: Kubernetes Concepts & ArgoCD Implementation Review

> **Scope**: This document reviews `kubernetes-app/` with a focus on Kubernetes concepts
> applied, ArgoCD patterns, and Helm design. Cluster bootstrap and CI/CD orchestration are
> covered only where they directly define a Kubernetes or ArgoCD pattern.

---

## 1. Repository Layout

```
kubernetes-app/
├── k8s-bootstrap/            # Day-0 cluster setup (ArgoCD install + root app seed)
│   └── system/argocd/        # bootstrap_argocd.py + steps/* + manifests
├── platform/
│   ├── argocd-apps/          # 14 ArgoCD Application manifests (infrastructure tier)
│   └── charts/               # In-repo Helm charts: monitoring, crossplane-xrds, ecr-token-refresh
└── workloads/
    ├── argocd-apps/          # ArgoCD Application manifests (business apps)
    └── charts/               # Per-service Helm charts: nextjs, start-admin, public-api, admin-api,
                              #   golden-path-service (template)
```

The two top-level tiers — `platform/` and `workloads/` — map directly to two separate
ArgoCD sync trees with independent sync waves, producing a clean separation between
infrastructure concerns and business application concerns.

---

## 2. ArgoCD: Implementation Deep-Dive

### 2.1 App-of-Apps Hierarchy

The system uses a two-level **App-of-Apps** pattern. Bootstrap plants two seed
Applications during Day-0 (`bootstrap_argocd.py`, step `apply_root_app`):

```
argocd namespace
│
├── platform-root   (sync-wave: 0)  ← points at platform/argocd-apps/
│   Manages 14 child Applications (all infrastructure)
│
└── workloads-root  (sync-wave: 1)  ← points at workloads/argocd-apps/
    Manages workload Applications + ApplicationSet
```

**Why two roots instead of one?**  
Infrastructure must be 100 % healthy before business apps start syncing. Wave ordering
enforces this: `platform-root` (wave 0) is fully synced before ArgoCD evaluates
`workloads-root` (wave 1). Each root Application uses `automated.selfHeal: true`, so any
manual `kubectl edit` on a child manifest is reverted within seconds.

Both roots are seeded imperatively once (via `kubectl apply` in the bootstrap Python
orchestrator) and are never touched again — subsequent changes to either tier go through
git commits.

### 2.2 Sync Waves — Full Wave Map

ArgoCD applies manifests in ascending wave order within a sync operation. The system
implements 7 waves:

| Wave | What deploys |
|------|-------------|
| `0` | `cert-manager` (CRDs must exist before all Certificate resources), `platform-root` itself |
| `1` | `cluster-autoscaler` (infra), `cert-manager-config` (Certificate CRs), `workloads-root` |
| `2` | `traefik` (DaemonSet, hostNetwork — must be running before ArgoCD ingress is applied) |
| `3` | `metrics-server` (required for HPA signals), `monitoring` stack (Prometheus, Grafana, Loki…) |
| `4` | `argo-rollouts`, `aws-ebs-csi-driver`, `ecr-token-refresh`, `crossplane`, `descheduler` |
| `5` | `nextjs`, `start-admin`, `public-api`, `admin-api` (business apps); `crossplane-providers` |
| `6` | `crossplane-xrds` (XRDs depend on working providers from wave 5) |

The wave annotation is set at the `Application` level:
```yaml
annotations:
  argocd.argoproj.io/sync-wave: "3"
```

### 2.3 Multi-Source Applications (Traefik, Monitoring)

Two platform Applications use ArgoCD's **multi-source** spec to separate chart and
values:

```yaml
# platform/argocd-apps/traefik.yaml (condensed)
spec:
  sources:
    # Source 1 — values from this monorepo
    - repoURL: git@github.com:Nelson-Lamounier/cdk-monitoring.git
      targetRevision: develop
      ref: values           # ← anchors $values variable

    # Source 2 — Traefik chart from upstream Helm registry
    - repoURL: https://traefik.github.io/charts
      chart: traefik
      targetRevision: "36.*"
      helm:
        valueFiles:
          - $values/kubernetes-app/k8s-bootstrap/system/traefik/traefik-values.yaml
```

**Why this matters**: The values file lives in the same monorepo as the rest of the
code, so a single PR can bump both the application code and its infrastructure
configuration atomically. The chart itself is always pinned to `36.*` (SemVer minor
range), which automatically receives patch releases but protects against breaking major
changes.

### 2.4 ApplicationSet — Self-Service Workload Generator

```yaml
# workloads/argocd-apps (embedded in one file, condensed)
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: workload-generator
spec:
  generators:
    - git:
        repoURL: git@github.com:Nelson-Lamounier/cdk-monitoring.git
        revision: develop
        directories:
          - path: kubernetes-app/workloads/charts/*
          - path: kubernetes-app/workloads/charts/golden-path-service
            exclude: true
          - path: kubernetes-app/workloads/charts/nextjs
            exclude: true
          - path: kubernetes-app/workloads/charts/start-admin
            exclude: true
  template:
    metadata:
      name: "{{path.basename}}"
    spec:
      source:
        path: "{{path}}/chart"
        helm:
          valueFiles:
            - "../{{path.basename}}-values.yaml"
      destination:
        namespace: "{{path.basename}}"  # namespace = directory name
```

The **Git Directory Generator** scans `workloads/charts/*/` and creates one ArgoCD
Application per directory. Adding a new service to the cluster requires only:

1. Create `workloads/charts/my-service/chart/` (Helm chart)
2. Create `workloads/charts/my-service/my-service-values.yaml`
3. Commit and push to `develop`

ArgoCD detects the new directory and creates the Application automatically — no manual
ArgoCD configuration needed.

`nextjs` and `start-admin` are **excluded** from the ApplicationSet because they require
ArgoCD Image Updater annotations (ECR SHA tag tracking + git write-back) that the generic
template cannot inject. They have manually committed Application manifests in
`workloads/argocd-apps/`.

### 2.5 ArgoCD Image Updater — Automated ECR Tag Tracking

`nextjs`, `start-admin`, and `public-api` all use the **ArgoCD Image Updater** sidecar
for continuous delivery:

```yaml
# workloads/argocd-apps/nextjs.yaml (condensed)
annotations:
  argocd-image-updater.argoproj.io/image-list: >
    "nextjs=771826808455.dkr.ecr.eu-west-1.amazonaws.com/nextjs-frontend"
  argocd-image-updater.argoproj.io/nextjs.update-strategy: newest-build
  argocd-image-updater.argoproj.io/nextjs.allow-tags: >
    "regexp:^[0-9a-f]{7,40}(-r[0-9]+)?$"
  argocd-image-updater.argoproj.io/write-back-method: >
    "git:secret:argocd/repo-cdk-monitoring"
  argocd-image-updater.argoproj.io/git-branch: develop
```

The CI pipeline pushes a new image tagged with a Git SHA (e.g. `a3f72bc`). Image Updater
detects the new tag via ECR API polling, commits the new tag to
`.argocd-source-nextjs.yaml` in the `develop` branch, and ArgoCD's `selfHeal` loop picks
up the git change and triggers a new Rollout revision.

The `-rN` suffix (`^[0-9a-f]{7,40}(-r[0-9]+)?$`) prevents tag overwrites on pipeline
retries — a retry produces `a3f72bc-r2` which is unambiguously newer than `a3f72bc-r1`.

The `newest-build` strategy selects by build timestamp rather than semver, which is
correct for SHA-tagged images that have no semantic version ordering.

### 2.6 selfHeal vs. ignoreDifferences

`workloads-root` uses `ignoreDifferences` to prevent an ownership conflict:

```yaml
# k8s-bootstrap/system/argocd/workloads-root-app.yaml
ignoreDifferences:
  - group: argoproj.io
    kind: Application
    jsonPointers:
      - /spec/source/helm/parameters
```

During bootstrap, `inject_monitoring_helm_params` patches live Helm parameters (IP
allowlist CIDRs read from SSM) directly into running Applications via the ArgoCD API.
These parameters are not in Git. Without `ignoreDifferences`, `selfHeal` would overwrite
the patched values on every sync cycle, breaking the Traefik rate-limit middleware.

### 2.7 Sync Options Applied Consistently

All Applications share a standard set of sync options:

| Option | Purpose |
|---|---|
| `CreateNamespace=true` | ArgoCD creates the target namespace if absent |
| `PruneLast=true` | Resource deletion happens after creation — prevents ordering issues during upgrades |
| `ServerSideApply=true` | Uses Kubernetes Server-Side Apply (SSA) instead of client-side `kubectl apply`; required to avoid last-applied annotation conflicts with Helm |
| `ApplyOutOfSyncOnly=true` | Only applies resources that differ from desired state; reduces API server load on large syncs |

### 2.8 Retry with Exponential Back-off

Every Application includes:

```yaml
retry:
  limit: 3
  backoff:
    duration: 5s
    factor: 2
    maxDuration: 3m
```

This prevents a failing resource (e.g., a CRD not yet installed) from immediately
exhausting all retries. Back-off ensures transient issues (API server restart, etcd
compaction) resolve before ArgoCD gives up.

### 2.9 ArgoCD Bootstrap Sequence (`bootstrap_argocd.py`)

The Python orchestrator (`bootstrap_argocd.py`) is the Day-0 imperative layer that
brings ArgoCD to a state where it can take over declaratively. Key steps:

1. **create_namespace** → `kubectl apply -f namespace.yaml`
2. **resolve_deploy_key** → reads SSH private key from SSM SecureString
3. **create_repo_secret** → creates `argocd/repo-cdk-monitoring` K8s Secret (type:
   `repository`) so ArgoCD can clone the private monorepo
4. **preserve / restore ArgoCD JWT signing key** → backs up the ArgoCD internal signing
   key to SSM before applying the install manifest (avoids invalidating all active
   sessions on cluster rebuild)
5. **install_argocd** → `kubectl apply -f install.yaml` (vendored ArgoCD manifest)
6. **create_default_project** → required for ArgoCD v3.x where the default project is
   no longer auto-created
7. **configure_argocd_server** → patches the `argocd-cmd-params-cm` ConfigMap to set
   `rootpath=/argocd` (for Traefik sub-path routing) and `insecure=true` (TLS terminated
   by Traefik)
8. **configure_health_checks** → adds custom health check logic for Argo Rollout
   resources to the `argocd-cm` ConfigMap
9. **apply_root_app** → seeds `platform-root` and `workloads-root` — from this point
   ArgoCD takes over all further deployments
10. **inject_monitoring_helm_params** → patches IP allowlist CIDRs into live Applications
11. **seed_ecr_credentials** → creates the `ecr-token-refresh` Secret with initial valid
    token (CronJob hasn't fired yet)
12. **provision_crossplane_credentials** → creates `crossplane-aws-creds` K8s Secret
    from AWS Secrets Manager
13. **restore_tls_cert** → restores Let's Encrypt certificate from SSM (avoids rate-limit
    reissuance on cluster rebuild)
14. **wait_for_argocd** → polls `/healthz` until ArgoCD server responds
15. **apply_ingress** → creates Traefik `IngressRoute` for the ArgoCD UI (requires Traefik
    CRDs to be synced by ArgoCD first — non-fatal if Traefik isn't ready yet)
16. **create_ci_bot** / **generate_ci_token** → creates an ArgoCD service account for the
    CI pipeline and writes the token to AWS Secrets Manager

---

## 3. Helm: Chart Architecture

### 3.1 Chart Layout Pattern

Each workload chart follows an identical layout:

```
charts/<service>/
├── chart/
│   ├── Chart.yaml
│   ├── values.yaml           # base defaults (safe to commit)
│   ├── templates/
│   │   ├── _helpers.tpl      # named templates
│   │   ├── rollout.yaml      # Argo Rollout (or deployment.yaml for simpler services)
│   │   ├── service.yaml
│   │   ├── ingressroute.yaml # Traefik CRD
│   │   ├── hpa.yaml
│   │   ├── pdb.yaml
│   │   ├── network-policy.yaml
│   │   ├── resource-quota.yaml
│   │   └── analysis-template.yaml
└── <service>-values.yaml     # runtime overrides (image tag, resource sizing)
```

The split between `values.yaml` (committed defaults) and `<service>-values.yaml`
(deployment-time overrides) maps to the ArgoCD `valueFiles` list:

```yaml
source:
  helm:
    valueFiles:
      - ../nextjs-values.yaml  # <service>-values.yaml sits one level above chart/
```

### 3.2 Feature Flags via Values

Every optional Kubernetes resource is guarded by a feature flag:

```yaml
{{- if .Values.hpa.enabled }}
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
...
{{- end }}
```

This keeps a single chart usable across environments without forking. A staging environment
with no HPA need only set `hpa.enabled: false` in its values file.

Supported feature flags across charts:

| Flag | Resource guarded |
|---|---|
| `hpa.enabled` | HorizontalPodAutoscaler |
| `pdb.enabled` | PodDisruptionBudget |
| `networkPolicy.enabled` | NetworkPolicy |
| `ingress.enabled` | Traefik IngressRoute (intentionally false for nextjs — see §4.3) |
| `serviceMonitor.enabled` | Prometheus ServiceMonitor |
| `autoscaling.enabled` | HorizontalPodAutoscaler (golden-path-service) |
| `crossplane.bucket.enabled` | Crossplane `EncryptedBucket` claim |
| `crossplane.queue.enabled` | Crossplane `MonitoredQueue` claim |
| `image.repository` | All deployment resources (golden-path-service) |

### 3.3 Named Templates (`_helpers.tpl`)

Charts with multiple templates share label logic via named templates:

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

`selectorLabels` is used in `matchLabels` (immutable — must be stable across upgrades);
`fullLabels` is used in `metadata.labels` (can change freely). This separation is a Helm
best practice: changing a selector label requires deleting the resource because
`spec.selector` is immutable on Deployments and StatefulSets.

### 3.4 Golden-Path Service Template

`workloads/charts/golden-path-service/` is not deployed itself — it is excluded from
the ApplicationSet and exists purely as a **copy template** for new services.
It demonstrates all production defaults a new service should inherit:

- Three-probe health check model (startup + readiness + liveness)
- `preStop: sleep 5` lifecycle hook for graceful connection draining
- Crossplane XRD claims (`EncryptedBucket`, `MonitoredQueue`)
- NetworkPolicy with default-deny + Traefik allow
- ServiceMonitor for Prometheus scraping
- CPU-based HPA
- PodDisruptionBudget

A developer bootstrapping a new service copies this chart and fills in their
`image.repository`. The ApplicationSet picks up the new directory automatically.

---

## 4. Kubernetes Concepts Applied

### 4.1 Argo Rollouts — Blue/Green Progressive Delivery

`nextjs` and `start-admin` replace the standard `Deployment` kind with an Argo
`Rollout`:

```yaml
# workloads/charts/nextjs/chart/templates/rollout.yaml (condensed)
apiVersion: argoproj.io/v1alpha1
kind: Rollout
spec:
  strategy:
    blueGreen:
      activeService: nextjs          # receives production traffic
      previewService: nextjs-preview # receives zero traffic
      autoPromotionEnabled: false    # requires explicit CI promote step
      scaleDownDelaySeconds: 30
      prePromotionAnalysis:
        templates:
          - templateName: nextjs-bluegreen-analysis
```

**How blue/green works here**:

1. CI pipeline pushes a new image; Image Updater commits the new SHA to Git
2. ArgoCD detects the git change and creates a new Rollout revision
3. Argo Rollouts spins up the **preview** (`blue`) ReplicaSet alongside the live
   **active** (`green`) ReplicaSet — both run full replicas simultaneously
4. `prePromotionAnalysis` runs automatically against the preview ReplicaSet using
   Prometheus metrics (error rate + P95 latency). The `AnalysisTemplate` queries
   Traefik's service-level metrics because those are always available, even for a
   service with zero external traffic yet
5. If analysis passes, the CI pipeline calls `argocd app actions run nextjs promote`
6. Argo Rollouts flips the active/preview Services, then scales down the old ReplicaSet
   after 30 seconds

`autoPromotionEnabled: false` means no promotion happens without the explicit `promote`
call from CI, regardless of analysis result. This ensures every deployment has a human
gate in the pipeline.

### 4.2 AnalysisTemplate — Prometheus-Gated Promotions

```yaml
# workloads/charts/nextjs/chart/templates/analysis-template.yaml (condensed)
apiVersion: argoproj.io/v1alpha1
kind: AnalysisTemplate
metadata:
  name: nextjs-bluegreen-analysis
spec:
  metrics:
    - name: error-rate
      provider:
        prometheus:
          address: http://prometheus.monitoring.svc.cluster.local:9090/prometheus
          query: |
            scalar(
              sum(rate(traefik_service_requests_total{
                service=~"nextjs-nextjs-app-.*@kubernetes", code=~"5.."
              }[5m])) /
              sum(rate(traefik_service_requests_total{
                service=~"nextjs-nextjs-app-.*@kubernetes"
              }[5m]))
            )
      successCondition: "isNaN(result) || result < 0.05"

    - name: p95-latency
      provider:
        prometheus:
          query: |
            scalar(
              histogram_quantile(0.95,
                sum(rate(traefik_service_request_duration_seconds_bucket{
                  service=~"nextjs-nextjs-app-.*@kubernetes"
                }[5m])) by (le)
              ) * 1000
            )
      successCondition: "isNaN(result) || result < 2000"
```

**Notable implementation detail**: PromQL results are wrapped in `scalar()` to convert
a one-element vector into a scalar. Without this conversion, Argo Rollouts receives
a `[]float64` type it cannot evaluate against numeric conditions — a bug fixed
on 2026-03-18 as noted in the comment.

`isNaN(result)` handles the case where the preview service has received zero traffic
(division by zero produces NaN). This prevents a false-negative on Day-0.

Thresholds (from `values.yaml`): error rate `< 5 %`, P95 latency `< 2,000 ms`.

### 4.3 Traefik IngressRoute CRD — Ownership Boundary

```yaml
# workloads/charts/nextjs/chart/values.yaml
ingress:
  enabled: false  # ← intentionally false
```

The `IngressRoute` is **not managed by ArgoCD**. It is owned exclusively by `deploy.py`
(Step 5). The reason is runtime secret injection:

- The `IngressRoute` match rule contains the CloudFront origin secret:  
  `Host(...) && PathPrefix(/) && HeaderRegexp(X-CloudFront-Origin-Secret, <secret>)`
- This secret is read from SSM at deploy time and must not be committed to git
- During zero-downtime secret rotation, `deploy.py` uses a regex OR pattern:  
  `old_escaped|new_escaped` — valid for 20 minutes while CloudFront propagates
- If ArgoCD managed the IngressRoute, every 3-minute self-heal cycle would overwrite the
  runtime-injected secret with the placeholder `^PLACEHOLDER_NEVER_MATCHES$`, silently
  breaking routing for every user

The priority cascade between routes (from `deploy.py`):

```
priority 200  start-admin  PathPrefix(`/admin`)     — most specific
priority 100  nextjs-preview  PathPrefix(`/`) && Header(`X-Preview`, `true`)
priority  50  nextjs (production)   PathPrefix(`/`) — catch-all
```

### 4.4 HPA Targeting a Rollout

The HPA for `nextjs` targets the Argo `Rollout` resource, not a standard `Deployment`:

```yaml
spec:
  scaleTargetRef:
    apiVersion: argoproj.io/v1alpha1
    kind: Rollout      # ← not apps/v1 Deployment
    name: nextjs
  minReplicas: 2
  maxReplicas: 5
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
```

This requires `metrics-server` (wave 3) to be healthy before the HPA can report `cpu`
utilisation — enforced by the sync wave ordering.

### 4.5 PodDisruptionBudget

All production workloads include a PDB:

```yaml
spec:
  minAvailable: 1
```

The PDB ensures at least one pod remains running during **voluntary disruptions**:
- Node drain before Spot instance termination
- `kubectl drain` during maintenance
- Cluster Autoscaler scale-down eviction

Without a PDB, a node drain could evict all pods simultaneously — causing a complete
service outage. The Spot-heavy cluster makes this particularly important.

### 4.6 TopologySpreadConstraints

`nextjs` uses `TopologySpreadConstraints` to spread the 2-replica blue/green deployment
across nodes:

```yaml
topologySpreadConstraints:
  - maxSkew: 1
    topologyKey: kubernetes.io/hostname
    whenUnsatisfiable: ScheduleAnyway  # ← not DoNotSchedule
    labelSelector:
      matchLabels:
        app: nextjs
```

`ScheduleAnyway` is used instead of `DoNotSchedule` because on a 2-node cluster
`DoNotSchedule` blocks pod creation when `maxSkew` is already violated (e.g., during
a rolling update when both active and preview pods are on the same node). `ScheduleAnyway`
allows the scheduler to place the pod immediately; the Descheduler (`platform/argocd-apps/descheduler.yaml`) rebalances asynchronously via eviction once a new node is available.

### 4.7 NetworkPolicy — Calico Enforcement

Every chart includes a `NetworkPolicy` implementing **default-deny with targeted ingress**:

```yaml
# workloads/charts/nextjs/chart/templates/network-policy.yaml (condensed)
spec:
  policyTypes:
    - Ingress
  ingress:
    # Traefik pods in kube-system
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
      ports:
        - port: 3000

    # Traefik hostNetwork pods (appear as node IPs, not namespace-matched)
    - from:
        - ipBlock:
            cidr: 10.0.0.0/16   # VPC node CIDR
      ports:
        - port: 3000

    # Cross-node VXLAN tunnel traffic (Calico pod CIDR)
    - from:
        - ipBlock:
            cidr: 192.168.0.0/16
      ports:
        - port: 3000

    # Prometheus scraping from monitoring namespace
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: monitoring
      ports:
        - port: 3000
```

The dual `ipBlock` rules for node CIDR + pod CIDR are a direct consequence of Traefik
running with `hostNetwork: true`. A pod-running-as-hostNetwork appears to other pods
as the node's IP rather than its pod IP, so `namespaceSelector` alone cannot match it
in Calico's NetworkPolicy evaluation.

### 4.8 ResourceQuota — Namespace-Level Resource Caps

The `nextjs` namespace has explicit resource caps sized for the blue/green double-replica
period:

```yaml
# values.yaml
resourceQuota:
  hard:
    requests.cpu: "300m"    # 2 × 25m × 2 (blue+green) × 1.5 safety
    requests.memory: 1536Mi
    limits.cpu: "3"
    limits.memory: 3Gi
    persistentvolumeclaims: "2"
```

The formula `(replicas × 2 × per-pod limit) × 1.5` explicitly accounts for both
blue and green ReplicaSets running simultaneously — a constraint unique to blue/green
vs. rolling update strategies.

### 4.9 Node Selectors and Taints/Tolerations

All workloads explicitly declare node placement:

```yaml
# nextjs — stays on general pool
nodeSelector:
  node-pool: general

# cluster-autoscaler — must NOT run on the pool it manages
nodeSelector:
  node-pool: monitoring
tolerations:
  - key: dedicated
    value: monitoring
    operator: Equal
    effect: NoSchedule

# opencost, crossplane — monitoring pool placement + toleration
nodeSelector:
  node-pool: monitoring
tolerations:
  - key: dedicated
    value: monitoring
    effect: NoSchedule
```

The monitoring pool carries a `dedicated=monitoring:NoSchedule` taint applied by the
bootstrap script at node join time. Without the matching toleration, no pod would
schedule on monitoring nodes — providing guaranteed resource isolation for Prometheus,
Grafana, and Loki from the general-purpose workload pool.

`cluster-autoscaler` is placed on the monitoring pool specifically to avoid the
self-defeating scenario where CA evicts its own pod while issuing a scale-down on the
general pool it manages.

### 4.10 Security Context

`nextjs` and `start-admin` enforce non-root execution:

```yaml
podSecurityContext:
  runAsNonRoot: true
  runAsUser: 1001
  fsGroup: 1001

containerSecurityContext:
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: false  # Next.js ISR writes to /app/.next/server at runtime
```

`readOnlyRootFilesystem: false` is a deliberate trade-off: Next.js ISR (Incremental Static
Regeneration) writes rendered pages to disk at runtime. Setting it `true` would require
mounting an `emptyDir` at every path Next.js writes to — a maintenance burden. The
`emptyDir` mounts at `/app/.next/cache` and `/tmp` are present, but the root filesystem
remains writable.

### 4.11 Secrets vs. ConfigMap Boundary

`deploy.py` enforces an explicit classification of every environment variable:

```python
_NEXTJS_SECRET_KEYS = [
    "NEXTAUTH_SECRET", "NEXTAUTH_URL",
    "AUTH_COGNITO_USER_POOL_ID", "AUTH_COGNITO_ID",
    "BEDROCK_AGENT_API_KEY", "REVALIDATION_SECRET",
    "NEXT_PUBLIC_API_URL",
]

_NEXTJS_CONFIG_KEYS = [
    "DYNAMODB_TABLE_NAME", "DYNAMODB_GSI1_NAME",
    "ASSETS_BUCKET_NAME", "BEDROCK_AGENT_API_URL",
    "PUBLISH_LAMBDA_ARN", "AWS_DEFAULT_REGION",
]
```

Sensitive values go into an `Opaque` Kubernetes Secret (`nextjs-secrets`). Non-sensitive
infrastructure references — table names, bucket names, region — go into a `ConfigMap`
(`nextjs-config`). The Rollout template mounts both via `envFrom`, so the container sees
a flat environment regardless of backing object.

AWS credentials are **not present in either object**. They are resolved by the AWS SDK's
default credential chain via the EC2 Instance Profile (IMDS), which makes the pods
credentials-free at rest.

---

## 5. Crossplane — Kubernetes-Native Infrastructure Abstraction

### 5.1 Architecture

Crossplane introduces a **Kubernetes-native control plane for AWS resource
management** alongside CDK. It provides:

- `Provider` CRDs (installed wave 5 by `crossplane-providers.yaml`)
- `Composite Resource Definitions` (XRDs) defining golden-path abstractions  
  (installed wave 6 by `crossplane-xrds.yaml`)
- Workloads claim resources by submitting a `Claim` of the XRD type

### 5.2 XRD Claims from the Golden-Path Chart

```yaml
# workloads/charts/golden-path-service/chart/templates/encrypted-bucket-claim.yaml
apiVersion: platform.nelsonlamounier.com/v1alpha1
kind: EncryptedBucket
metadata:
  name: {{ .Values.crossplane.bucket.bucketName }}
spec:
  parameters:
    bucketName: {{ .Values.crossplane.bucket.bucketName | quote }}
    retentionDays: {{ .Values.crossplane.bucket.retentionDays }}
    environment: {{ .Values.crossplane.bucket.environment | quote }}
```

The `EncryptedBucket` kind is a Crossplane `XRD Claim` — a simplified API that a
developer uses. Behind the claim, the XRD `Composition` expands it into the actual
Crossplane `Bucket` managed resource (which maps 1:1 to an AWS S3 bucket).

**What the developer gets automatically without knowing AWS**:
- SSE-S3 encryption (AES256)
- Versioning enabled
- Public access block (all four settings)
- Lifecycle rule (`retentionDays`)
- Standard tagging schema

This is the **Internal Developer Platform (IDP)** pattern: platform engineers define safe
defaults in the Composition; developers consume the simplified XRD without needing IAM,
policy, or S3 configuration knowledge.

### 5.3 Credentials Model

Crossplane credentials are seeded imperatively by `bootstrap_argocd.py`:
```
provision_crossplane_credentials: reads from AWS Secrets Manager → creates K8s Secret
  crossplane-aws-creds in crossplane-system namespace
```

The `ProviderConfig` references this Secret. Crossplane providers then use the long-lived
IAM credentials to call AWS APIs. This is separate from the worker node Instance Profile
used by application pods.

---

## 6. Platform Services: Kubernetes Primitives Applied

### 6.1 cert-manager — TLS via Kubernetes CRDs

cert-manager replaces Traefik's built-in ACME resolver. The motivation (documented in
`cert-manager.yaml`) was the DaemonSet + hostPath persistence problem:

- Traefik's ACME stores certificates in a node-local file (`/data/acme.json`)
- On a 3-node DaemonSet with `hostNetwork: true`, each Traefik pod has its own local
  copy — they are not shared across nodes
- When the control-plane node is rebuilt, its Traefik pod loses the cert and reissues
  — consuming Let's Encrypt rate limit quota

cert-manager stores certificates in etcd-backed Kubernetes `Secrets`, accessible
from all nodes. The `ClusterIssuer` is injected by `bootstrap_argocd.py` with SSM-read
values (Route 53 hosted zone ID, cross-account DNS role ARN) rather than managed by
ArgoCD, preventing ArgoCD from overwriting runtime-resolved values.

`bootstrap_argocd.py` also **restores the TLS certificate from SSM** on cluster rebuild
(step `restore_tls_cert`). This means a fresh cluster inherits the previously issued
certificate immediately — no rate-limit wait, no downtime.

### 6.2 ECR Token Refresh — CronJob

ECR tokens expire every 12 hours. The `ecr-token-refresh` chart deploys a `CronJob`
that refreshes the `imagePullSecrets` automatically:

```yaml
# platform/argocd-apps/ecr-token-refresh.yaml — points at platform/charts/ecr-token-refresh/
```

On bootstrap Day-0, `seed_ecr_credentials` pre-seeds a valid token before the CronJob
has fired — preventing an `ErrImagePull` on first pod scheduling.

### 6.3 Cluster Autoscaler — Kubernetes-Native ASG Control

```yaml
# platform/argocd-apps/cluster-autoscaler.yaml (condensed from values)
autoDiscovery:
  clusterName: k8s-development  # matches k8s/cluster-api tag on ASG
awsRegion: eu-west-1
extraArgs:
  scale-down-delay-after-add: 5m
  scale-down-unneeded-time: 5m
  scale-down-utilization-threshold: "0.5"
  skip-nodes-with-system-pods: "false"
  expander: least-waste
```

CA uses AWS auto-discovery via the `k8s.io/cluster-autoscaler/k8s-development: owned`
tag on the ASG. It calls the AWS Autoscaling API to adjust `desiredCapacity` — the same
ASG managed by the CDK `worker-asg-stack.ts`. CA only touches the `general` pool
(`min=2/max=4`); the monitoring pool is static.

`skip-nodes-with-system-pods: false` prevents the control-plane's DaemonSet pods
from blocking scale-down of general worker nodes.

### 6.4 Descheduler — Async Rebalancing

The `descheduler` (wave 4) provides **reactive pod rebalancing**. When the Cluster
Autoscaler adds a new node to the general pool, existing pods may be unbalanced across
nodes (violating `TopologySpreadConstraints`). The Descheduler runs on a schedule and
evicts violating pods, allowing the scheduler to re-place them across nodes. This is the
asynchronous complement to `whenUnsatisfiable: ScheduleAnyway` in the topology spread
constraints.

### 6.5 Metrics Server — HPA Dependency

```yaml
# platform/argocd-apps/metrics-server.yaml (condensed)
args:
  - --kubelet-insecure-tls  # kubeadm uses self-signed kubelet certs
```

`metrics-server` aggregates CPU/memory usage from the kubelet `/metrics/resource`
endpoint. Without it, `kubectl top` returns an error and all HPAs remain at `<unknown>`
utilization — preventing any scale-up regardless of actual load.

`--kubelet-insecure-tls` is required because `kubeadm` generates self-signed kubelet
certificates. In a managed cluster (EKS, GKE), this flag would not be needed.

---

## 7. Ownership Boundaries Summary

This table clarifies which layer owns each resource type — a recurring question in any
GitOps system:

| Resource | Owner | Why |
|---|---|---|
| Argo `Rollout`, `Service`, `HPA`, `PDB`, `NetworkPolicy`, `ResourceQuota` | **ArgoCD (Helm)** | Fully declarative, no runtime secrets |
| Traefik `IngressRoute` (nextjs, nextjs-preview) | **deploy.py** | Contains SSM-sourced CloudFront origin secret |
| Traefik `IngressRoute` (ArgoCD UI) | **bootstrap_argocd.py** | Seeded once; Traefik CRDs may not exist at ArgoCD install time |
| Kubernetes `Secret` (nextjs-secrets, start-admin-secrets) | **deploy.py** | SSM-sourced values; committing to git is a security violation |
| Kubernetes `ConfigMap` (nextjs-config) | **deploy.py** | SSM-sourced; updated at every deploy |
| ArgoCD `repo-cdk-monitoring` Secret | **bootstrap_argocd.py** | SSH deploy key from SSM; seeded once |
| cert-manager `ClusterIssuer` | **bootstrap_argocd.py** | Route 53 zone ID and cross-account role ARN from SSM |
| cert-manager `Certificate` | **ArgoCD** (`cert-manager-config` Application) | Fully declarative |
| Crossplane `ProviderConfig` / credentials Secret | **bootstrap_argocd.py** | IAM credentials from Secrets Manager |
| Crossplane XRD `Claims` (EncryptedBucket, MonitoredQueue) | **ArgoCD (Helm)** | Golden-path template rendered by Helm |
| Image tag in `.argocd-source-*.yaml` | **ArgoCD Image Updater** | ECR polling → git write-back |

---

## 8. Key Kubernetes Concepts Reference Table

| Concept | Where applied | File(s) |
|---|---|---|
| GitOps / App-of-Apps | Platform + workloads two-tier hierarchy | `platform-root-app.yaml`, `workloads-root-app.yaml` |
| ApplicationSet (Git Directory) | Self-service workload registration | embedded in workloads argocd-apps |
| Multi-source Application | Traefik, monitoring (chart + values separated) | `traefik.yaml`, `monitoring.yaml` |
| Sync Waves | 7-wave deployment ordering | All Application manifests |
| Argo Rollout (blue/green) | `nextjs`, `start-admin` progressive delivery | `rollout.yaml` |
| AnalysisTemplate (Prometheus) | Pre-promotion error rate + P95 gate | `analysis-template.yaml` |
| ArgoCD Image Updater | ECR SHA tag → git write-back | Application annotations |
| Horizontal Pod Autoscaler | CPU-based scaling for nextjs | `hpa.yaml` |
| PodDisruptionBudget | Availability during Spot evictions | `pdb.yaml` |
| TopologySpreadConstraints | Cross-node pod spread | `rollout.yaml`, `values.yaml` |
| NetworkPolicy | Default-deny + Traefik/Prometheus allow | `network-policy.yaml` |
| ResourceQuota | Namespace-level resource caps | `resource-quota.yaml` |
| Node Selector | Pool affinity (general / monitoring) | All chart `values.yaml` |
| Taints + Tolerations | Monitoring pool isolation | All monitoring-pool Application values |
| Crossplane XRD (golden-path) | AWS resource abstraction for developers | `encrypted-bucket-claim.yaml`, `crossplane-xrds` |
| cert-manager CRDs | Kubernetes-native TLS (replaces Traefik ACME) | `cert-manager.yaml`, `cert-manager-config.yaml` |
| CronJob (ECR token) | ECR pull secret refresh | `ecr-token-refresh` chart |
| Cluster Autoscaler | Kubernetes-controlled ASG scaling | `cluster-autoscaler.yaml` |
| Descheduler | Async pod rebalancing after scale-up | `descheduler.yaml` |
| metrics-server | HPA resource metric source | `metrics-server.yaml` |
| ServerSideApply | Conflict-free multi-owner field management | All syncOptions |
| ignoreDifferences | Protect runtime-patched Helm parameters | `workloads-root-app.yaml` |
| Secret vs. ConfigMap boundary | Sensitive vs. non-sensitive env vars | `deploy.py` |
| IRSA-equivalent (Instance Profile) | AWS credential chain, no static keys | `deploy.py`, `values.yaml` |
