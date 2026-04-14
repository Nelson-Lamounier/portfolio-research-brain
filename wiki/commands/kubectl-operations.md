---
title: kubectl Operations Reference
type: command
tags: [kubernetes, kubectl, commands, debugging, argocd, operations]
sources: [raw/kubectl-operations-reference.md, raw/kubernetes_observability_report.md, raw/prometheus-targets-troubleshooting.md, raw/deployment_testing_guide.md, raw/cross-node-networking-troubleshooting.md]
created: 2026-04-14
updated: 2026-04-14
---

# kubectl Operations Reference

Day-2 operations command reference for the ArgoCD-managed cluster. Complements [[k8s-bootstrap-commands]] (bootstrap and CDK) with cluster management, debugging, and the ArgoCD+kubectl workflow.

## Core Flags

| Flag | Short | Purpose |
|---|---|---|
| `--namespace` | `-n` | Target namespace |
| `--output` | `-o` | Format: `json`, `yaml`, `wide` |
| `--all-namespaces` | `-A` | All namespaces |
| `--selector` | `-l` | Filter by label |
| `--watch` | `-w` | Stream changes live |

---

## Inspect: `get` and `describe`

Use `get` for quick status. Use `describe` when something is wrong — it shows events, conditions, attached volumes, environment variables, and recent state transitions.

```bash
# All pods in a namespace
kubectl get pods -n monitoring
kubectl get pods -n monitoring -o wide         # includes node and IP
kubectl get pods -A                            # all namespaces

# Filter by label
kubectl get pods -n monitoring -l app=steampipe

# Describe (events + full detail)
kubectl describe pod <pod-name> -n monitoring
kubectl describe deployment steampipe -n monitoring
kubectl describe node <node-name>
```

---

## exec — Run Commands Inside a Pod

`exec` runs a command inside a running pod's container — not on the host. The `--` separator is critical: without it, kubectl interprets flags after the pod name as its own.

```bash
# Single command
kubectl exec -n monitoring deployment/steampipe -- steampipe plugin list

# Interactive shell
kubectl exec -n monitoring deployment/steampipe -it -- /bin/bash

# Check a mounted config file
kubectl exec -n monitoring deployment/steampipe -- \
  cat /home/steampipe/.steampipe/config/aws.spc

# Check environment variables
kubectl exec -n monitoring deployment/steampipe -- env | grep AWS

# Test DNS resolution from inside a pod
kubectl exec -n monitoring deployment/steampipe -- \
  nslookup steampipe.monitoring.svc.cluster.local

# Multi-container pod (specify container)
kubectl exec -n monitoring <pod> -c steampipe -- <command>
```

---

## Ephemeral Pods — In-Cluster Connectivity Testing

`kubectl run --rm -it --restart=Never` creates a temporary pod, runs a command, and deletes it on exit. Essential for testing service-to-service connectivity without exec-ing into a running pod.

```bash
# Test HTTP status code of an in-cluster URL
kubectl run curl-test --rm -it --restart=Never \
  --image=curlimages/curl -- \
  curl -s -o /dev/null -w "%{http_code}" \
  http://prometheus.monitoring.svc.cluster.local:9090/prometheus/metrics

# Test from a specific namespace (NetworkPolicy enforcement)
kubectl run curl-test --rm -it --restart=Never \
  -n monitoring --image=curlimages/curl -- \
  curl -s -o /dev/null -w "%{http_code}" \
  http://nextjs.nextjs-app.svc.cluster.local:3000/api/metrics

# Pretty-print JSON API response
kubectl run curl-test --rm -it --restart=Never \
  --image=curlimages/curl -- \
  curl -s http://prometheus.monitoring.svc.cluster.local:9090/prometheus/api/v1/targets \
  | python3 -m json.tool
```

| Flag | Meaning |
|---|---|
| `--rm` | Delete the pod when the command exits |
| `-it` | Attach stdin/stdout (interactive) |
| `--restart=Never` | Don't restart on exit — one-shot execution |
| `-n <namespace>` | Run from a specific namespace — tests NetworkPolicy rules |
| `--image=curlimages/curl` | Lightweight image with curl installed |

> Run from `-n monitoring` when testing whether the monitoring namespace can reach a target — this exercises the actual NetworkPolicy rules as Prometheus would see them.

See [[prometheus-scrape-targets]] for real examples using this pattern to diagnose scrape failures.

---

## rollout — Manage Deployment Updates

| Scenario | Command |
|---|---|
| ConfigMap changed but pod didn't restart | `rollout restart` |
| Check if deployment finished updating | `rollout status` |
| Something broke, need to revert | `rollout undo` |
| View update history | `rollout history` |

```bash
# Force restart all pods (required after ConfigMap/Secret changes — they don't auto-restart)
kubectl rollout restart deployment/steampipe -n monitoring

# Watch progress
kubectl rollout status deployment/steampipe -n monitoring

# Undo to previous revision
kubectl rollout undo deployment/steampipe -n monitoring

# Undo to a specific revision
kubectl rollout undo deployment/steampipe -n monitoring --to-revision=2

# View history
kubectl rollout history deployment/steampipe -n monitoring
```

> `rollout restart` adds a `restartedAt` annotation — forces pod recreation without changing the spec. Safe and idempotent.

---

## Logs

```bash
# Last 100 lines
kubectl logs -n monitoring deployment/steampipe --tail=100

# Follow in real time
kubectl logs -n monitoring deployment/steampipe -f

# Previous container logs (after crash/restart)
kubectl logs -n monitoring <pod-name> --previous

# Specific container in multi-container pod
kubectl logs -n monitoring <pod-name> -c steampipe

# All pods with a label
kubectl logs -n monitoring -l app=steampipe --all-containers
```

---

## ConfigMaps and Secrets

```bash
# View ConfigMap contents
kubectl get configmap steampipe-config -n monitoring -o yaml

# View a specific data key
kubectl get configmap steampipe-config -n monitoring \
  -o jsonpath='{.data.steampipe\.spc}'

# In-place edit (WARNING: ArgoCD will overwrite on next sync)
kubectl edit configmap steampipe-config -n monitoring
kubectl rollout restart deployment/steampipe -n monitoring   # required after edit
```

---

## Resource Quotas and Limits

```bash
# View namespace quota usage vs limits
kubectl describe resourcequota -n monitoring

# View actual resource usage (requires metrics-server)
kubectl top pods -n monitoring
kubectl top nodes

# Temporarily patch limits (ArgoCD will revert on next sync)
kubectl set resources -n monitoring deployment/steampipe \
  --limits=cpu=500m,memory=1Gi \
  --requests=cpu=100m,memory=512Mi
```

---

## ArgoCD + kubectl Workflow

```
1. Edit Helm chart locally
2. git commit && git push origin develop
3. ArgoCD auto-syncs (~3 min)
4. ConfigMap changed? → kubectl rollout restart
5. Verify: kubectl exec / kubectl logs
```

```bash
# Check if ArgoCD synced the new ConfigMap
kubectl get configmap steampipe-config -n monitoring -o yaml

# Restart pods after ConfigMap sync
kubectl rollout restart deployment/steampipe -n monitoring
kubectl rollout status deployment/steampipe -n monitoring

# Verify config inside pod
kubectl exec -n monitoring deployment/steampipe -- \
  cat /home/steampipe/.steampipe/config/aws.spc

# Check ArgoCD Application sync status
kubectl get applications -n argocd -o custom-columns=\
'NAME:.metadata.name,SYNC:.status.sync.status,HEALTH:.status.health.status'

# Force ArgoCD to sync immediately
kubectl patch application monitoring -n argocd \
  --type merge -p '{"operation":{"sync":{"force":true}}}'

# Pause ArgoCD auto-sync for temporary testing
kubectl patch application monitoring -n argocd \
  --type merge -p '{"spec":{"syncPolicy":null}}'

# Re-enable auto-sync
kubectl patch application monitoring -n argocd \
  --type merge -p '{"spec":{"syncPolicy":{"automated":{"selfHeal":true}}}}'
```

---

## JSONPath (kubectl) vs JMESPath (AWS CLI)

| Feature | JSONPath (kubectl) | JMESPath (AWS CLI) |
|---|---|---|
| Field access | `.metadata.name` | `Parameter.Value` |
| Array all | `[*]` | `[*]` |
| Filter | `[?(@.type=="X")]` | `[?State==\`X\`]` |
| Multi-select | `custom-columns=` | `[Field1,Field2]` |
| Pipe | N/A | `\|` |

### kubectl JSONPath examples

```bash
# Pod names only
kubectl get pods -n monitoring -o jsonpath='{.items[*].metadata.name}'

# Custom columns: name + status + restarts
kubectl get pods -n monitoring \
  -o custom-columns='NAME:.metadata.name,STATUS:.status.phase,RESTARTS:.status.containerStatuses[0].restartCount'

# Current image for a deployment
kubectl get deployment steampipe -n monitoring \
  -o jsonpath='{.spec.template.spec.containers[0].image}'

# Detect OOMKilled containers
kubectl get pods -n monitoring -l app=steampipe \
  -o jsonpath='{.items[*].status.containerStatuses[*].lastState.terminated.reason}'

# Node internal IPs
kubectl get nodes \
  -o jsonpath='{.items[*].status.addresses[?(@.type=="InternalIP")].address}'

# Memory limits for all containers in a namespace
kubectl get pods -n monitoring \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.containers[*].resources.limits.memory}{"\n"}{end}'
```

### AWS CLI JMESPath examples

```bash
# Running instances: ID + private IP
aws ec2 describe-instances \
  --query 'Reservations[*].Instances[?State.Name==`running`].[InstanceId,PrivateIpAddress]' \
  --output table

# Most recently pushed ECR image tag
aws ecr describe-images \
  --repository-name steampipe-aws \
  --query 'sort_by(imageDetails, &imagePushedAt)[-1].imageTags[0]' \
  --output text

# SSM parameter value
aws ssm get-parameter \
  --name "/k8s/development/elastic-ip" \
  --query 'Parameter.Value' --output text
```

---

## BlueGreen Deployment Testing

```bash
# Quick health summary for all rollouts
kubectl get rollout -A -o custom-columns=\
'NS:.metadata.namespace,NAME:.metadata.name,STATUS:.status.phase,DESIRED:.spec.replicas,READY:.status.readyReplicas'

# Watch live rollout state (Argo Rollouts plugin)
kubectl argo rollouts get rollout nextjs -n nextjs-app --watch
kubectl argo rollouts get rollout start-admin -n start-admin --watch

# Check active vs. preview services
kubectl -n nextjs-app get svc
# Expected: nextjs (active) and nextjs-preview (preview)

# Check both IngressRoutes exist
kubectl -n nextjs-app get ingressroutes
# Expected: nextjs AND nextjs-preview

# AnalysisRuns (pre-promotion metrics check)
kubectl -n nextjs-app get analysisruns
kubectl -n nextjs-app describe analysisrun <run-name>

# Promote (after testing preview)
kubectl argo rollouts promote nextjs -n nextjs-app

# Port-forward Prometheus to replicate AnalysisTemplate queries
kubectl -n monitoring port-forward svc/prometheus 9090:9090
# Then open http://localhost:9090 and run the PromQL queries manually
```

---

## Traefik Connectivity Testing

```bash
# Get Traefik pod name
TRAEFIK_POD=$(kubectl -n kube-system get pods -l app.kubernetes.io/name=traefik \
  -o jsonpath='{.items[0].metadata.name}')

# Test connectivity from Traefik's pod network (validates ClusterIP routing)
NEXTJS_IP=$(kubectl -n nextjs-app get svc nextjs -o jsonpath='{.spec.clusterIP}')
kubectl -n kube-system exec "$TRAEFIK_POD" -- \
  wget -qO- --timeout=5 "http://${NEXTJS_IP}:3000/api/health"

# Port-forward Traefik dashboard
kubectl -n kube-system port-forward svc/traefik 9000:9000
# Open: http://localhost:9000/dashboard/#/
# Navigate to: HTTP → Services and HTTP → Routers
# Verify: nextjs@kubernetes and nextjs-preview@kubernetes both present
```

---

## Networking Diagnostics

```bash
# Verify cross-node routing (should show vxlan.calico, not ens5)
ip route | grep 192.168

# Check Calico pod status
kubectl get pods -n calico-system -l k8s-app=calico-node -o wide

# Check SourceDestCheck on all K8s instances (AWS CLI from local machine)
aws ec2 describe-instances \
  --filters "Name=instance-state-name,Values=running" \
  --query 'Reservations[].Instances[].[InstanceId,
    Tags[?Key==`Name`].Value|[0],
    NetworkInterfaces[0].SourceDestCheck]' \
  --output table --region eu-west-1 --profile dev-account

# kube-proxy DaemonSet (verify it's deployed after DR)
kubectl get daemonset kube-proxy -n kube-system

# Manual kube-proxy recovery (if missing after DR restore)
kubeadm init phase addon kube-proxy \
  --apiserver-advertise-address=$(curl -s http://169.254.169.254/latest/meta-data/local-ipv4) \
  --pod-network-cidr=192.168.0.0/16
```

---

## Troubleshooting Patterns

### Pod Won't Start

```bash
# 1. Events and conditions
kubectl describe pod <pod-name> -n monitoring
# Look for: ImagePullBackOff, CrashLoopBackOff, OOMKilled, Pending

# 2. Quota exhausted?
kubectl describe resourcequota -n monitoring

# 3. Node resources
kubectl top nodes
```

### OOMKilled (exit code 137)

```bash
# Confirm OOM
kubectl get pods -n monitoring -l app=steampipe \
  -o jsonpath='{.items[*].status.containerStatuses[*].lastState.terminated.reason}'
# Output: "OOMKilled"

# Increase limit (temporary — ArgoCD will revert)
kubectl set resources deployment/steampipe -n monitoring --limits=memory=1Gi
```

### ArgoCD Keeps Reverting Changes

In-cluster edits are overwritten by ArgoCD on sync. For permanent changes: modify the Helm chart → `git push` → ArgoCD syncs. For temporary testing, pause auto-sync first (see ArgoCD+kubectl Workflow above).

---

## Grafana Dashboard Debugging

Three levels, use in order:

**Level 1 — Panel inspector** (fastest): hover → ⋮ → Inspect → Query. Shows exact SQL and raw error.

**Level 2 — Grafana logs** (connection failures):
```bash
kubectl logs -f -n monitoring deployment/grafana | grep -i "error\|failed\|bad gateway"
```

**Level 3 — [[steampipe]] logs** (SQL/plugin errors):
```bash
kubectl logs -f -n monitoring deployment/steampipe
kubectl logs -n monitoring deployment/steampipe --tail=200 | grep -i "error\|fatal"
```

See [[steampipe]] for the full SQL pitfalls table and per-table debugging commands.

---

## Related Pages

- [[k8s-bootstrap-commands]] — bootstrap, CDK, SSM, Step Functions commands
- [[steampipe]] — cloud inventory tool; exec query reference and SQL pitfalls
- [[argocd]] — GitOps controller; sync management
- [[argo-rollouts]] — BlueGreen testing, preview promotion commands
- [[self-hosted-kubernetes]] — cluster design context
- [[observability-stack]] — monitoring namespace components
- [[prometheus-scrape-targets]] — real in-cluster curl examples; ConfigMap restart workflow
- [[cross-node-networking]] — networking diagnostic commands
- [[kube-proxy-missing-after-dr]] — manual kube-proxy recovery commands
