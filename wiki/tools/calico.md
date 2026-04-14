---
title: Calico CNI
type: tool
tags: [kubernetes, cni, networking, calico, tigera, vxlan]
sources: [raw/step-function-runtime-logging.md, raw/kubernetes_app_review.md, raw/cross-node-networking-troubleshooting.md, raw/kubernetes_networking_report.md]
created: 2026-04-13
updated: 2026-04-14
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

## Encapsulation: VXLANAlways (Not VXLANCrossSubnet)

All cluster nodes reside in a **single AWS subnet**. This makes encapsulation mode selection critical.

| Mode | Behaviour | AWS Single-Subnet |
|---|---|---|
| `VXLANAlways` | All cross-node traffic VXLAN-encapsulated | ✅ Required |
| `VXLANCrossSubnet` | Same-subnet nodes use direct routing | ❌ Fails silently |
| `None` | Direct routing only | ❌ Always fails |

**Why `VXLANCrossSubnet` fails:** In single-subnet deployments, Calico treats all nodes as "same subnet" and routes pod-to-pod traffic directly — sending packets with pod IPs (`192.168.x.x`) onto the VPC. The VPC has no routes for pod CIDRs and silently drops the packets, even with `SourceDestCheck` disabled.

**Why VXLAN uses UDP:** Encapsulating TCP inside TCP causes TCP Meltdown — exponential congestion from double retransmission under packet loss. UDP is a stateless wrapper; the inner TCP handles reliability independently.

### Route Table Signatures

```bash
ip route | grep 192.168
```

**VXLANAlways (correct):**
```
192.168.101.0/26 via 192.168.101.0 dev vxlan.calico onlink   ← ✅
```

**VXLANCrossSubnet (broken on single subnet):**
```
192.168.101.0/26 via 10.0.0.160 dev ens5   ← ❌ Direct routing
```

Routes via `ens5` instead of `vxlan.calico` confirm the wrong mode.

### IPAM: /26 Blocks Per Node

Pod IPs are assigned from `192.168.0.0/16`. Each node gets a `/26` block (62 pod capacity). Felix (Calico's per-node agent) programs routes, iptables rules, and the VXLAN Forwarding Database for all known blocks.

### SourceDestCheck

AWS EC2's `SourceDestCheck` must be `false` on all cluster nodes. When enabled, the hypervisor drops packets whose source/dest IPs don't match the ENI — which includes all pod IPs. Disabled via `disableSourceDestCheck: true` in the CDK `LaunchTemplate`.

### Persistent Fix Location

```python
# kubernetes-app/k8s-bootstrap/boot/steps/03_install_calico.py
spec:
  calicoNetwork:
    ipPools:
      - cidr: 192.168.0.0/16
        encapsulation: VXLANAlways    # NOT VXLANCrossSubnet
        natOutgoing: Enabled
        nodeSelector: all()
```

Also in `infra/lib/common/compute/builders/user-data-builder.ts` (CDK user-data fallback).

For the full 10-step cross-node diagnostic guide, see [[cross-node-networking]].

## NetworkPolicy: Dual ipBlock for Traefik hostNetwork

Because [[traefik]] runs with `hostNetwork: true`, it appears to other pods as the **node's IP address**, not a pod IP. Standard `namespaceSelector` NetworkPolicy rules cannot match it.

Every workload's `NetworkPolicy` needs two separate `ipBlock` ingress rules to allow Traefik traffic:

```yaml
ingress:
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
```

Without both rules, pods that receive traffic forwarded from a node on the other side of a VXLAN tunnel would have their packets dropped by Calico's NetworkPolicy enforcement.

## Related Pages

- [[self-hosted-kubernetes]] — why a CNI is needed after kubeadm init
- [[k8s-bootstrap-pipeline]] — project using Calico
- [[cluster-networking]] — full VPC + VXLAN + SG architecture
- [[cross-node-networking]] — 10-step diagnostic guide for cross-node failures
- [[traefik]] — DaemonSet hostNetwork design that requires dual ipBlock
- [[helm-chart-architecture]] — NetworkPolicy template in workload charts
- [[aws-ccm]] — the other critical post-kubeadm component
