---
title: Self-Hosted Kubernetes (kubeadm on EC2)
type: concept
tags: [kubernetes, ec2, kubeadm, self-hosted, architecture]
sources: [raw/step-function-runtime-logging.md, raw/kubernetes_system_design_review.md]
created: 2026-04-13
updated: 2026-04-14
---

# Self-Hosted Kubernetes (kubeadm on EC2)

Unlike managed Kubernetes services (EKS, GKE, AKS) that provision the control plane, networking, and node registration automatically, self-hosted Kubernetes using `kubeadm` on EC2 requires explicit automation for everything.

## What kubeadm Does Not Provide

After an EC2 instance boots from the [[golden-ami|Golden AMI]], it has the right binaries installed (`kubeadm`, `kubelet`, `kubectl`, `containerd`) but:

- No cluster exists
- No CNI is installed (pods cannot be scheduled)
- No cloud controller manager (AWS taints block scheduling)
- No GitOps controller
- No application secrets or config

The [[k8s-bootstrap-pipeline]] fills this gap — Python scripts automate every step from blank EC2 instance to functioning cluster node.

## Cluster Topology

**3 nodes total:** one static control-plane EC2 instance and two ASG-backed worker pools.

| Pool | Type | Instance | Spot | Min/Max | Taint | Workloads |
|---|---|---|---|---|---|---|
| `general` | Worker | `t3.small` | ✓ | 1/4 | None | Next.js, start-admin, ArgoCD, system components |
| `monitoring` | Worker | `t3.medium` | ✓ | 1/2 | `dedicated=monitoring:NoSchedule` | Prometheus, Grafana, Loki, Tempo, Alloy, Cluster Autoscaler |

**No taint on general pool:** System pods (Calico, EBS CSI, cert-manager) must always have a schedulable node. Only the monitoring stack is isolated by taint to protect observability capacity from workload pods.

**Single parameterised stack:** The old pattern of three named worker stacks (`AppWorker`, `MonitoringWorker`, `ArgocdWorker`) was replaced by a single `KubernetesWorkerAsgStack` driven by `WorkerPoolType`. This eliminates IAM policy drift and provides one source of truth for all node IAM.

## Node Labels

Applied by `worker.py` via `kubelet --node-labels` at bootstrap time:
- `node-pool=general` — general pool nodes
- `node-pool=monitoring` — monitoring pool nodes

Used by `nodeSelector` on monitoring-stack pods to pin them to the monitoring pool.

## Control Plane Bootstrap (10 Steps)

| Step | What it does |
|---|---|
| 1. AMI validation | Verifies binaries and kernel settings |
| 2. DR restore | Restores etcd + PKI from S3 backup if this is a replacement instance |
| 3. EBS mount | Formats (first boot) and mounts `/data/` — persists state across replacements |
| 4. kubeadm init | Initializes cluster, creates Route 53 DNS, backs up certs to S3 |
| 5. [[calico]] | Installs CNI via Tigera operator — pods can now be scheduled |
| 5b. [[aws-ccm]] | Installs AWS CCM via Helm — removes cloud provider taint |
| 6. kubectl access | Copies kubeconfig to root, ec2-user, ssm-user |
| 7. S3 sync | Downloads bootstrap manifests |
| 8. [[argocd]] | Installs ArgoCD + App-of-Apps root applications |
| 9. Verify | Health checks: nodes Ready, pods healthy, ArgoCD sync |
| 10. etcd backup | Installs hourly systemd timer for S3 etcd snapshots |

## Worker Node Bootstrap (5 Steps)

| Step | What it does |
|---|---|
| 1. AMI validation | Same as control plane |
| 2. `kubeadm join` | Reads join token + CA hash from SSM; detects CA mismatch and resets if needed |
| 3. CloudWatch agent | Log streaming setup |
| 4. Stale PV cleanup | **Monitoring pool only:** removes PVs with `nodeAffinity` to dead hostnames |
| 5. Membership verify | Confirms node registration and correct labels |

**CA mismatch detection:** Before the join idempotency guard, `worker.py` compares the local CA cert hash against `{prefix}/ca-hash` in SSM. If they differ (control-plane was replaced with a new CA), it runs `kubeadm reset -f` so the join proceeds with fresh credentials.

**API reachability gate:** A TCP socket probe loop polls `{endpoint}:6443` every 10s with a 300s timeout before attempting `kubeadm join`. This prevents cascading failures during control-plane initialisation.

## Stale PV Cleanup (Monitoring Pool)

When the monitoring ASG replaces its instance, `local-path` PVs retain `nodeAffinity` to the dead hostname. Monitoring pods (Prometheus, Loki, Tempo) cannot schedule against those PVs.

Step 4 of the worker bootstrap reads all PVs, filters those in the `monitoring` namespace with affinity to nodes no longer in the cluster, and deletes both the PVC and PV. ArgoCD recreates them on the next sync cycle; `local-path-provisioner` provisions fresh PVs on the new node.

## Cluster Autoscaler

Both ASGs are tagged at CDK synth time:
```
k8s.io/cluster-autoscaler/enabled = true
k8s.io/cluster-autoscaler/<clusterName> = owned
```

CA scale-write IAM permissions (`SetDesiredCapacity`, `TerminateInstanceInAutoScalingGroup`) are scoped **only** to the monitoring pool role. The CA pod itself runs on the monitoring pool with a matching `nodeSelector`. This prevents a compromised general-pool node from manipulating ASG capacity.

## Idempotency

Each step creates a marker file (e.g., `/etc/kubernetes/.calico-installed`). On re-run, the step checks for the marker and skips if already complete. This makes the entire bootstrap safe to re-run after AMI upgrades or instance replacements.

## Related Pages

- [[k8s-bootstrap-pipeline]] — the project implementing this
- [[calico]] — why a CNI is required
- [[aws-ccm]] — why the cloud controller manager is required
- [[shift-left-validation]] — testing the bootstrap scripts
- [[disaster-recovery]] — control-plane replacement and etcd restore
- [[observability-stack]] — monitoring pool design and PV lifecycle
