---
title: Self-Hosted Kubernetes (kubeadm on EC2)
type: concept
tags: [kubernetes, ec2, kubeadm, self-hosted, architecture]
sources: [raw/step-function-runtime-logging.md]
created: 2026-04-13
updated: 2026-04-13
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

## Control Plane Bootstrap (10 Steps)

| Step | What it does |
|------|-------------|
| 1. AMI validation | Verifies binaries and kernel settings |
| 2. DR restore | Restores etcd from S3 backup if admin.conf missing |
| 3. EBS mount | Formats (first boot) and mounts `/data/` — persists state across replacements |
| 4. kubeadm init | Initializes cluster, creates Route 53 DNS, backs up certs to S3 |
| 5. [[calico]] | Installs CNI via Tigera operator — pods can now be scheduled |
| 5b. [[aws-ccm]] | Installs AWS CCM via Helm — removes cloud provider taint |
| 6. kubectl access | Copies kubeconfig to root, ec2-user, ssm-user |
| 7. S3 sync | Downloads bootstrap manifests |
| 8. [[argocd]] | Installs ArgoCD + App-of-Apps root application |
| 9. Verify | Health checks: nodes Ready, pods healthy, ArgoCD sync |
| 10. etcd backup | Installs hourly systemd timer for S3 etcd snapshots |

## Worker Node Bootstrap (5 Steps)

1. AMI validation (same as control plane)
2. `kubeadm join` — reads join token + CA hash from SSM, handles CA mismatches
3. CloudWatch agent install
4. Stale PVC cleanup (monitoring pool only)
5. Membership verification — confirms node registration and labels

## Idempotency

Each step creates a marker file (e.g., `/etc/kubernetes/.calico-installed`). On re-run, the step checks for the marker and skips if already complete. This makes the entire bootstrap safe to re-run after AMI upgrades or instance replacements.

## Related Pages

- [[k8s-bootstrap-pipeline]] — the project implementing this
- [[calico]] — why a CNI is required
- [[aws-ccm]] — why the cloud controller manager is required
- [[shift-left-validation]] — testing the bootstrap scripts
