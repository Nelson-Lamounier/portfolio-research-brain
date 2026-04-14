---
title: Event-Driven Orchestration (SM-A → EventBridge → SM-B)
type: pattern
tags: [aws, step-functions, eventbridge, self-healing, architecture]
sources: [raw/step-function-runtime-logging.md]
created: 2026-04-13
updated: 2026-04-13
---

# Event-Driven Orchestration

The [[k8s-bootstrap-pipeline]] uses a two-state-machine architecture decoupled by EventBridge. This enables self-healing: any EC2 replacement automatically triggers the full bootstrap → config injection cycle without CI involvement.

## The Pattern

```
SM-A (Bootstrap Orchestrator) SUCCEED
    → EventBridge rule fires
        → SM-B (Config Orchestrator) starts automatically
            → 5 deploy.py scripts re-inject secrets/config
```

## Why Decoupled

SM-A manages **cluster infrastructure** (kubeadm, CNI, CCM, ArgoCD). SM-B manages **application runtime config** (K8s Secrets, ConfigMaps, IngressRoutes). These are separate concerns with different:

- Trigger conditions (SM-A: instance launch; SM-B: SM-A success OR manual)
- Failure modes (SM-A failure = no cluster; SM-B failure = cluster running but apps unconfigured)
- Re-run frequency (SM-A: rare; SM-B: on every secret rotation)

## Self-Healing Property

When an EC2 instance is replaced (planned or unplanned):

1. ASG launches new instance from [[self-hosted-kubernetes|Golden AMI]]
2. GHA or EventBridge triggers SM-A
3. SM-A bootstraps the cluster (kubeadm init, Calico, CCM, ArgoCD)
4. SM-A SUCCEED → EventBridge → SM-B fires automatically
5. SM-B injects all 5 application configs
6. Cluster is fully operational — no human intervention

## Manual Triggers

SM-B can also be triggered independently for secret rotation:

```bash
just config-run development    # via just recipe
# or via trigger-config.ts in GHA Phase 6
```

## What SM-A SUCCEED Does NOT Trigger

`just bootstrap-run` (ArgoCD-only Day-2) does **not** emit an EventBridge event. It uses `AWS-RunShellScript` directly, bypassing Step Functions. SM-B will not auto-fire after a `bootstrap-run`.

## Related Pages

- [[k8s-bootstrap-pipeline]] — project implementing this pattern
- [[aws-step-functions]] — SM-A and SM-B definitions
- [[argocd]] — the two execution paths (bootstrap-run vs SM-A)
