---
title: AWS Systems Manager (SSM)
type: tool
tags: [aws, ssm, run-command, session-manager, ec2, security]
sources: [raw/step-function-runtime-logging.md]
created: 2026-04-13
updated: 2026-04-13
---

# AWS Systems Manager (SSM)

The remote execution layer for the [[k8s-bootstrap-pipeline]]. All script execution on EC2 uses SSM Run Command — no SSH, no Ansible, no bastion host.

## SSM Run Command vs SSH

| Concern | SSH | SSM Run Command |
|---------|-----|-----------------|
| Key management | Key pair distributed to every machine/dev | None — IAM-governed |
| Network access | Port 22 open, bastion/VPN required | No ports, no bastion |
| Audit trail | Manual setup | CloudWatch by default |
| Credential rotation | Manual key rotation when engineers leave | Automatic via IAM |

SSM requires only: the SSM agent (pre-installed on Amazon Linux 2023) + an IAM instance profile with `ssm:SendCommand` permission.

## SSM Documents in This Project

| Document | Purpose | Orchestrated by |
|----------|---------|-----------------|
| `k8s-dev-bootstrap-runner` | Tier 1 bootstrap scripts (`control_plane.py`, `worker.py`) | SM-A |
| `k8s-dev-deploy-runner` | Tier 2 deploy scripts (5x `deploy.py`) | SM-B |
| `AWS-RunShellScript` | Ad-hoc script execution (e.g., `just bootstrap-run`) | Manual |
| `AWS-StartInteractiveCommand` | Root interactive session (`just ssm-shell`) | Manual |

## SSM Session Manager (Interactive Shell)

```bash
just ssm-shell
```

Opens a root bash session via `AWS-StartInteractiveCommand` with `sudo su -`. The SSM agent handles privilege escalation — no sudoers configuration needed.

## SSM Parameter Store

Used as the single source of truth for environment-specific values:

- `/k8s/development/bootstrap/control-plane-instance-id` — CP instance ID
- `/k8s/development/bootstrap/state-machine-arn` — SM-A ARN
- `/k8s/development/bootstrap/config-state-machine-arn` — SM-B ARN
- `/k8s/development/scripts-bucket` — S3 bucket name
- Cognito pool IDs, DynamoDB table names, app secrets

Deploy scripts bridge SSM → Kubernetes Secrets/ConfigMaps.

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
|-----------|---------|
| `/ssm/k8s/development/bootstrap` | Tier 1 script output (14-day retention) |
| `/ssm/k8s/development/deploy` | Tier 2 script output (14-day retention) |

## Python Environment

The Golden AMI pre-installs a Python venv at `/opt/k8s-venv/` with `boto3`, `pyyaml`. The SSM document prepends `/opt/k8s-venv/bin` to `$PATH`. In interactive `ssm-shell`, use `/opt/k8s-venv/bin/python3` explicitly — bare `python3` resolves to the system interpreter without `boto3`.

## Related Pages

- [[k8s-bootstrap-pipeline]] — project using SSM
- [[aws-step-functions]] — orchestration layer calling SSM
- [[ssm-permission-denied]] — EBS volume permissions troubleshooting
- [[k8s-bootstrap-commands]] — SSM-related just recipes and CLI commands
