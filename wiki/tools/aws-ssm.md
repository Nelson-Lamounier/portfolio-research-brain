---
title: AWS Systems Manager (SSM)
type: tool
tags: [aws, ssm, run-command, session-manager, ec2, security]
sources: [raw/step-function-runtime-logging.md, raw/kubernetes_system_design_review.md]
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

Used as the single source of truth for environment-specific values:

**Bootstrap parameters:**
- `{prefix}/security-group-id` — Cluster SG
- `{prefix}/join-token` — `kubeadm join` token (SecureString)
- `{prefix}/ca-hash` — `kubeadm join` CA hash
- `{prefix}/control-plane-endpoint` — API server hostname:port
- `{prefix}/scripts-bucket` — S3 boot script source
- `{prefix}/golden-ami/latest` — Golden AMI ID

**Runtime parameters:**
- `/k8s/development/bootstrap/control-plane-instance-id` — CP instance ID
- `/k8s/development/bootstrap/state-machine-arn` — SM-A ARN
- `/k8s/development/bootstrap/config-state-machine-arn` — SM-B ARN
- Cognito pool IDs, DynamoDB table names, app secrets

**DR backup parameters (SecureString):**
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
- [[aws-step-functions]] — orchestration layer calling SSM
- [[ssm-permission-denied]] — EBS volume permissions troubleshooting
- [[k8s-bootstrap-commands]] — SSM-related just recipes and CLI commands
- [[disaster-recovery]] — SSM SecureString as secondary backup target for certs and keys
