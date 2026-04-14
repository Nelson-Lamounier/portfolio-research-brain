---
title: Calico CNI
type: tool
tags: [kubernetes, cni, networking, calico, tigera]
sources: [raw/step-function-runtime-logging.md]
created: 2026-04-13
updated: 2026-04-13
---

# Calico CNI

The Container Network Interface (CNI) plugin used in the [[k8s-bootstrap-pipeline]]. Installed as Step 5 of the control plane bootstrap via the Tigera operator.

## Why a CNI Is Required

After `kubeadm init`, the control plane is running but **no pod can be scheduled**. Every node gets the taint `node.kubernetes.io/not-ready` until a CNI is installed.

A CNI provides:

- **Pod IP assignment** from the pod CIDR (`192.168.0.0/16`)
- **Cross-node pod routing** — traffic between pods on different nodes
- **NetworkPolicy enforcement** — namespace and service isolation

Without a CNI: CoreDNS stays `Pending`, kubeadm cannot confirm readiness, nothing follows.

## Why Calico Specifically

| Requirement | How Calico satisfies it |
|-------------|------------------------|
| NetworkPolicy support | Native, not bolted on |
| Works on EC2 without BGP peering | VXLAN encapsulation mode routes pod traffic without L3 routing config in AWS |
| Managed via K8s operator | Tigera operator — declarative, upgradeable via `kubectl apply` |
| PodDisruptionBudgets | Calico DaemonSets tolerate rolling updates without network loss |
| Resource-bounded | Explicit CPU/memory requests prevent starving app pods on small nodes |

## Installation in the Bootstrap

The `calico.py` step:

1. Applies the Tigera operator manifest
2. Waits for the `Installation` custom resource to reach `Available`
3. Applies PodDisruptionBudget manifests (`system/calico-pdbs.yaml`) for node drain protection

Uses a marker file (`/etc/kubernetes/.calico-installed`) for [[idempotency]].

## Related Pages

- [[self-hosted-kubernetes]] — why a CNI is needed after kubeadm init
- [[k8s-bootstrap-pipeline]] — project using Calico
- [[aws-ccm]] — the other critical post-kubeadm component
