---
title: AWS Cloud Controller Manager (CCM)
type: tool
tags: [aws, kubernetes, ccm, cloud-controller-manager, ec2]
sources: [raw/step-function-runtime-logging.md]
created: 2026-04-13
updated: 2026-04-13
---

# AWS Cloud Controller Manager (CCM)

Installed as Step 5b of the [[k8s-bootstrap-pipeline]] control plane bootstrap. Removes the cloud provider taint that blocks all pod scheduling on EC2 nodes.

## The Problem It Solves

After `kubeadm init`, every EC2 node gets the taint:

```
node.cloudprovider.kubernetes.io/uninitialized
```

This taint blocks **all** pod scheduling — including CoreDNS, [[argocd|ArgoCD]], and [[calico|Calico]] operator pods. The taint exists because Kubernetes knows it's running on a cloud provider but hasn't verified the node's cloud identity.

## What the CCM Does

1. Calls the EC2 API to verify instance identity (via IMDS)
2. Sets `spec.providerID` (`aws:///eu-west-1a/i-0abc123`) on the node object
3. Removes the `uninitialized` taint so pods can be scheduled

Without the CCM, the cluster is created but immediately non-functional.

## Installation

The `ccm.py` step:

1. Installs the CCM via Helm
2. Waits up to 120 seconds for the taint to be removed
3. [[argocd|ArgoCD]] later adopts the Helm release and manages future upgrades declaratively

## Related Pages

- [[calico]] — the other critical post-kubeadm component (CNI)
- [[self-hosted-kubernetes]] — full bootstrap sequence
- [[k8s-bootstrap-pipeline]] — project context
