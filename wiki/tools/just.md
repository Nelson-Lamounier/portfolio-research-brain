---
title: Just (Task Runner)
type: tool
tags: [devops, just, task-runner, developer-experience]
sources: [raw/step-function-runtime-logging.md]
created: 2026-04-13
updated: 2026-04-13
---

# Just (Task Runner)

[Just](https://github.com/casey/just) is the developer CLI interface for the [[k8s-bootstrap-pipeline]]. All workflows are exposed as `just` recipes that encode environment-specific defaults and abstract long AWS CLI invocations.

## Why Just

- Self-documenting via `just --list`
- Recipes encode the same bucket, SSM prefix, and IAM identity as CI — dev/prod parity per the 12-Factor App principle
- Prints human-readable instructions after every step

## Key Recipes

See [[k8s-bootstrap-commands]] for the full command reference.

### Deploy Script Workflows

| Recipe | Purpose |
|--------|---------|
| `just deploy-test <script>` | Run offline unit tests (< 5s) |
| `just deploy-sync <script>` | Upload deploy.py to S3 (file mode, ~10s) |
| `just deploy-sync <script> development full` | Upload entire chart directory |
| `just deploy-script <script>` | Trigger via SSM document + CloudWatch tail |
| `just ssm-shell` | Root interactive session on EC2 |

### Bootstrap Script Workflows

| Recipe | Purpose |
|--------|---------|
| `just boot-test-local` | Offline pytest for bootstrap scripts |
| `just bootstrap-pytest` | Full 75-test suite |
| `just bootstrap-sync` | Sync bootstrap scripts to S3 |
| `just bootstrap-pull $ID` | Pull updated scripts onto EC2 |
| `just bootstrap-dry-run $ID` | Dry-run on live instance |
| `just bootstrap-test $ID` | All-in-one: sync + pull + dry-run |
| `just bootstrap-run $ID` | Live run (ArgoCD-only Day-2) |

### Step Functions & Config

| Recipe | Purpose |
|--------|---------|
| `just config-run development` | Trigger SM-B (all 5 deploy scripts) |
| `just config-status` | Latest SM-B execution ARN + status |

### CDK

| Recipe | Purpose |
|--------|---------|
| `just deploy-stack <stack> kubernetes development` | Deploy single CDK stack |
| `just diff kubernetes development` | CDK diff before deploying |
| `just list kubernetes development` | List all stacks |

## Related Pages

- [[k8s-bootstrap-pipeline]] — project context
- [[k8s-bootstrap-commands]] — full command reference
- [[shift-left-validation]] — the testing philosophy these recipes implement
