---
title: Wiki Index
type: index
updated: 2026-04-14
---

# Knowledge Base Index

## Projects

- [[projects/k8s-bootstrap-pipeline]] — CDK-managed self-hosted Kubernetes bootstrap pipeline on EC2 with Step Functions and SSM

## Concepts

- [[concepts/self-hosted-kubernetes]] — kubeadm on EC2: what managed K8s provides that self-hosted does not, and how bootstrap scripts fill the gap
- [[concepts/shift-left-validation]] — local-first testing philosophy: unit tests (5s) → dry-run (30s) → SSM trigger (1min) → CI pipeline (10min)

## Tools

- [[tools/aws-step-functions]] — orchestration engine for bootstrap (SM-A) and config injection (SM-B) state machines
- [[tools/aws-ssm]] — remote execution layer: Run Command, Session Manager, Parameter Store — replaces SSH entirely
- [[tools/calico]] — Calico CNI via Tigera operator: pod networking and NetworkPolicy enforcement
- [[tools/aws-ccm]] — AWS Cloud Controller Manager: removes cloud provider taint to unblock pod scheduling
- [[tools/argocd]] — GitOps controller: declarative workload management from Git after bootstrap
- [[tools/github-actions]] — CI/CD with OIDC credential federation, custom Docker CI image, path-scoped monorepo triggers
- [[tools/just]] — task runner: developer CLI wrapping all deploy, bootstrap, and CDK workflows

## Patterns

- [[patterns/event-driven-orchestration]] — SM-A SUCCEED → EventBridge → SM-B auto-fires: self-healing config injection
- [[patterns/poll-loop-pattern]] — custom Step Functions poll loop for SSM Run Command completion (no native waiter exists)

## Troubleshooting

- [[troubleshooting/ssm-permission-denied]] — EACCES on /data/app-deploy/ from ssm-shell: root cause (root:root 755) and two-layer fix (group-write + root session)

## Commands

- [[commands/k8s-bootstrap-commands]] — complete command reference: just recipes, AWS CLI, SSM debugging, CDK operations

## Comparisons

- [[comparisons/llm-wiki-vs-bedrock-pipeline]] — LLM Wiki vs Bedrock article pipeline: where each excels, hybrid architecture proposal, 3-phase migration plan
