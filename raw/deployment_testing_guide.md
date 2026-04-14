# Deployment Testing Guide
## nextjs & start-admin — BlueGreen + UI + Networking

> **Live state observed at 2026-04-09 04:33 BST**
> | Application | ArgoCD Sync | ArgoCD Health | Image |
> |---|---|---|---|
> | `nextjs` | ✅ Synced | ✅ Healthy | `c9614a118d2e...-r1` |
> | `start-admin` | ✅ Synced | ⚠️ **Degraded** | `latest` |

---

## Phase 1 — ArgoCD Application Health

### Step 1.1 — Check ArgoCD App status in the terminal

```bash
# List both apps with health + sync status in one shot
kubectl -n argocd get applications nextjs start-admin \
  -o custom-columns=\
'NAME:.metadata.name,HEALTH:.status.health.status,SYNC:.status.sync.status,IMAGE:.status.summary.images[0]'
```

**Expected output for `nextjs`:**
```
NAME     HEALTH    SYNC     IMAGE
nextjs   Healthy   Synced   771826808455.dkr.ecr.eu-west-1.amazonaws.com/nextjs-frontend:c9614a...
```

**Expected output for `start-admin`:**
```
NAME          HEALTH     SYNC     IMAGE
start-admin   Healthy    Synced   771826808455.dkr.ecr.eu-west-1.amazonaws.com/start-admin:<SHA>
```

> [!CAUTION]
> `start-admin` is currently **Degraded**. Do NOT skip Phase 4 — investigate the pod status before testing the UI.

---

### Step 1.2 — Check operation message for the last sync

```bash
# See the last sync result + any error message
kubectl -n argocd get application nextjs \
  -o jsonpath='{.status.operationState.message}{"\n"}'

kubectl -n argocd get application start-admin \
  -o jsonpath='{.status.operationState.message}{"\n"}'
```

Expected: `"successfully synced (all tasks run)"`

---

## Phase 2 — Pod & Rollout Health

### Step 2.1 — Check pods are Running

```bash
# nextjs pods (namespace: nextjs-app)
kubectl -n nextjs-app get pods -o wide

# start-admin pods (namespace: start-admin)
kubectl -n start-admin get pods -o wide
```

**What to look for:**
- `STATUS` = `Running`
- `READY` = `1/1` (or `2/2` if a sidecar exists)
- Both active AND preview pods present during a BlueGreen deployment

---

### Step 2.2 — Inspect the Argo Rollout objects

```bash
# nextjs rollout — shows BlueGreen phase, active/preview ReplicaSet
kubectl -n nextjs-app get rollout nextjs -o wide

# start-admin rollout
kubectl -n start-admin get rollout start-admin -o wide
```

**Interpret the output:**

| Phase | Meaning |
|---|---|
| `Healthy` | Active ReplicaSet is live and serving traffic |
| `Paused` | Waiting for manual promotion after pre-promotion analysis |
| `Progressing` | Rollout in progress — preview RS is starting up |
| `Degraded` | Rollout failed — check AnalysisRun or pod events |

---

### Step 2.3 — Use the Argo Rollouts kubectl plugin (recommended)

> [!TIP]
> This gives a beautiful tree view showing active vs. preview ReplicaSets, replica counts, and phase.

```bash
# Install the plugin once (if not present)
brew install argoproj/tap/kubectl-argo-rollouts

# Watch the live rollout state (press Ctrl+C to exit)
kubectl argo rollouts get rollout nextjs -n nextjs-app --watch

kubectl argo rollouts get rollout start-admin -n start-admin --watch
```

**Example healthy BlueGreen output:**
```
Name:            nextjs
Namespace:       nextjs-app
Status:          ✔ Healthy
Strategy:        BlueGreen
Active Service:  nextjs
Preview Service: nextjs-preview

REVISION  STATUS     PODS   READY  AVAILABLE
2         ✔ Healthy  1      1      1     ← active (green, serving traffic)
1         • Scaled   0      0      0     ← old (blue, scaled down)
```

**BlueGreen mid-rollout output (what you want to see when testing):**
```
REVISION  STATUS       PODS   READY  AVAILABLE
3         ◌ Running    1      1      1     ← preview (new version)
2         ✔ Healthy    1      1      1     ← active (current stable)
```

---

## Phase 3 — BlueGreen Verification (Is it Applied?)

### Step 3.1 — Confirm both Services exist

```bash
# nextjs: active + preview services must both be present
kubectl -n nextjs-app get svc

# Expected:
# NAME             TYPE        CLUSTER-IP   PORT(S)   
# nextjs           ClusterIP   10.x.x.x     3000/TCP  ← active (production traffic)
# nextjs-preview   ClusterIP   10.x.x.x     3000/TCP  ← preview (test traffic)

# start-admin: same pattern
kubectl -n start-admin get svc

# Expected:
# NAME                  TYPE        CLUSTER-IP   PORT(S)   
# start-admin           ClusterIP   10.x.x.x     5001/TCP  ← active
# start-admin-preview   ClusterIP   10.x.x.x     5001/TCP  ← preview
```

### Step 3.2 — Confirm both IngressRoutes exist

```bash
kubectl -n nextjs-app get ingressroutes
# Expected: nextjs  AND  nextjs-preview

kubectl -n start-admin get ingressroutes
# Expected: start-admin  AND  start-admin-preview
```

### Step 3.3 — Verify the Rollout strategy field

```bash
# Confirm the strategy is blueGreen, not canary or rolling
kubectl -n nextjs-app get rollout nextjs \
  -o jsonpath='{.spec.strategy}' | python3 -m json.tool

kubectl -n start-admin get rollout start-admin \
  -o jsonpath='{.spec.strategy}' | python3 -m json.tool
```

**Expected output snippet:**
```json
{
  "blueGreen": {
    "activeService": "nextjs",
    "previewService": "nextjs-preview",
    "autoPromotionEnabled": false,
    "scaleDownDelaySeconds": 30
  }
}
```

---

## Phase 4 — Investigating `start-admin` Degraded Status

> [!WARNING]
> `start-admin` is **Degraded**. Run these checks before attempting UI testing.

### Step 4.1 — Get pod events

```bash
kubectl -n start-admin describe pods
```

Look for:
- `ImagePullBackOff` → ECR pull failure (check IRSA / ECR token)
- `CrashLoopBackOff` → App is crashing (check logs)
- `Pending` → No node available (check `node-pool: general` node label)

### Step 4.2 — Check pod logs

```bash
# Get the pod name first
POD=$(kubectl -n start-admin get pods -o jsonpath='{.items[0].metadata.name}')

# Tail the last 100 lines
kubectl -n start-admin logs "$POD" --tail=100

# If the pod has restarted, check the previous container logs
kubectl -n start-admin logs "$POD" --previous
```

### Step 4.3 — Check if ECR token is fresh

```bash
# The ECR token refresher should regenerate the imagePullSecret
kubectl -n start-admin get secret ecr-token -o jsonpath='{.metadata.creationTimestamp}'

# Also check the token refresher pod
kubectl -n kube-system get pods -l app=ecr-token-refresh
```

### Step 4.4 — Check the rollout event log

```bash
kubectl -n start-admin describe rollout start-admin | tail -30
```

### Step 4.5 — Check if `latest` tag is the problem

> [!IMPORTANT]
> `start-admin` is using `tag: "latest"` in `start-admin-values.yaml`. ArgoCD Image Updater's `allow-tags` regexp **only matches SHA tags** (`^[0-9a-f]{7,40}(-r[0-9]+)?$`). This means Image Updater will **never update** the image from `latest` to a SHA tag automatically.
>
> Fix: Push a SHA-tagged image to ECR and update `start-admin-values.yaml` to pin a real commit SHA.

```bash
# Verify what tag is actually deployed
kubectl -n start-admin get rollout start-admin \
  -o jsonpath='{.spec.template.spec.containers[0].image}'
```

---

## Phase 5 — Pre-Promotion Analysis Check

> Only relevant when a new rollout is in progress (preview RS spinning up).

### Step 5.1 — List AnalysisRuns

```bash
# nextjs
kubectl -n nextjs-app get analysisruns

# start-admin
kubectl -n start-admin get analysisruns
```

### Step 5.2 — Inspect an AnalysisRun

```bash
# Replace <run-name> with the name from Step 5.1
kubectl -n nextjs-app describe analysisrun <run-name>
```

**What to check:**
- `Phase: Running` → analysis in progress
- `Phase: Successful` → metrics passed, ready to promote
- `Phase: Failed` → error rate or P95 latency breached thresholds

### Step 5.3 — Query Prometheus directly to replicate the analysis

```bash
# Port-forward Prometheus (run in a separate terminal)
kubectl -n monitoring port-forward svc/prometheus 9090:9090

# Then in a browser open: http://localhost:9090
# Run this PromQL to check error rate:
# scalar(sum(rate(traefik_service_requests_total{service=~"nextjs-nextjs-app-.*@kubernetes",code=~"5.."}[5m])) / sum(rate(traefik_service_requests_total{service=~"nextjs-nextjs-app-.*@kubernetes"}[5m])))

# Run this for P95 latency (ms):
# scalar(histogram_quantile(0.95, sum(rate(traefik_service_request_duration_seconds_bucket{service=~"nextjs-nextjs-app-.*@kubernetes"}[5m])) by (le)) * 1000)
```

---

## Phase 6 — Browser UI Testing

### Step 6.1 — Access the active (production) version

Open your domain in the browser:
- **nextjs** → `https://<your-cloudfront-domain>/`
- **start-admin** → `https://<your-cloudfront-domain>/admin`

> [!NOTE]
> Traffic flows: `Browser → CloudFront → NLB → Traefik → nextjs Service (active RS)`
> The IngressRoute requires the `X-CloudFront-Origin-Secret` header to be present. CloudFront injects this automatically. Direct access to the NLB IP without the header will be **rejected by Traefik**.

### Step 6.2 — Access the preview (blue) version via header

This lets you test the new version **before it is promoted**, without impacting any real users.

**Method A — curl**
```bash
# Test nextjs preview (replace <NLB_IP> with your NLB's IP or internal hostname)
curl -v \
  -H "X-Preview: true" \
  -H "Host: <your-domain>" \
  http://<NLB_IP>/

# Test start-admin preview
curl -v \
  -H "X-Preview: true" \
  -H "Host: <your-domain>" \
  http://<NLB_IP>/admin
```

**Method B — Browser Extension (ModHeader)**

1. Install [ModHeader](https://chrome.google.com/webstore/detail/modheader/) in Chrome/Brave
2. Add a request header: `X-Preview` = `true`
3. Navigate to `https://<your-cloudfront-domain>/` → you will hit the **preview** ReplicaSet
4. Check the response for any visual differences or version indicators

> [!TIP]
> Add a `version` or `build-id` env var to your container and expose it at `/api/health` or `/api/version` so you can definitively confirm which version is active vs. preview.

### Step 6.3 — Verify the health endpoint responds

```bash
# nextjs — port-forward directly for isolated testing (bypasses CloudFront)
kubectl -n nextjs-app port-forward svc/nextjs 3000:3000

# Then open: http://localhost:3000/api/health

# start-admin — port 5001
kubectl -n start-admin port-forward svc/start-admin 5001:5001

# Then open: http://localhost:5001/admin/
```

---

## Phase 7 — Network Connectivity Checks

### Step 7.1 — Verify IngressRoute rules are correct

```bash
# Check the active IngressRoute for nextjs
kubectl -n nextjs-app get ingressroute nextjs -o yaml

# Check the preview IngressRoute
kubectl -n nextjs-app get ingressroute nextjs-preview -o yaml
```

**Key things to verify in the output:**
- `match` rule includes `HeaderRegexp` with your `cloudfront.originSecret` value (not the placeholder)
- `services[0].name` points to the correct service (`nextjs` or `nextjs-preview`)
- `entryPoints` includes `web`

### Step 7.2 — Check NetworkPolicy is not blocking traffic

```bash
kubectl -n nextjs-app describe networkpolicy nextjs-allow-traefik
kubectl -n start-admin describe networkpolicy start-admin-allow-traefik
```

Confirm that:
- Traefik's namespace is in the `namespaceSelector`
- Port `3000` (nextjs) / `5001` (start-admin) is in the `ports` allow list

### Step 7.3 — Check Traefik can reach the pods

```bash
# Get the Traefik pod name
TRAEFIK_POD=$(kubectl -n kube-system get pods -l app.kubernetes.io/name=traefik \
  -o jsonpath='{.items[0].metadata.name}')

# Get the ClusterIP of nextjs service
NEXTJS_IP=$(kubectl -n nextjs-app get svc nextjs -o jsonpath='{.spec.clusterIP}')

# Test connectivity from Traefik's pod network
kubectl -n kube-system exec "$TRAEFIK_POD" -- \
  wget -qO- --timeout=5 "http://${NEXTJS_IP}:3000/api/health"
```

### Step 7.4 — Inspect Traefik dashboard (optional)

```bash
# Port-forward the Traefik dashboard
kubectl -n kube-system port-forward svc/traefik 9000:9000

# Open: http://localhost:9000/dashboard/#/
# Navigate to: HTTP → Services and HTTP → Routers
# Confirm you see: nextjs@kubernetes and nextjs-preview@kubernetes
```

---

## Phase 8 — Manual Promotion Workflow

> Run this only once you have tested the preview and are satisfied it is healthy.

### Step 8.1 — Promote `nextjs`

```bash
kubectl argo rollouts promote nextjs -n nextjs-app
```

### Step 8.2 — Watch the promotion

```bash
kubectl argo rollouts get rollout nextjs -n nextjs-app --watch
```

**Expected sequence:**
1. Preview RS becomes `Active`
2. Old RS enters `ScaleDownDelay` (30 seconds)
3. Old RS scales to 0 replicas
4. Rollout phase = `Healthy`

### Step 8.3 — Promote `start-admin` (only after pod is Healthy)

```bash
kubectl argo rollouts promote start-admin -n start-admin
```

---

## Phase 9 — ArgoCD Image Updater Verification

### Step 9.1 — Check Image Updater logs

```bash
# See what image tags Image Updater is discovering from ECR
kubectl -n argocd logs -l app.kubernetes.io/name=argocd-image-updater --tail=50 | \
  grep -E "nextjs|start-admin"
```

### Step 9.2 — Verify write-back committed to Git

After a successful image update, Image Updater commits `.argocd-source-nextjs.yaml`
to the `develop` branch.

```bash
git log --oneline origin/develop | head -10
# Look for commits like: "build: automatic update of nextjs"
```

### Step 9.3 — Confirm the written-back tag matches the running pod

```bash
# Check what tag Image Updater wrote back
cat kubernetes-app/workloads/charts/nextjs/chart/.argocd-source-nextjs.yaml

# Compare with what's actually running
kubectl -n nextjs-app get rollout nextjs \
  -o jsonpath='{.spec.template.spec.containers[0].image}'
```

---

## Quick Reference — Status at a Glance

```bash
# One-liner health summary for both apps
kubectl get rollout -A -o custom-columns=\
'NS:.metadata.namespace,NAME:.metadata.name,STATUS:.status.phase,DESIRED:.spec.replicas,READY:.status.readyReplicas'
```

```bash
# Check all pods across both namespaces
kubectl get pods -n nextjs-app -n start-admin
# Note: multi-namespace flag requires kubectl 1.28+; otherwise run separately
```
