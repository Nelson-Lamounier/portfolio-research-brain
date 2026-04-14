---
title: AWS Systems Manager (SSM)
type: tool
tags: [aws, ssm, run-command, session-manager, ec2, security]
sources: [raw/step-function-runtime-logging.md, raw/kubernetes_system_design_review.md, raw/base-stack-review.md]
created: 2026-04-13
updated: 2026-04-14
---

# AWS Systems Manager (SSM)

The remote execution layer for the [[k8s-bootstrap-pipeline]]. All script execution on EC2 uses SSM Run Command — no SSH, no Ansible, no bastion host.

## SSM Run Command vs SSH

| Concern | SSH | SSM Run Command |
|---|---|---|
| Key management | Key pair distributed to every machine/dev | None — IAM-governed |
| Network access | Port 22 open, bastion/VPN required | No ports, no bastion |
| Audit trail | Manual setup | CloudWatch by default |
| Credential rotation | Manual key rotation when engineers leave | Automatic via IAM |

SSM requires only: the SSM agent (pre-installed on Amazon Linux 2023) + an IAM instance profile with `ssm:SendCommand` permission.

## SSM over `Fn::ImportValue` for Cross-Stack Dependencies

All inter-stack dependencies in the [[k8s-bootstrap-pipeline]] are resolved at runtime via SSM Parameter Store rather than CloudFormation `Fn::ImportValue`. The pattern:

1. Stack A writes its output to SSM at deploy time
2. Stack B reads the SSM parameter at EC2 instance boot time (not synth time)

**Why this matters:**
- Stacks deploy in any order — no CloudFormation dependency graph to satisfy
- A stack can be deleted and recreated without breaking stacks that depend on it
- SSM values can be updated at runtime (e.g., new instance ID after ASG replacement) without a CloudFormation update

The worker stack reads ~10 SSM parameters at synth time for CDK constructs, and the bootstrap Python scripts read additional parameters at runtime.

## SSM Documents in This Project

| Document | Purpose | Orchestrated by |
|---|---|---|
| `k8s-dev-bootstrap-runner` | Tier 1 bootstrap scripts (`control_plane.py`, `worker.py`) | SM-A |
| `k8s-dev-deploy-runner` | Tier 2 deploy scripts (5× `deploy.py`) | SM-B |
| `AWS-RunShellScript` | Ad-hoc script execution (e.g., `just bootstrap-run`) | Manual |
| `AWS-StartInteractiveCommand` | Root interactive session (`just ssm-shell`) | Manual |

## SSM Session Manager (Interactive Shell)

```bash
just ssm-shell
```

Opens a root bash session via `AWS-StartInteractiveCommand` with `sudo su -`. The SSM agent handles privilege escalation — no sudoers configuration needed.

## SSM Parameter Store

Used as the single source of truth for environment-specific values. All paths use the prefix `/k8s/{environment}`.

### BaseStack Outputs (14 parameters)

Published by `KubernetesBaseStack` at deploy time. See [[cdk-kubernetes-stacks]] for the full stack context.

| SSM Parameter Path | Value Source | Consumed By |
|---|---|---|
| `/k8s/{env}/vpc-id` | VPC lookup | Control Plane, Worker, Edge, Observability |
| `/k8s/{env}/elastic-ip` | EIP address | Edge stack (CloudFront origin) |
| `/k8s/{env}/elastic-ip-allocation-id` | EIP allocation ID | NLB subnet mapping |
| `/k8s/{env}/security-group-id` | Cluster base SG ID | Control Plane + Worker (node SG) |
| `/k8s/{env}/control-plane-sg-id` | Control plane SG ID | Control Plane stack |
| `/k8s/{env}/ingress-sg-id` | Ingress SG ID | Control Plane + Worker stacks |
| `/k8s/{env}/monitoring-sg-id` | Monitoring SG ID | Worker ASG stack (monitoring pool) |
| `/k8s/{env}/scripts-bucket` | S3 bucket name | CI pipeline, user-data scripts |
| `/k8s/{env}/hosted-zone-id` | Route 53 zone ID | Control Plane (user-data updates A record) |
| `/k8s/{env}/api-dns-name` | `k8s-api.k8s.internal` | Control Plane (`kubeadm --control-plane-endpoint`) |
| `/k8s/{env}/kms-key-arn` | KMS key ARN | Observability stack (CloudWatch log encryption) |
| `/k8s/{env}/nlb-full-name` | NLB full name | CloudWatch metrics (NLB target health dashboards) |
| `/k8s/{env}/nlb-http-target-group-arn` | NLB HTTP TG ARN | Worker ASG stack (both pools register) |
| `/k8s/{env}/nlb-https-target-group-arn` | NLB HTTPS TG ARN | Worker ASG stack (both pools register) |

### Bootstrap parameters (published by control_plane.py at runtime)

- `/k8s/{env}/join-token` — `kubeadm join` token (SecureString)
- `/k8s/{env}/ca-hash` — `kubeadm join` CA hash
- `/k8s/{env}/control-plane-endpoint` — API server hostname:port
- `/k8s/{env}/control-plane-instance-id` — CP instance ID
- `/k8s/{env}/prometheus-basic-auth` — Prometheus credentials
- `/k8s/{env}/cloudfront-origin-secret` — `X-Origin-Verify` header value

### Runtime parameters (published by SsmAutomation stack)

- `/k8s/{env}/bootstrap/state-machine-arn` — SM-A ARN
- `/k8s/{env}/bootstrap/config-state-machine-arn` — SM-B ARN
- `/k8s/{env}/bootstrap/control-plane-doc-name` — SSM document name
- Cognito pool IDs, DynamoDB table names, app secrets

### DR backup parameters (SecureString)

- `{prefix}/tls-cert` — Traefik `ops-tls-cert`
- `{prefix}/argocd-jwt-key` — ArgoCD JWT signing key
- `{prefix}/argocd-admin-password` — ArgoCD admin password
- `{prefix}/github-deploy-key` — SSH deploy key for ArgoCD repo access

Deploy scripts bridge SSM → Kubernetes Secrets/ConfigMaps at runtime.

## SSM Bash Preamble

Every SSM document execution starts with:

```bash
set -exo pipefail
export HOME="${HOME:-/root}"
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH"
```

The `-u` (`nounset`) flag was intentionally removed — non-login SSM shells may not have `$HOME` set.

## CloudWatch Output

SSM stdout/stderr is routed via `CloudWatchOutputConfig` in the `sendCommand` call:

| Log Group | Content |
|---|---|
| `/ssm/k8s/development/bootstrap` | Tier 1 script output (14-day retention) |
| `/ssm/k8s/development/deploy` | Tier 2 script output (14-day retention) |

## Python Environment

The Golden AMI pre-installs a Python venv at `/opt/k8s-venv/` with `boto3`, `pyyaml`. The SSM document prepends `/opt/k8s-venv/bin` to `$PATH`. In interactive `ssm-shell`, use `/opt/k8s-venv/bin/python3` explicitly — bare `python3` resolves to the system interpreter without `boto3`.

## Related Pages

- [[k8s-bootstrap-pipeline]] — project using SSM
- [[cdk-kubernetes-stacks]] — full 14-parameter BaseStack SSM output table
- [[aws-step-functions]] — orchestration layer calling SSM
- [[ssm-permission-denied]] — EBS volume permissions troubleshooting
- [[k8s-bootstrap-commands]] — SSM-related just recipes and CLI commands
- [[disaster-recovery]] — SSM SecureString as secondary backup target for certs and keys
