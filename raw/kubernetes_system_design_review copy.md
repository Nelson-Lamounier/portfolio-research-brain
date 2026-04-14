# Kubernetes Self-Healing System — System Design Review

> **Source grounding:** Every claim in this document is derived from the
> actual codebase read during this session:
> `infra/lib/stacks/kubernetes/worker-asg-stack.ts`,
> `kubernetes-app/k8s-bootstrap/boot/steps/control_plane.py`,
> `kubernetes-app/k8s-bootstrap/boot/steps/worker.py`,
> `kubernetes-app/k8s-bootstrap/system/argocd/bootstrap_argocd.py`,
> `kubernetes-app/k8s-bootstrap/system/traefik/traefik-values.yaml`,
> `api/public-api/src/`, and `api/admin-api/src/`.

---

## 1. Cluster Topology — 3 Nodes

The cluster is composed of **3 nodes**: one static control-plane EC2 instance
and **two ASG-backed worker pools** defined by the single generic
`KubernetesWorkerAsgStack` CDK stack (`worker-asg-stack.ts`).

### Node Pools — Source: `worker-asg-stack.ts`

The old pattern of three named worker stacks (`AppWorker`, `MonitoringWorker`,
`ArgocdWorker`) was **replaced** by a single parameterised stack driven by
`WorkerPoolType`:

```
type WorkerPoolType = 'general' | 'monitoring'
```

| Pool | Instance Type | Spot | Min | Max | Taint | Hosts |
|---|---|---|---|---|---|---|
| `general` | `t3.small` | ✓ | 1 | 4 | None (accepts all pods) | Next.js, start-admin, ArgoCD, system components |
| `monitoring` | `t3.medium` | ✓ | 1 | 2 | `dedicated=monitoring:NoSchedule` (applied by bootstrap) | Prometheus, Grafana, Loki, Tempo, Alloy, Cluster Autoscaler |

> **Design decision — no taint on general pool:** The `general` pool has no
> taint so that unschedulable system pods (e.g. Calico, EBS CSI, cert-manager)
> always have a home. Only the monitoring stack is tainted to prevent
> workload pods from consuming observability node capacity.

### Node Labels (applied by `worker.py` via `kubelet --node-labels`)

- `node-pool=general` (general pool)
- `node-pool=monitoring` (monitoring pool)

### Cluster Autoscaler Integration

Both ASGs are tagged at CDK synth time:

```
k8s.io/cluster-autoscaler/enabled = true
k8s.io/cluster-autoscaler/<clusterName> = owned
```

CA scale-write permissions (`SetDesiredCapacity`, `TerminateInstanceInAutoScalingGroup`)
are **conditional** — granted only to the monitoring pool role. This prevents a
compromised general-pool node from manipulating ASG capacity. The CA pod itself
runs on the monitoring pool with a matching `nodeSelector`.

---

## 2. Infrastructure Bootstrapped from SSM (No Cross-Stack Exports)

All inter-stack dependencies are resolved at runtime via SSM rather than
CloudFormation `Fn::ImportValue`. The worker stack reads at synth time:

| SSM Parameter | Used For |
|---|---|
| `{prefix}/security-group-id` | Cluster SG |
| `{prefix}/ingress-sg-id` | Traefik ingress SG |
| `{prefix}/monitoring-sg-id` | Monitoring SG (monitoring pool only) |
| `{prefix}/kms-key-arn` | Log group encryption |
| `{prefix}/scripts-bucket` | S3 boot script source |
| `{prefix}/join-token` | `kubeadm join` token (SecureString) |
| `{prefix}/ca-hash` | `kubeadm join` CA hash |
| `{prefix}/control-plane-endpoint` | API server hostname:port |
| `{prefix}/nlb-http-target-group-arn` | NLB HTTP TG |
| `{prefix}/nlb-https-target-group-arn` | NLB HTTPS TG |
| `{prefix}/golden-ami/latest` | Golden AMI ID |

**Both pools register with both NLB target groups**, ensuring failover is available
regardless of which node the EIP resolves to (see §4 networking).

---

## 3. Bootstrap Pipeline — `k8s-bootstrap`

The bootstrap pipeline is a Python package (`k8s-bootstrap/boot/steps/`) with
two entry points and step-based orchestration using a `StepRunner` context
manager that provides structured logging, timing, and idempotency guards
via marker files.

### 3.1 Control Plane Bootstrap — `control_plane.py`

Steps executed in order on the control-plane node:

| Step | Function | Purpose |
|---|---|---|
| 1 | `step_validate_ami` | Verify Golden AMI binaries present |
| 2 | `restore_backup` | Restore etcd + certs from S3 if EBS empty (DR path) |
| 3 | `init_kubeadm` / `_handle_second_run` | `kubeadm init` (first boot) or reconstruct from PKI (DR) |
| 4 | `install_calico` | Calico CNI via Tigera operator |
| 4b | `install_ccm` | AWS Cloud Controller Manager (`uninitialized` taint removal) |
| 5 | `configure_kubectl` | kubeconfig for root, ec2-user, ssm-user |
| 6 | `sync_manifests` | Download bootstrap manifests from S3 |
| 7 | `bootstrap_argocd` | Install ArgoCD + App-of-Apps (runs `bootstrap_argocd.py`) |
| 8 | `verify_cluster` | Post-boot health checks |
| 9 | `install_cw_agent` | CloudWatch Agent for log streaming |
| 10 | `install_etcd_backup` | Hourly etcd backup timer |

**DR path (second-run):** When `admin.conf` already exists (ASG replacement),
the script detects whether the API server is responding. If manifests are missing
(`kube-apiserver.yaml` absent), it calls `_reconstruct_control_plane()`, which:

1. Starts `containerd`
2. Configures ECR credential provider for `kubelet`
3. Writes new `kubelet --node-ip` for current instance
4. Updates Route 53 A record (`k8s-api.k8s.internal`)
5. Regenerates kubeconfigs (`kubeadm init phase kubeconfig all`)
6. Regenerates API server cert SANs with new instance IPs (critical — old cert
   references old private/public IPs; kubelet TLS verification fails without this)
7. Generates static pod manifests (`kubeadm init phase control-plane all`)
8. Generates etcd static pod manifest
9. Restarts `kubelet`
10. Waits up to 180s for `/healthz` to return `ok`

**Bootstrap token repair (DR):** On DR restore, `kubeadm init` is skipped, so
`cluster-info` ConfigMap, RBAC bindings, `kube-proxy` DaemonSet, and CoreDNS
Deployment are missing. The script explicitly repairs these with idempotent
`kubeadm init phase` subcommands.

### 3.2 Worker Bootstrap — `worker.py`

| Step | Function | Purpose |
|---|---|---|
| 1 | `step_validate_ami` | Golden AMI binary validation |
| 2 | `step_join_cluster` | `kubeadm join` with SSM-discovered credentials |
| 3 | `step_install_cloudwatch_agent` | Log streaming |
| 4 | `step_clean_stale_pvs` | Monitoring-pool only: remove PVs pinned to dead nodes |
| 5 | `verify_membership` | Confirm node registration and correct labels |

**CA mismatch detection:** Before the join idempotency guard, `worker.py`
compares the local CA cert hash against `{prefix}/ca-hash` in SSM. If they
differ (control-plane was replaced with a new CA), it runs `kubeadm reset -f`
and removes `kubelet.conf` so the join step can proceed with new credentials.

**API reachability gate:** Before burning the `kubeadm join` retry budget,
`worker.py` holds a TCP socket probe loop (Python `socket.create_connection`)
polling `{endpoint}:6443` every 10s with a 300s timeout. This prevents
cascading failures during control-plane initialisation.

**Stale PV cleanup (monitoring pool only):** On monitoring node replacement,
`local-path` PVs retain `nodeAffinity` to the dead hostname. The cleanup step
reads all PVs, filters those in the `monitoring` namespace with affinity to
nodes no longer in the cluster, and deletes both the PVC and PV. ArgoCD/Helm
recreates them on the next sync.

### 3.3 ArgoCD Bootstrap — `bootstrap_argocd.py`

Run as step 7 of the control-plane bootstrap, this Python orchestrator handles
a 41-step ArgoCD installation sequence via a `BootstrapLogger` (JSON event
logging to SSM). Key steps:

| Phase | Steps |
|---|---|
| Namespace & credentials | Create `argocd` namespace, resolve SSH deploy key from SSM, create repo secret |
| ArgoCD JWT key continuity | Preserve JWT signing key before install → restore after (prevents session invalidation on cluster rebuild) |
| Installation | `kubectl apply` ArgoCD install manifest |
| App-of-Apps | Apply `platform-root-app.yaml` and `workloads-root-app.yaml` |
| Monitoring injection | Inject SNS topic ARN and Prometheus credentials into Helm params |
| ECR seeding | Day-1 ECR credential seed (before the ECR refresh CronJob fires) |
| TLS | Restore TLS cert from SSM; apply cert-manager `ClusterIssuer` |
| Networking | Wait for ArgoCD; apply Traefik `IngressRoute`; create IP allowlist middleware |
| Auth hardening | Set admin password from SSM; generate CI bot token → Secrets Manager |
| DR backup | Backup TLS cert and ArgoCD JWT key to SSM |

Non-fatal steps (CRD timing): `apply_cert_manager_issuer` and `apply_ingress`
are wrapped in `try/except` because Traefik and cert-manager CRDs may not be
ready during first bootstrap (ArgoCD is still syncing). These are retried by
`SM-B` (`deploy.py`) idempotently.

---

## 4. Networking Stack

### 4.1 End-to-End Request Path

```
Browser / API Client
    │
    ▼
Route 53 → nelsonlamounier.com (A record → CloudFront distribution)
    │
    ▼
CloudFront (WAF + Edge Cache)
    │  TLS terminated at CloudFront edge (AWS-managed ACM cert)
    │  Origin: NLB DNS name over HTTPS (port 443)
    │  Cache: s-maxage TTL from Cache-Control headers on responses
    │
    ▼
Network Load Balancer (TCP passthrough: 80→80, 443→443)
    │  Both ASG pools register to BOTH NLB TGs
    │  Health check: TCP :443 on every registered node
    │
    ▼
Traefik DaemonSet (hostNetwork, port 443 bound directly on node eth0)
    │  TLS: cert-manager-issued cert stored as Secret `ops-tls-cert`
    │  Routes by HTTP Host + Path headers
    │
    ▼
Pod (ClusterIP Service → Kubernetes networking via Calico overlay)
```

### 4.2 TLS Boundary Design

| Segment | TLS Owner | Certificate |
|---|---|---|
| Browser → CloudFront | CloudFront / ACM | `*.nelsonlamounier.com` managed by ACM |
| CloudFront → NLB | CloudFront (origin request) | NLB presents Traefik cert (`ops-tls-cert`) |
| NLB → Traefik | Traefik | cert-manager DNS-01 via cross-account Route 53 |
| Traefik → Pod | Unencrypted (in-cluster, Calico overlay) | N/A |

> **Key design decision:** `nelsonlamounier.com` public TLS is **CloudFront's
> responsibility** (ACM wildcard). Traefik's cert-manager cert (`ops-tls-cert`)
> is used for the CloudFront → NLB → Traefik leg only. The monitoring services
> (`grafana.`, `prometheus.`) are served directly via Traefik IngressRoute on
> `nelsonlamounier.com` subpaths or subdomains without CloudFront, meaning
> **Traefik's cert is what end-users see for monitoring**.

### 4.3 Traefik — DaemonSet `hostNetwork` Design

Source: `k8s-bootstrap/system/traefik/traefik-values.yaml`

```yaml
deployment:
  kind: DaemonSet
  dnsPolicy: ClusterFirstWithHostNet   # resolves K8s service DNS in host net mode

hostNetwork: true                      # binds ports 80/443 directly on node ethernet

tolerations:
  - key: node-role.kubernetes.io/control-plane   # runs on ALL nodes
  - key: dedicated
    value: monitoring                  # runs on monitoring pool too
    effect: NoSchedule

service:
  enabled: false                       # no Kubernetes Service; EIP is the VIP

updateStrategy:
  type: RollingUpdate
  rollingUpdate:
    maxUnavailable: 1
    maxSurge: 0                        # two pods cannot share the same host port
```

**Why DaemonSet + `hostNetwork`:** When the NLB target group registers all
nodes, any node could receive traffic when the EIP moves. If Traefik were
a Deployment with `replicas: 1`, the pod might be on a node that isn't the
current NLB target. DaemonSet guarantees Traefik is running and listening on
ports 80/443 on **every** node — the NLB health checks eliminate unhealthy
nodes from rotation automatically.

**Metrics and tracing:** Traefik exposes Prometheus metrics on port 9100
(`/metrics`) and ships OTLP traces to `tempo.monitoring.svc.cluster.local:4317`
over gRPC.

**PodDisruptionBudget disabled:** The Kubernetes PDB controller does not count
DaemonSet-owned pods correctly — ArgoCD v3's PDB health check marks DaemonSet
PDBs as Degraded whenever `disruptionsAllowed == 0`. Deliberately disabled;
rolling updates are controlled by `maxUnavailable: 1`.

---

## 5. In-Cluster API Services

The system hosts **two Hono/Node.js API services** as Kubernetes pods, both
using AWS SDK v3 credentials from the EC2 Instance Profile (IMDS) — no secrets
in pod environment variables.

### 5.1 `public-api` — Port 3001

**Framework:** Hono on `@hono/node-server`  
**Authentication:** None (public, read-only)

| Route | Method | Data Source | Cache-Control |
|---|---|---|---|
| `GET /healthz` | GET | — | — |
| `GET /api/articles` | GET | DynamoDB GSI1 (`gsi1-status-date`), `STATUS#published` | `s-maxage=300, stale-while-revalidate=60` |
| `GET /api/articles/:slug` | GET | DynamoDB `GetItem` (`ARTICLE#<slug>`, `METADATA`) | `s-maxage=300, stale-while-revalidate=60` |
| `GET /api/tags` | GET | DynamoDB scan | `s-maxage=300` |
| `GET /api/resumes/active` | GET | DynamoDB scan (Strategist table) — graceful 204 if unconfigured | `s-maxage=300, stale-while-revalidate=600` |

**CORS:** Allowed origins `https://nelsonlamounier.com` and `http://localhost:3000`.
Methods restricted to `GET, HEAD, OPTIONS`.

**Credential chain:** AWS SDK v3 resolves credentials via IMDS on the general
pool node. The `AWS_DEFAULT_REGION` env var is injected from the `nextjs-config`
ConfigMap.

**CloudFront caching:** The `s-maxage` `Cache-Control` headers instruct CloudFront
to cache article listings at the edge for 5 minutes, reducing DynamoDB reads
on the high-traffic public listing.

### 5.2 `admin-api` — Port 3002

**Framework:** Hono on `@hono/node-server`  
**Authentication:** Cognito JWT middleware — all `/api/admin/*` routes protected

```
/healthz               → unauthenticated (Kubernetes probes cannot send JWTs)
/api/admin/*           → jwtMiddleware (Cognito User Pool, RS256)
```

| Route | Method | Backend |
|---|---|---|
| `GET /api/admin/articles` | GET | DynamoDB GSI1 fan-out across `all\|draft\|review\|published\|rejected` |
| `GET /api/admin/articles/:slug` | GET | DynamoDB `GetItem` |
| `PUT /api/admin/articles/:slug` | PUT | DynamoDB `UpdateCommand`, syncs `gsi1pk` on status change |
| `DELETE /api/admin/articles/:slug` | DELETE | Parallel cascade delete: `METADATA` + `CONTENT#<slug>` |
| `POST /api/admin/articles/:slug/publish` | POST | Lambda `InvokeCommand` (async `Event`) → Bedrock pipeline |
| `GET /api/admin/applications` | GET | DynamoDB |
| `GET/POST/PUT/DELETE /api/admin/resumes` | CRUD | DynamoDB |
| `GET /api/admin/assets` | GET | S3 |
| `GET /api/admin/comments` | GET | DynamoDB |
| `GET /api/admin/content` | GET/DELETE | DynamoDB + S3 |
| `GET /api/admin/finops/realtime` | GET | CloudWatch (`BedrockMultiAgent` namespace) |
| `GET /api/admin/finops/costs` | GET | Cost Explorer (`us-east-1`, always) |
| `GET /api/admin/finops/chatbot` | GET | CloudWatch (`BedrockChatbot` namespace) |
| `GET /api/admin/finops/self-healing` | GET | CloudWatch (`self-healing-development/SelfHealing`) |
| `GET /api/admin/pipelines` | GET | DynamoDB / Step Functions |

**BFF pattern:** After the BFF migration, all API calls from `start-admin`
originate from **server-side functions (pod-to-pod)**. The browser never
sends cross-origin requests to `admin-api` directly. CORS config is retained as
defence-in-depth for any future client-side fetch.

**CORS:** Allowed origin `https://nelsonlamounier.com` (the admin sub-path
`/admin/*` CloudFront routes to the `start-admin` pod; the browser origin is
always the main domain, never a subdomain).

**Credential chain (admin-api):**
- `admin-api-secrets` → Cognito IDs only
- `admin-api-config` ConfigMap → DynamoDB tables, bucket, Lambda ARNs, region
- IMDS → AWS SDK credentials (DynamoDB, S3, Lambda, CloudWatch, Cost Explorer)

**Publish flow (article pipeline trigger):** `POST /api/admin/articles/:slug/publish`
invokes the Bedrock publish Lambda with `InvocationType: 'Event'` (fire-and-forget
async). The Lambda carries slug, triggering user (from JWT `sub`), and timestamp.

---

## 6. GitOps — ArgoCD App-of-Apps

The `bootstrap_argocd.py` applies two root apps:

- `platform-root-app.yaml` — platform components (Traefik, cert-manager,
  monitoring stack, Descheduler, Calico PDBs, priority classes)
- `workloads-root-app.yaml` — application workloads (Next.js, start-admin,
  public-api, admin-api)

ArgoCD sync waves enforce dependency ordering (infrastructure before workloads).
The monitoring stack ArgoCD app uses `ignoreDifferences` for bootstrap-injected
secrets (SNS topic ARN, Prometheus credentials) to prevent ArgoCD from
reverting runtime values.

**Image Updater:** ECR image tags are monitored by ArgoCD Image Updater.
The `-rN` retry suffix in the tag format is an ArgoCD Image Updater convention
used to force a re-tag event when the underlying image digest changes without
a version bump.

---

## 7. Progressive Delivery — Argo Rollouts Blue/Green

The Next.js application uses an Argo Rollouts `Rollout` CR (Blue/Green strategy):

- **Promotion:** Manual gate — human approval required in ArgoCD UI or `kubectl argo rollouts promote`
- **Pre-promotion analysis:** Prometheus `AnalysisTemplate` gates promotion on
  error rate metrics
- **Scale-down delay:** 30s before the old (blue) pods are terminated
- **N-1 static asset retention:** The previous version's static assets are
  retained in S3 for 30s post-scale-down to serve in-flight requests that still
  reference old asset hashes (eliminates CSS/JS 404 errors during transitions)

---

## 8. Scheduling Resilience

### `topologySpreadConstraints`

Key workloads (Next.js, Prometheus, Loki) use `maxSkew: 1` with
`whenUnsatisfiable: ScheduleAnyway`. This allows scheduling to proceed even
when topology spread would be violated (needed on a small 2-node general pool
where CA may not have scaled up yet).

### Descheduler

A Descheduler CronJob runs periodically to correct topology violations that
accumulated while CA was scaling. It respects PodDisruptionBudgets and is
pinned to the monitoring node to prevent self-eviction (the Descheduler cannot
evict itself).

---

## 9. Persistent Storage

### EBS CSI Driver

Both pools have the full EBS CSI IAM policy set (`ec2:CreateVolume`,
`ec2:AttachVolume`, `ec2:DetachVolume`, etc.) because the CSI node agent runs
as a DaemonSet on every node.

**`WaitForFirstConsumer` binding mode:** PVCs are not bound until a pod is
scheduled, ensuring the EBS volume is created in the same AZ as the pod.
Without this, the volume may be created in a different AZ than the node,
causing attachment failure.

**`Retain` reclaim policy:** PVs survive ArgoCD prune operations. Monitoring
stack PVs (Prometheus TSDB, Loki chunks) are not deleted when ArgoCD syncs
a chart change that removes the PVC temporarily.

**Stale PV cleanup on monitoring node replacement:** When the monitoring ASG
replaces its instance, the worker bootstrap (step 4: `step_clean_stale_pvs`)
cleans up `monitoring` namespace PVs with `nodeAffinity` referencing the dead
hostname. ArgoCD recreates the PVCs on the next sync, and `local-path-provisioner`
provisions fresh PVs on the new node.

---

## 10. IAM Design

### Split IAM Blast Radius

The single `KubernetesWorkerAsgStack` applies different IAM policies per pool
type:

**Both pools receive:**
- SSM `GetParameter` for join credentials
- KMS decrypt for SSM SecureString
- ECR pull (`GetDownloadUrlForLayer`, `BatchGetImage`, `ListImages`, `DescribeImages`)
- SSM `StartAutomationExecution` + `GetAutomationExecution`
- EBS CSI volume lifecycle
- CloudWatch log read (Grafana datasource + Alloy log shipping)
- DynamoDB read-only on content table (`bedrock-<env>-ai-content`)
- S3 read-only on KB data bucket (`bedrock-<env>-kb-data`)
- CA Describe* (both pools report ASG membership)

**Monitoring pool additionally receives:**
- `AWS:job-function/ViewOnlyAccess` (Steampipe cloud inventory)
- Additional S3/Route 53/CloudFront/WAFv2 read (Steampipe queries)
- CA `SetDesiredCapacity` + `TerminateInstanceInAutoScalingGroup` (CA runs here)
- SNS `Publish` to monitoring alerts topic

### Credential Model — API Services

Both `public-api` and `admin-api` use IMDS (EC2 Instance Profile) for all AWS
SDK calls. No AWS credentials appear in Kubernetes Secrets or ConfigMaps.
Cognito client IDs (non-secret) are stored in `admin-api-secrets` for the
JWT middleware; the actual credentials are the Cognito public JWKS endpoint.

---

## 11. DR Strategy

| Asset | Backup Target | Mechanism | Recovery |
|---|---|---|---|
| etcd snapshot | S3 (`dr-backups/` prefix) | Hourly systemd timer (`install_etcd_backup`) | `restore_backup` (step 2, control-plane bootstrap) |
| Kubernetes PKI (`/etc/kubernetes/pki/`) | S3 | Backed up alongside etcd | Restored before `_reconstruct_control_plane` |
| `admin.conf` | S3 | Alongside etcd | Restored → used to skip `kubeadm init` on DR path |
| TLS Secret (`ops-tls-cert`) | SSM SecureString | `backup_tls_cert` (step 10c, ArgoCD bootstrap) | `restore_tls_cert` (step 5d, ArgoCD bootstrap) |
| ArgoCD JWT signing key | SSM SecureString | `backup_argocd_secret_key` (step 10d) | `preserve_argocd_secret` → `restore_argocd_secret` |
| ArgoCD admin password | SSM | `set_admin_password` (step 10b) | Read at bootstrap |
| GitHub SSH deploy key | SSM | Pre-provisioned | `resolve_deploy_key` (step 2, ArgoCD bootstrap) |

**Recovery RTO:** A full control-plane replacement completes in approximately
5–8 minutes: S3 restore → `_reconstruct_control_plane` (~3 min) → ArgoCD bootstrap
(~5 min) → workers rejoin (SSM token discovery, `kubeadm join`).

---

## 12. Observability Stack

| Component | Role | Node |
|---|---|---|
| Prometheus | Metrics collection | monitoring pool |
| Loki | Log aggregation | monitoring pool |
| Tempo | Distributed tracing | monitoring pool |
| Grafana | Dashboards + alerting | monitoring pool |
| Alloy | Collector agent (DaemonSet) | all nodes |
| Cluster Autoscaler | Scale decisions | monitoring pool |

**Traefik → Tempo:** Traefik ships OTLP traces to `tempo.monitoring.svc.cluster.local:4317`
(gRPC, insecure — in-cluster). This provides Traefik request traces alongside
Next.js/Node.js application traces.

**Monitoring ingress:** Monitoring services (Grafana, Prometheus) are exposed
via Traefik `IngressRoute` on operator-controlled hostnames. These routes are
**not** fronted by CloudFront — they use Traefik's `ops-tls-cert` directly.
An IP allowlist middleware (created in step 7b of ArgoCD bootstrap) restricts
access to operator IPs only.

---

## 13. Self-Healing Agent

The AI-driven remediation pipeline:

```
CloudWatch Alarm → EventBridge Rule → Lambda (Bedrock ConverseCommand loop)
    ↓
MCP Gateway (AgentCore)
    ↓
Tools: diagnose_alarm | ebs_detach | check_node_health | analyse_cluster_health
    ↓
SNS → Email (monitoring alerts topic, created per monitoring pool by worker-asg-stack.ts)
```

The monitoring alerts SNS topic ARN is published to SSM at CDK synth time
(`{prefix}/monitoring/alerts-topic-arn-pool`) and injected into ArgoCD Helm
parameters during `inject_monitoring_helm_params` (step 5b of ArgoCD bootstrap).

**FinOps observability:** The `admin-api` FinOps route `GET /finops/self-healing`
queries the `self-healing-development/SelfHealing` CloudWatch namespace for
`InputTokens` and `OutputTokens`, giving admin dashboard operators token cost
visibility per remediation event.

---

## 14. Key Design Decisions Summary

| Decision | Rationale |
|---|---|
| Single parameterised `WorkerPoolType` replaces three named stacks | Eliminates IAM policy drift; one source of truth for all node IAM; easier to add future pools |
| SSM over `Fn::ImportValue` for cross-stack references | Allows independent stack deployment without CloudFormation dependency graph; runtime SSM lookup survives stack deletion/recreation |
| Monitoring pool gets CA scale-write, general pool does not | Minimises blast radius if a general-pool node is compromised |
| `hostNetwork` DaemonSet Traefik | Every node listens on 80/443; NLB health checks handle EIP failover routing |
| CloudFront terminates public TLS; Traefik terminates monitoring TLS | Allows wildcard ACM cert for public domain without sharing cert key material with cluster nodes |
| IMDS credentials for all in-cluster API services | No static credentials in pods; automatic rotation; compatible with instance role boundary |
| BFF pattern (pod-to-pod for admin calls) | Browser never talks cross-origin to admin-api; CORS is defence-in-depth only |
| Non-fatal bootstrap steps with SM-B retry | Traefik CRDs not ready at bootstrap time; idempotent retry by deploy.py prevents blocking the entire bootstrap on one step |
| `WaitForFirstConsumer` + `Retain` for EBS | Prevents cross-AZ volume placement; protects monitoring TSDB from ArgoCD prune |
| Stale PV cleanup on monitoring node bootstrap | Monitoring pods cannot schedule against dead-node PV affinity; proactive cleanup on new node join prevents manual intervention |
