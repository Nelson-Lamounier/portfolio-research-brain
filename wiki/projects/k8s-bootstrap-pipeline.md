---
title: K8s Bootstrap Pipeline
type: project
tags: [kubernetes, aws, cdk, step-functions, ssm, ec2, self-hosted, devops]
sources: [raw/step-function-runtime-logging.md]
created: 2026-04-13
updated: 2026-04-13
---

# K8s Bootstrap Pipeline

A CDK-managed pipeline that bootstraps self-hosted Kubernetes clusters on EC2 using [[kubeadm]], [[aws-ssm|SSM Run Command]], and [[aws-step-functions|Step Functions]]. No managed Kubernetes (EKS/GKE) — full control-plane and worker node automation via Python scripts.

## Architecture

The system has two orchestration tiers, decoupled by [[event-driven-orchestration|EventBridge]]:

### SM-A — Bootstrap Orchestrator (Tier 1)

Manages cluster infrastructure lifecycle. Runs once per EC2 instance (or replacement):

1. **InvokeRouter Lambda** — reads ASG tags to determine role, SSM prefix, S3 bucket
2. **UpdateInstanceId** — writes instance ID to SSM
3. **BootstrapControlPlane** — runs `control_plane.py` via SSM Run Command (10 steps: AMI validation → DR restore → EBS mount → kubeadm init → [[calico|Calico CNI]] → [[aws-ccm|AWS CCM]] → kubectl access → S3 sync → [[argocd|ArgoCD]] → etcd backup)
4. **Worker rejoin** — parallel `worker.py` execution on general + monitoring pools

### SM-B — Config Orchestrator (Tier 2)

Manages application runtime config. Runs 5 `deploy.py` scripts sequentially on the control plane:

1. `nextjs/deploy.py` — K8s Secrets, ConfigMap, Traefik IngressRoute
2. `monitoring/deploy.py` — Grafana Secret, Prometheus ConfigMap, Helm release
3. `start-admin/deploy.py` — Cognito + DynamoDB + Bedrock config
4. `admin-api/deploy.py` — Secrets, ConfigMap, IngressRoute
5. `public-api/deploy.py` — ConfigMap, IngressRoute

### Self-Healing

SM-A SUCCEED → EventBridge rule → SM-B fires automatically. Any EC2 replacement triggers the full bootstrap → config injection cycle without CI involvement.

## Key Design Decisions

- **[[adr-python-ec2-scripts|Python over Bash/TypeScript]]** for EC2 scripts — unit testability (75 offline pytest tests), idempotency via marker files, structured error handling
- **[[aws-ssm|SSM Run Command over SSH]]** — no keys, no bastion, no port 22, IAM-governed access
- **[[aws-step-functions|Step Functions over Lambda chains]]** — native parallel branches, no 15-min timeout limit, visual debugging console, structured failure handling
- **[[github-actions|GitHub Actions with OIDC]]** — zero infrastructure CI, temporary credentials per run, path-scoped triggers for monorepo

## Testing Workflow

Follows [[shift-left-validation]]:

1. `just deploy-test <script>` — offline unit tests (< 5s)
2. `just deploy-sync <script>` → `just ssm-shell` → `--dry-run` — live node validation (< 30s)
3. `just deploy-script <script>` — SSM document trigger with CloudWatch tail (< 1min)
4. `just config-run development` — full SM-B execution (integration gate)

## Logging

| Layer | Log Group | Retention |
|-------|-----------|-----------|
| SM-A state transitions | `/aws/vendedlogs/states/k8s-dev-bootstrap-orchestrator` | 7 days |
| SM-B state transitions | `/aws/vendedlogs/states/k8s-dev-config-orchestrator` | 7 days |
| Bootstrap script stdout | `/ssm/k8s/development/bootstrap` | 14 days |
| Deploy script stdout | `/ssm/k8s/development/deploy` | 14 days |

## CDK Stacks

| Stack | Purpose |
|-------|---------|
| `SsmAutomation-development` | SSM Documents + Step Functions + IAM |
| `ControlPlane-development` | EC2 control-plane + ASG |
| `GeneralPool-development` | Worker pool ASG |
| `MonitoringPool-development` | Monitoring worker pool |
| `AppIam-development` | IAM roles for pod workloads |

## Related Pages

- [[aws-step-functions]] — orchestration engine
- [[aws-ssm]] — remote execution layer
- [[calico]] — CNI plugin
- [[argocd]] — GitOps controller
- [[shift-left-validation]] — testing philosophy
- [[event-driven-orchestration]] — SM-A → EventBridge → SM-B pattern
- [[ssm-permission-denied]] — /data/app-deploy/ permissions fix
- [[k8s-bootstrap-commands]] — all just recipes and CLI commands
