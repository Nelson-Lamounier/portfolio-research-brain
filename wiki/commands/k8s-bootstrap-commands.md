---
title: K8s Bootstrap Command Reference
type: command
tags: [devops, commands, just, aws-cli, kubectl, ssm]
sources: [raw/step-function-runtime-logging.md]
created: 2026-04-13
updated: 2026-04-13
---

# K8s Bootstrap Command Reference

All commands for the [[k8s-bootstrap-pipeline]]. Most are [[just]] recipes wrapping AWS CLI calls.

## Deploy Script Testing

```bash
# Offline unit tests (no AWS, < 5s)
just deploy-test admin-api
just deploy-test public-api
just deploy-test nextjs

# Full bootstrap test suite (75 tests)
just bootstrap-pytest

# Specific bootstrap tests
just boot-test-local
just boot-test-local test_ebs_volume.py
just boot-test-local -k "test_chown_and_chmod_applied_to_app_deploy"
```

## S3 Sync

```bash
# Upload single deploy.py to S3 (file mode — 95% of iterations)
just deploy-sync admin-api

# Upload entire chart directory (when helpers changed)
just deploy-sync admin-api development full

# Sync bootstrap scripts to S3
just bootstrap-sync
```

## Interactive Shell

```bash
# Root shell on control-plane EC2 via SSM
just ssm-shell

# Inside the shell — pull and run a script:
aws s3 cp s3://<bucket>/app-deploy/admin-api/deploy.py /data/app-deploy/admin-api/deploy.py --region eu-west-1

# Dry-run (safe, prints config only)
KUBECONFIG=/etc/kubernetes/admin.conf SSM_PREFIX=/k8s/development \
  /opt/k8s-venv/bin/python3 /data/app-deploy/admin-api/deploy.py --dry-run

# Live run (applies K8s resources)
KUBECONFIG=/etc/kubernetes/admin.conf SSM_PREFIX=/k8s/development \
  /opt/k8s-venv/bin/python3 /data/app-deploy/admin-api/deploy.py
```

## SSM Document Trigger

```bash
# Trigger deploy script via real SSM document + CloudWatch tail
just deploy-script admin-api

# Sync then trigger
just deploy-sync admin-api && just deploy-script admin-api
```

## Bootstrap Script Operations

```bash
# Get control-plane instance ID
INSTANCE_ID=$(aws ssm get-parameter \
  --name "/k8s/development/bootstrap/control-plane-instance-id" \
  --region eu-west-1 --profile dev-account \
  --query "Parameter.Value" --output text)

# Pull scripts onto EC2
just bootstrap-pull $INSTANCE_ID

# Dry-run on live instance
just bootstrap-dry-run $INSTANCE_ID

# All-in-one: sync + pull + dry-run
just bootstrap-test $INSTANCE_ID

# Live run (ArgoCD-only Day-2)
just bootstrap-run $INSTANCE_ID
```

## Step Functions

```bash
# Trigger SM-B (all 5 deploy scripts)
just config-run development

# Check SM-B status
just config-status

# Trigger SM-A (full bootstrap) — raw CLI
aws stepfunctions start-execution \
  --state-machine-arn "$SM_A_ARN" \
  --name "manual-test-$(date +%s)" \
  --input '{"detail":{"EC2InstanceId":"'$INSTANCE_ID'","AutoScalingGroupName":"'$ASG_NAME'"}}'
```

## CloudWatch Log Tailing

```bash
# SM-A state transitions
aws logs tail "/aws/vendedlogs/states/k8s-dev-bootstrap-orchestrator" \
  --region eu-west-1 --profile dev-account --follow --format short

# SM-B state transitions
aws logs tail "/aws/vendedlogs/states/k8s-dev-config-orchestrator" \
  --region eu-west-1 --profile dev-account --follow --format short

# Deploy script stdout (all 5 scripts)
aws logs tail "/ssm/k8s/development/deploy" \
  --region eu-west-1 --profile dev-account --follow --format short

# List 5 most recent SSM log streams
aws logs describe-log-streams \
  --log-group-name "/ssm/k8s/development/deploy" \
  --region eu-west-1 --profile dev-account \
  --order-by LastEventTime --descending \
  --query "logStreams[:5].logStreamName" --output table
```

## SSM Debugging

```bash
# View specific SSM command invocation
aws ssm get-command-invocation \
  --command-id "$COMMAND_ID" \
  --instance-id "$INSTANCE_ID" \
  --region eu-west-1 --profile dev-account \
  --query "{Status:Status,Stdout:StandardOutputContent,Stderr:StandardErrorContent}" \
  --output json

# Validate SSM bash preamble
just ssm-preamble-test
```

## CDK Operations

```bash
# Deploy single stack
just deploy-stack SsmAutomation-development kubernetes development

# Diff before deploying
just diff kubernetes development

# List all stacks
just list kubernetes development

# Synth only (validate template)
cd infra && npx cdk synth SsmAutomation-development \
  -c project=kubernetes -c environment=development --profile dev-account
```

## Permissions Fix (Manual)

```bash
# One-time fix on existing cluster
chown -R root:ssm-user /data/app-deploy && chmod -R g+w /data/app-deploy

# Verify permissions
ls -la /data/app-deploy/
ls -la /data/app-deploy/admin-api/
```

## Related Pages

- [[just]] — task runner details
- [[aws-ssm]] — SSM execution model
- [[shift-left-validation]] — the testing workflow these commands implement
- [[ssm-permission-denied]] — permissions troubleshooting
