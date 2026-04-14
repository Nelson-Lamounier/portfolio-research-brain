---
title: AWS EBS CSI Driver
type: tool
tags: [kubernetes, aws, ebs, storage, csi, persistent-volumes]
sources: [raw/base-stack-review.md]
created: 2026-04-14
updated: 2026-04-14
---

# AWS EBS CSI Driver

The cluster's primary dynamic storage provisioner. Deployed and managed by [[argocd]] at **Sync Wave 4** (after core platform, before monitoring workloads). Replaced the `local-path` StorageClass in March 2026 to eliminate permanent data loss on monitoring node replacement.

## Component Topology

| Component | Kind | Runs On | Responsibility |
|---|---|---|---|
| `ebs-csi-controller` | `Deployment` (1 replica) | Control-plane node | `CreateVolume`, `DeleteVolume`, `AttachVolume`, `DetachVolume` RPCs |
| `ebs-csi-node` | `DaemonSet` | **Every node** (CP + all workers) | `NodeStageVolume`, `NodePublishVolume` — mounts the EBS volume into the pod's filesystem |

Because `ebs-csi-node` runs on **every** node, all instance roles — both `K8sControlPlaneStack` and `KubernetesWorkerAsgStack` — must carry the `EbsCsiDriverVolumeLifecycle` + `EbsCsiDriverKms` IAM policies. This is not duplication; it is an architectural requirement.

## `ebs-sc` StorageClass

```yaml
name: ebs-sc
annotations:
  storageclass.kubernetes.io/is-default-class: "true"
parameters:
  type: gp3
  encrypted: "true"
reclaimPolicy: Delete
volumeBindingMode: WaitForFirstConsumer
allowVolumeExpansion: true
```

**`WaitForFirstConsumer`** is the key parameter. It delays EBS volume creation until a Pod is scheduled, ensuring the volume is created in the **same AZ as the Pod**. Without this, volumes can end up in a different AZ from the node, causing an unresolvable attachment failure.

## PersistentVolumes (Monitoring Stack)

All stateful monitoring workloads run on the monitoring pool and use `ebs-sc`:

| Workload | PVC Size (dev) | StorageClass | Update Strategy |
|---|---|---|---|
| Prometheus | 10 Gi | `ebs-sc` | `Recreate` |
| Grafana | 10 Gi | `ebs-sc` | `Recreate` |
| Loki | 10 Gi | `ebs-sc` | `Recreate` |
| Tempo | 10 Gi | `ebs-sc` | `Recreate` |

**`Recreate` update strategy** (not `RollingUpdate`) prevents RWO (`ReadWriteOnce`) PVC deadlocks. Because only one pod can hold the volume mount at a time, a rolling update would block the new pod waiting for the old pod to release the volume.

## Stale PV Cleanup on Node Replacement

When the monitoring pool Spot instance is replaced:

1. The old PV has `nodeAffinity` bound to the terminated instance's hostname
2. A new instance appears at a different private IP / hostname
3. The PV cannot be reattached (cross-AZ or stale node binding)

`worker.py` on the new monitoring node detects this at Step 4 of the bootstrap sequence: calls `kubectl delete pv` for orphaned PVs, allowing ArgoCD to recreate PVCs with fresh volumes on the new node. See [[self-hosted-kubernetes]] for the full worker bootstrap sequence.

## Migration from `local-path` (2026-03-31)

Prior to this migration, monitoring PVs used the `local-path` StorageClass which bound volumes to the specific node's local disk. **Every Spot interruption caused permanent data loss and pod deadlocks** — the pod would be scheduled on the new node but find its local-path PV pointing to the dead node's filesystem.

The migration to `ebs-sc` resolved this by switching to network-attached EBS volumes that survive node replacement. The archived runbook is at `knowledge-base/kubernetes/runbooks/local-path-orphaned-pvcs.md` in the project repo.

## IAM Requirements

All nodes require these policies for EBS CSI to function:

| Permission | Service | Reason |
|---|---|---|
| `ec2:CreateVolume`, `DeleteVolume`, `AttachVolume`, `DetachVolume`, `ModifyVolume` | EC2 | CSI controller operations |
| `ec2:CreateSnapshot`, `DeleteSnapshot`, `DescribeSnapshots`, `CreateTags` | EC2 | Volume snapshot support |
| `kms:Decrypt`, `Encrypt`, `ReEncrypt*`, `GenerateDataKey*`, `CreateGrant`, `DescribeKey` | KMS | Encrypted GP3 volume operations |

## Related Pages

- [[observability-stack]] — monitoring workloads using EBS CSI PVs
- [[self-hosted-kubernetes]] — worker pool design; stale PV cleanup in boot sequence
- [[argocd]] — manages EBS CSI deployment at Sync Wave 4
- [[disaster-recovery]] — PV cleanup on monitoring node replacement
- [[cdk-kubernetes-stacks]] — IAM policies in control-plane and worker stacks
