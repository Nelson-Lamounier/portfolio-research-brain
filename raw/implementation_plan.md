# Kubernetes-Native Worker Architecture (v2)

Replace 3 named CDK worker stacks with 2 purpose-built ASG node groups. CDK shrinks to control-plane + two ASG definitions. Kubernetes manifests (nodeSelector/taints) own workload placement. Cluster Autoscaler owns scale decisions.

## User Review Required

> [!IMPORTANT]
> **This is an additive migration, not a cutover.** The plan adds new ASGs alongside existing named nodes. Old stacks are only deleted after v2 validates on the new nodes. No downtime is expected.

> [!WARNING]
> **Three CDK stacks will be deleted** as the final step:
> - `KubernetesAppWorkerStack` → replaced by `KubernetesWorkerAsgStack` (general-purpose pool)
> - `KubernetesMonitoringWorkerStack` → replaced by `KubernetesWorkerAsgStack` (monitoring pool)
> - `KubernetesArgocdWorkerStack` → consolidated into the general-purpose pool (ArgoCD is not memory-heavy; the taint/toleration model handles isolation without a dedicated stack)
>
> Deleting these stacks will terminate the named EC2 instances. Ensure all workloads have migrated first.

> [!CAUTION]
> **BlueGreen awareness:** ArgoCD already handles application-layer BlueGreen promotion. This plan does not change that. The node migration is transparent to ArgoCD — new nodes join the cluster, pods get rescheduled, rollout proceeds normally. The NLB target group registration is the one concern: the new ASGs must attach to the same NLB target groups as the old ones before you drain the old nodes.

---

## Confirmed Configuration

| Decision | Answer |
|---|---|
| General pool instance type | `t3.small` — scale out via CA, not up |
| General pool pricing | **Spot** (same as monitoring pool) |
| ArgoCD placement | Folds into general pool — no dedicated node |
| SNS alerts topic | Moves to monitoring pool stack, same SSM path |

---

## Architecture: Before vs After

### Before (4 separate CDK stacks)
```
KubernetesBaseStack          — VPC, SGs, NLB, EIP, S3, SSM (stays)
KubernetesControlPlaneStack  — Control plane EC2 (stays)
KubernetesAppWorkerStack     — 1× t3.small, max=1 (DELETE)
KubernetesMonitoringWorkerStack — 1× t3.small, max=1 (DELETE)
KubernetesArgocdWorkerStack  — 1× t3.small, max=1 Spot (DELETE)
```

### After (2 CDK stacks → N Kubernetes-managed instances)
```
KubernetesBaseStack               — unchanged (stays)
KubernetesControlPlaneStack       — unchanged (stays)
KubernetesWorkerAsgStack (general)  — ASG min=1, max=4, t3.small
                                      labels: node-pool=general
                                      workloads: frontend, argocd, cert-manager, system
KubernetesWorkerAsgStack (monitoring) — ASG min=1, max=2, t3.medium
                                        labels: node-pool=monitoring
                                        taint: dedicated=monitoring:NoSchedule
                                        workloads: prometheus, grafana, loki, tempo, alloy
```

### IAM Role Consolidation
The 3 worker roles become 2 **shared** roles — one per ASG. All IAM policies from the 3 existing stacks are merged:
- `general-pool` role = AppWorker + ArgocdWorker permissions (ECR pull + Image Updater, DynamoDB, S3 content, CloudWatch read, DNS)
- `monitoring-pool` role = MonitoringWorker permissions (EBS CSI, Steampipe ViewOnly, SNS, CloudWatch deep access)

---

## Proposed Changes

### New File

#### [NEW] [worker-asg-stack.ts](file:///Users/nelsonlamounier/Desktop/portfolio/cdk-monitoring/infra/lib/stacks/kubernetes/worker-asg-stack.ts)

Single parameterised stack replacing all 3 worker stacks. Key design:

```typescript
export type WorkerPoolType = 'general' | 'monitoring';

export interface KubernetesWorkerAsgStackProps extends cdk.StackProps {
    readonly poolType: WorkerPoolType;
    readonly targetEnvironment: Environment;
    readonly controlPlaneSsmPrefix: string;
    readonly namePrefix?: string;
    // Cluster Autoscaler bounds
    readonly minCapacity: number;
    readonly maxCapacity: number;
    readonly desiredCapacity: number;
    readonly instanceType: ec2.InstanceType;
    // Spot optional
    readonly useSpotInstances?: boolean;
    // Notifications (monitoring pool only)
    readonly notificationEmail?: string;
    readonly crossAccountDnsRoleArn?: string;
}
```

**Key differences from existing stacks:**

| Feature | Old stacks | New `worker-asg-stack.ts` |
|---|---|---|
| ASG capacity | min=0, max=1, desired=1 (fixed) | min/max/desired configurable — Cluster Autoscaler scales |
| Node tags | absent | `k8s.io/cluster-autoscaler/enabled: "true"` + `k8s.io/cluster-autoscaler/{clusterName}: "owned"` |
| Node labels | per-stack hardcoded | `node-pool=general\|monitoring` via user data |
| Node taints | none (app/argocd) or none | `dedicated=monitoring:NoSchedule` for monitoring pool |
| IAM role | 3 separate roles | 2 merged roles |
| NLB registration | each ASG registers both TGs | same — both ASGs register both NLB TGs |
| SSM instance ID | named (app-worker-instance-id) | pool-name-based |

**Cluster Autoscaler tags (required):**
```typescript
asgConstruct.autoScalingGroup.addTag(
    'k8s.io/cluster-autoscaler/enabled', 'true', true
);
asgConstruct.autoScalingGroup.addTag(
    `k8s.io/cluster-autoscaler/${clusterName}`, 'owned', true
);
// Propagate labels/taints to CA so it can simulate scheduling
asgConstruct.autoScalingGroup.addTag(
    'k8s.io/cluster-autoscaler/node-template/label/node-pool', poolType, true
);
```

---

### Modified Files

#### [MODIFY] [index.ts](file:///Users/nelsonlamounier/Desktop/portfolio/cdk-monitoring/infra/lib/stacks/kubernetes/index.ts)
Export `KubernetesWorkerAsgStack`. Keep old stack exports until migration is complete (allows both to coexist during transition).

#### [MODIFY] [kubernetes factory](file:///Users/nelsonlamounier/Desktop/portfolio/cdk-monitoring/infra/lib/factories)
Replace the 3 named worker stack instantiations with 2 `KubernetesWorkerAsgStack` calls:

```typescript
// General-purpose pool (replaces app-worker + argocd-worker)
new KubernetesWorkerAsgStack(app, `K8s-GeneralPool-${env}`, {
    poolType: 'general',
    minCapacity: 1, maxCapacity: 4, desiredCapacity: 2,
    instanceType: ec2.InstanceType.of(ec2.InstanceClass.T3, ec2.InstanceSize.SMALL),
    useSpotInstances: false, // on-demand for stability
    ...commonProps,
});

// Monitoring pool (replaces monitoring-worker)
new KubernetesWorkerAsgStack(app, `K8s-MonitoringPool-${env}`, {
    poolType: 'monitoring',
    minCapacity: 1, maxCapacity: 2, desiredCapacity: 1,
    instanceType: ec2.InstanceType.of(ec2.InstanceClass.T3, ec2.InstanceSize.MEDIUM),
    useSpotInstances: true, // Spot acceptable — Prometheus re-scrapes, Loki re-indexes
    notificationEmail: props.notificationEmail,
    ...commonProps,
});
```

#### [MODIFY] Kubernetes manifests (Helm values)
Workload placement moves from CDK into manifests. Required changes:

| App | Current placement | New placement |
|---|---|---|
| Next.js (site) | `nodeSelector: workload=frontend` | `nodeSelector: node-pool=general` |
| start-admin | `nodeSelector: workload=frontend` | `nodeSelector: node-pool=general` |
| ArgoCD | `nodeSelector: workload=argocd`, `tolerations: workload=argocd` | `nodeSelector: node-pool=general` (no taint needed) |
| Prometheus/Grafana/Loki/Tempo | `nodeSelector: workload=monitoring` | `nodeSelector: node-pool=monitoring` + `tolerations: dedicated=monitoring:NoSchedule` |
| cert-manager | any node | `nodeSelector: node-pool=general` |
| Traefik DaemonSet | all nodes | all nodes (unchanged — DaemonSet by definition) |

---

### Kubernetes Add-ons (new manifest additions)

#### Cluster Autoscaler
Deploy as an ArgoCD Application. Minimal configuration for single-AZ development:

```yaml
# kubernetes-app/k8s-bootstrap/system/cluster-autoscaler/values.yaml
autoDiscovery:
  clusterName: k8s-development
awsRegion: eu-west-1
nodeSelector:
  node-pool: general
extraArgs:
  scale-down-delay-after-add: 10m
  scale-down-unneeded-time: 10m
  skip-nodes-with-local-storage: "false"  # allow scaling nodes with emptyDir
```

The CA IAM role is granted in `KubernetesWorkerAsgStack` via the pod identity / IRSA pattern (or simpler: CA runs with the node's instance role, which already has `autoscaling:DescribeAutoScalingGroups` etc via the merged policy).

---

## Migration Flow (Zero-Downtime)

```
Phase 1 — Add new ASGs (no changes to existing nodes)
  └── Deploy K8s-GeneralPool + K8s-MonitoringPool via CDK
      → New EC2 instances join the cluster
      → CA installs on new general pool node

Phase 2 — Migrate workloads (frontend v2 entry point)
  └── Update Helm values: nodeSelector=node-pool=general
  └── ArgoCD syncs → pods evict from old nodes, schedule on new
  └── NLB health checks validate new nodes are serving traffic
  └── BlueGreen promotion proceeds normally via ArgoCD

Phase 3 — Validate (1 deployment cycle minimum)
  └── monitoring stack → validate prometheus scraping new nodes
  └── ArgoCD → validate sync state, no pending pods on old nodes
  └── NLB → access logs confirm traffic flowing to new instances

Phase 4 — Drain & delete old named stacks
  └── kubectl drain k8s-app-worker / k8s-mon-worker / k8s-argocd-worker
  └── cdk destroy K8s-AppWorker-dev K8s-MonWorker-dev K8s-ArgocdWorker-dev
```

---

## Cluster Autoscaler IAM Permissions

The instance role for both pools needs these additional permissions (not in current stacks):

```typescript
new iam.PolicyStatement({
    sid: 'ClusterAutoscaler',
    effect: iam.Effect.ALLOW,
    actions: [
        'autoscaling:DescribeAutoScalingGroups',
        'autoscaling:DescribeAutoScalingInstances',
        'autoscaling:DescribeLaunchConfigurations',
        'autoscaling:DescribeScalingActivities',
        'autoscaling:SetDesiredCapacity',
        'autoscaling:TerminateInstanceInAutoScalingGroup',
        'ec2:DescribeLaunchTemplateVersions',
        'ec2:DescribeInstanceTypes',
    ],
    resources: ['*'],
});
```

---

## SSM Automation & Script Impact Analysis

This is the **most critical section**. The existing scripts are tightly coupled to 3 specific role names (`app-worker`, `mon-worker`, `argocd-worker`). Every reference must be updated or the automation will silently skip nodes.

### 1. `trigger-bootstrap.ts` — HIGH IMPACT ⚠️

**Problem:** `buildTargets()` hardcodes 3 worker target entries with role names and SSM execution ID paths that reference the old named roles.

**Current:**
```typescript
{ role: 'app-worker',    targetTagValue: 'app-worker',    execParam: '.../bootstrap/worker-execution-id' },
{ role: 'mon-worker',   targetTagValue: 'mon-worker',    execParam: '.../bootstrap/mon-worker-execution-id' },
{ role: 'argocd-worker', targetTagValue: 'argocd-worker', execParam: '.../bootstrap/argocd-worker-execution-id' },
```

**Fix:** Replace with 2 pool-based targets:
```typescript
{ role: 'general-pool',    targetTagValue: 'general-pool',    execParam: '.../bootstrap/general-pool-execution-id' },
{ role: 'monitoring-pool', targetTagValue: 'monitoring-pool', execParam: '.../bootstrap/monitoring-pool-execution-id' },
```

> [!NOTE]
> `resolveInstanceByTag()` already does EC2 tag discovery — it just needs the new tag values. **No architectural change.** The function is already correct; only the tag value strings change.

> [!WARNING]
> During the migration window (new ASGs deployed but old named nodes still running), both old and new tags co-exist. The new pool tags (`general-pool`, `monitoring-pool`) resolve the new instances; old tag values (`app-worker`, etc.) still resolve old instances. Remove old targets from the script ONLY after the old stacks are drained.

---

### 2. `verify-cluster.sh` — MEDIUM IMPACT

**Problem:** Check 2 (Node Labels) hardcodes `workload=frontend` and `workload=monitoring`:
```bash
APP_NODES=$(kube get nodes -l workload=frontend ...)
MON_NODES=$(kube get nodes -l workload=monitoring ...)
```

**Fix:** Replace with new pool labels:
```bash
GENERAL_NODES=$(kube get nodes -l node-pool=general ...)
MON_NODES=$(kube get nodes -l node-pool=monitoring ...)
```

Also update the error message "Fix (permanent)" text and `FIX` examples in the same section (lines 263–298).

**Node count check (line 198):** Currently expects exactly `3` nodes (1 CP + 2 workers). With autoscaling, the count is dynamic. Change to:
```bash
# Expect at least 3 (1 control-plane + 1 general + 1 monitoring)
if [ "$NODE_COUNT" -ge 3 ]; then
  pass "Node count: $NODE_COUNT (minimum 3 met)"
```

---

### 3. `stale_pvs.py` — LOW IMPACT (constant update only)

**Problem:** Hardcoded constant gates PV cleanup to nodes with label `workload=monitoring`:
```python
MONITORING_WORKER_LABEL = "workload=monitoring"  # line 38
```

**Fix:** Update to new label:
```python
MONITORING_WORKER_LABEL = "node-pool=monitoring"
```

This affects both `stale_pvs.py` AND `boot/steps/worker.py` which has the same constant at line 454. Both files must be updated together.

---

### 4. `system/argocd/install.yaml` — HIGH IMPACT ⚠️

**Problem:** The vendored ArgoCD manifest has `workload: argocd` in **7 nodeSelector blocks** (lines ~31720, 31862, 31964, 32065, 32422, 32828, 33204). This file is applied directly by `bootstrap_argocd.py` — it is not a Helm chart, so there is no values override.

**Fix options (choose one):**
- **Option A (Recommended):** Mass-replace `workload: argocd` → `node-pool: general` in the vendored manifest. This is safe because the ArgoCD vendor file is intentionally customised for this cluster.
- **Option B:** Patch the manifest post-apply with `kubectl patch`. More fragile, not recommended.

**Chosen approach: Option A** — sed replacement on all 7 occurrences.

> [!IMPORTANT]
> The `install.yaml` must be regenerated if ArgoCD is upgraded. Document this in the file header.

---

### 5. Helm `values.yaml` Files — MEDIUM IMPACT

All 8 files below need `nodeSelector` updated:

| File | Current value | New value |
|---|---|---|
| `workloads/charts/nextjs/chart/values.yaml` | `workload: frontend` | `node-pool: general` |
| `workloads/charts/start-admin/chart/values.yaml` | `workload: frontend` | `node-pool: general` |
| `platform/charts/monitoring/chart/values.yaml` | `workload: monitoring` (implied) | `node-pool: monitoring` |
| `platform/argocd-apps/opencost.yaml` | `workload: monitoring` | `node-pool: monitoring` |
| `platform/argocd-apps/crossplane.yaml` | `workload: monitoring` | `node-pool: monitoring` |
| `platform/argocd-apps/argocd-image-updater.yaml` | `workload: argocd` | `node-pool: general` |
| `platform/argocd-apps/argo-rollouts.yaml` | `workload: argocd` (×2) | `node-pool: general` |
| `platform/charts/crossplane-providers/manifests/providers.yaml` | `workload: monitoring` | `node-pool: monitoring` |

**Tolerations** must also be added to monitoring workloads (Prometheus, Grafana, etc.) since the monitoring pool will carry `dedicated=monitoring:NoSchedule`:
```yaml
tolerations:
  - key: dedicated
    operator: Equal
    value: monitoring
    effect: NoSchedule
```

---

### 6. CDK Unit Tests — LOW IMPACT

3 test files reference old instance-ID SSM paths in assertions:
- `argocd-worker-stack.test.ts` → expects `bootstrap/argocd-worker-instance-id`
- `monitoring-worker-stack.test.ts` → expects `bootstrap/mon-worker-instance-id`
- `ssm-automation-runtime.integration.test.ts` → expects `mon-worker-execution-id` and `argocd-worker-execution-id`

These tests will be replaced with new tests for `KubernetesWorkerAsgStack`.

---

### Impact Summary Table

| File | Change Type | Blocker? |
|---|---|---|
| `trigger-bootstrap.ts` | Role names + SSM paths | ✅ Yes — automation fails to target new nodes |
| `verify-cluster.sh` | Label selectors + node count | ⚠️ No — diagnostic only, not production path |
| `stale_pvs.py` + `worker.py` | Constant value | ✅ Yes — PV cleanup silently skips monitoring pool |
| `system/argocd/install.yaml` | 7× nodeSelector blocks | ✅ Yes — ArgoCD pods will be Pending at bootstrap |
| 8× Helm `values.yaml` files | nodeSelector + tolerations | ✅ Yes — pods Pending after migration |
| CDK unit tests | Assertion strings | ⚠️ No — CI fails, not production |

---

## Open Questions (All Resolved)

> [!NOTE]
> **1. ✅ Instance type for general pool.** `t3.small` — scale out horizontally via Cluster Autoscaler (more instances, not bigger).

> [!NOTE]
> **2. ✅ General pool pricing.** Spot — BlueGreen handles graceful Next.js handoff; ArgoCD tolerates interruptions.

> [!NOTE]
> **3. ✅ ArgoCD placement.** Folds into general pool — no dedicated node, no `workload=argocd` taint. Saves one Spot instance.

> [!NOTE]
> **4. ✅ SNS topic.** Moves to monitoring pool stack. SSM path unchanged — no application changes needed.

---

## Verification Plan

### Automated Tests
- `yarn workspace infra exec cdk synth -c project=kubernetes -c environment=dev` — confirm both new stacks synthesise cleanly alongside the old ones
- Existing CDK unit tests pass (no regression)

### Manual Verification
1. `kubectl get nodes -L node-pool` — new nodes show correct label
2. `kubectl get pods -A -o wide` — all pods on new nodes after drain
3. NLB health check → both new ASG instances show healthy
4. ArgoCD BlueGreen promotion cycle → completes successfully
5. Cluster Autoscaler logs → `I0408 ... Scale-up: ... 1 new nodes`
6. `cdk destroy` old stacks → no CloudFormation errors
