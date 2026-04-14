---
title: Wiki Index
type: index
updated: 2026-04-14

---

# Knowledge Base Index

## Projects

- [[projects/k8s-bootstrap-pipeline]] — CDK-managed self-hosted Kubernetes bootstrap pipeline on EC2 with Step Functions, SSM, and full cluster topology for `nelsonlamounier.com`

## Concepts

- [[concepts/self-hosted-kubernetes]] — kubeadm on EC2: cluster topology (both pools t3.medium), KubernetesWorkerAsgStack v2, bootstrap steps, CA mismatch, stale PV cleanup
- [[concepts/cluster-networking]] — VPC topology (single AZ), 4-tier Security Groups, NLB over ALB, Calico VXLAN/VXLANAlways, SourceDestCheck, /26 IPAM, end-to-end traffic flows
- [[concepts/shift-left-validation]] — local-first testing philosophy: unit tests (5s) → dry-run (30s) → SSM trigger (1min) → CI pipeline (10min)
- [[concepts/self-healing-agent]] — AI-driven remediation: CloudWatch Alarm → EventBridge → Lambda → Bedrock ConverseCommand loop → MCP → SNS
- [[concepts/observability-stack]] — LGTM + Promtail DaemonSet + Alloy Faro/RUM + 13 GitOps dashboards; 12-job Prometheus scrape inventory; Tempo span-metrics for DynamoDB; Grafana alerting via SNS; known limitations (single-AZ, Spot, Faro CORS)
- [[concepts/disaster-recovery]] — etcd + PKI backup to S3, TLS and JWT to SSM, _reconstruct_control_plane DR path, RTO ~5–8 min; kube-proxy/CoreDNS addon guards on second-run path
- [[concepts/cdk-kubernetes-stacks]] — full 10-stack CDK catalogue with deployment order, lifecycle separation, config-driven SG pattern, KubernetesWorkerAsgStack v2 (3→2 stacks, CA tags, zero-downtime migration)

## Tools

- [[tools/aws-step-functions]] — orchestration engine for SM-A/SM-B; 3600s timeout story; Node Drift Enforcement; ResourceCleanupProvider
- [[tools/aws-ssm]] — remote execution layer: Run Command, Session Manager, 14-param BaseStack outputs, DR SecureStrings
- [[tools/aws-cloudfront]] — CloudFront + WAF + ACM edge stack: TLS model, X-Origin-Verify, cross-region SSM read pattern
- [[tools/aws-ebs-csi]] — EBS CSI Driver: controller/node topology, ebs-sc StorageClass, WaitForFirstConsumer, local-path migration
- [[tools/ec2-image-builder]] — Golden AMI pipeline: pre-baked K8s toolchain, bootstrap time from 15 min → 2–3 min
- [[tools/calico]] — Calico CNI via Tigera operator: pod networking, VXLANAlways encapsulation (VXLANCrossSubnet fails on single-subnet AWS), SourceDestCheck, /26 IPAM, NetworkPolicy dual-ipBlock for hostNetwork
- [[tools/aws-ccm]] — AWS Cloud Controller Manager: removes cloud provider taint to unblock pod scheduling
- [[tools/argocd]] — GitOps controller: 7-wave sync map, ApplicationSet, multi-source Apps, bootstrap sequence
- [[tools/traefik]] — DaemonSet + hostNetwork ingress: IngressRoute ownership boundary, secret rotation, priority cascade
- [[tools/argo-rollouts]] — Blue/Green: scalar() analysis fix, HPA targeting Rollout, ResourceQuota formula, deployment testing workflow, start-admin :latest tag bug
- [[tools/crossplane]] — Kubernetes-native IDP: EncryptedBucket/MonitoredQueue XRDs, golden-path service provisioning
- [[tools/steampipe]] — Cloud inventory SQL FDW in monitoring namespace: Grafana datasource, cloud-inventory dashboard, exec queries, SQL pitfalls
- [[tools/promtail]] — Log shipping DaemonSet: kubernetes-pods + journal scrape jobs, CRI parsing, Loki push, Loki→Tempo TraceID derived fields
- [[tools/hono]] — Hono/Node.js API services: public-api (port 3001) and admin-api (port 3002) with IMDS credentials
- [[tools/github-actions]] — CI/CD with OIDC credential federation, custom Docker CI image, path-scoped monorepo triggers
- [[tools/just]] — task runner: developer CLI wrapping all deploy, bootstrap, and CDK workflows

## Patterns

- [[patterns/event-driven-orchestration]] — SM-A SUCCEED → EventBridge → SM-B auto-fires: self-healing config injection
- [[patterns/poll-loop-pattern]] — custom Step Functions poll loop for SSM Run Command completion (no native waiter exists)
- [[patterns/bff-pattern]] — Backend-for-Frontend: start-admin calls admin-api pod-to-pod; browser never crosses origin to admin-api

## Troubleshooting

- [[troubleshooting/ssm-permission-denied]] — EACCES on /data/app-deploy/ from ssm-shell: root cause (root:root 755) and two-layer fix (group-write + root session)
- [[troubleshooting/prometheus-scrape-targets]] — 6 real scrape failures (relabel bug, 404s, redirect loop, missing jobs, replicas:0); sub-path prefix reference table; ephemeral curl pod diagnostics
- [[troubleshooting/cross-node-networking]] — 10-step Calico diagnostic: VXLANCrossSubnet vs VXLANAlways root cause, routing table patterns, VXLAN packet capture, NetworkPolicy testing
- [[troubleshooting/kube-proxy-missing-after-dr]] — DR gap: S3 restore skips kubeadm init → kube-proxy/CoreDNS never deployed → ClusterIP broken; ensure_kube_proxy + ensure_coredns guards; manual recovery
- [[troubleshooting/nextjs-image-asset-sync]] — content-hash build alignment, 6 issues (404s, Image Updater IAM, self-heal reverts, start-admin :latest bug, CloudFront invalidation, IfNotPresent); ArgoCD parameter override pattern

## Commands

- [[commands/k8s-bootstrap-commands]] — complete command reference: just recipes, AWS CLI, SSM debugging, CDK operations
- [[commands/kubectl-operations]] — day-2 operations: get/describe/exec/rollout/logs, BlueGreen testing, Traefik connectivity, networking diagnostics, ArgoCD workflow, JSONPath reference

## Comparisons

- [[comparisons/llm-wiki-vs-bedrock-pipeline]] — LLM Wiki vs Bedrock article pipeline: where each excels, hybrid architecture proposal, 3-phase migration plan
