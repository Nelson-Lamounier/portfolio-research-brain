---
title: Concept-to-Resume Mapping
type: resume
tags: [resume, language, mapping, devops, kubernetes, ai-engineering]
sources: [raw/kubernetes_infrastructure_audit_16_04.md]
created: 2026-04-16
updated: 2026-04-16
---

# Concept-to-Resume Mapping

Implementation detail → job application language. Use this when a job description mentions a technology or concept — look up how it maps to what was actually built. Do NOT invent claims not present in the source wiki page.

## Infrastructure & Cloud

| What Was Built | Wiki Page | Resume Language | Honesty Boundary |
|---|---|---|---|
| 10-stack CDK architecture | [[cdk-kubernetes-stacks]] | "Designed multi-stack CDK IaC with lifecycle-separated stacks" | Portfolio, not enterprise-scale |
| SSM Parameter Store cross-stack | [[aws-ssm]] | "Implemented service discovery via SSM Parameter Store, decoupling stack dependencies" | 14 params, one environment |
| CloudFront + WAF + ACM edge stack | [[aws-cloudfront]] | "Built CDN edge layer with WAF, ACM cert rotation, origin verification" | Portfolio traffic volume |
| EC2 Image Builder pipeline | [[ec2-image-builder]] | "Implemented Golden AMI pipeline reducing EC2 boot time 75%" | Single pipeline, single region |
| EBS CSI Driver | [[aws-ebs-csi]] | "Configured EBS CSI with StorageClass, WaitForFirstConsumer" | No multi-AZ (single-AZ cluster) |
| VPC topology + security groups | [[concepts/cluster-networking]] | "Designed 4-tier security group model with defence-in-depth" | Single-AZ, single-region |
| Spot instances + ASG | [[cdk-kubernetes-stacks]] | "Right-sized worker pools on Spot (60–70% cost reduction vs. On-Demand)" | t3.small/medium, not large-scale |

## Kubernetes

| What Was Built | Wiki Page | Resume Language | Honesty Boundary |
|---|---|---|---|
| kubeadm bootstrap | [[concepts/self-hosted-kubernetes]] | "Bootstrapped self-managed Kubernetes clusters (kubeadm) on AWS EC2" | Not EKS — deliberate choice |
| Calico CNI | [[tools/calico]] | "Configured Calico CNI with VXLANAlways encapsulation for cross-node networking" | Single-subnet AWS (VXLANCrossSubnet doesn't work) |
| AWS CCM | [[tools/aws-ccm]] | "Integrated AWS Cloud Controller Manager for node lifecycle management" | Standard kubeadm integration |
| etcd backup + DR | [[disaster-recovery]] | "Implemented etcd + PKI backup to S3, control-plane reconstruction in ~5–8 min RTO" | Solo ops, no SLA |
| ArgoCD GitOps | [[tools/argocd]] | "Managed 9 Helm charts via ArgoCD (7-wave sync, ApplicationSet, multi-source apps)" | Portfolio workloads |
| Argo Rollouts Blue/Green | [[tools/argo-rollouts]] | "Implemented Blue/Green deployment strategy with HPA targeting and analysis runs" | Portfolio apps only |
| Traefik ingress | [[tools/traefik]] | "Configured Traefik DaemonSet as hostNetwork ingress with priority routing and secret rotation" | Single-node DaemonSet |
| Crossplane | [[tools/crossplane]] | "Implemented Kubernetes-native IDP with Crossplane XRDs for golden-path provisioning" | Dev environment, XRDs only |

## CI/CD & GitOps

| What Was Built | Wiki Page | Resume Language | Honesty Boundary |
|---|---|---|---|
| 26-workflow GitHub Actions monorepo | [[ci-cd-pipeline-architecture]] | "Designed 26-workflow monorepo CI/CD with reusable workflow library" | Solo-authored, not team process |
| OIDC + AROA masking | [[tools/github-actions]] | "Implemented OIDC-based AWS authentication with AROA masking for secret-less CI" | Standard GitHub OIDC pattern |
| sha-rAttempt image tags | [[ci-cd-pipeline-architecture]] | "Enforced immutable image tags (sha-rAttempt) for full deployment traceability" | Portfolio CI, not enterprise registry |
| Custom CI Docker image | [[ci-cd-pipeline-architecture]] | "Built custom CI container (Node.js, AWS CLI, just, Python) eliminating ~3 min/run" | Single image |
| `just` task runner | [[tools/just]] | "Standardised local-CI parity via `just` task runner — identical logic locally and in pipeline" | 6 recipe groups |
| Checkov + CDK-NAG | [[tools/checkov]] | "Automated IaC security scanning with 10 custom rules, severity-gated pipeline" | 10 custom rules (5 IAM + 5 SG) |

## Observability

| What Was Built | Wiki Page | Resume Language | Honesty Boundary |
|---|---|---|---|
| LGTM stack on Kubernetes | [[observability-stack]] | "Deployed full LGTM observability stack (Loki, Grafana, Tempo, Mimir/Prometheus) on self-managed K8s" | In-cluster, single-AZ |
| 13 Grafana dashboards (GitOps) | [[observability-stack]] | "Managed 13 Grafana dashboards as code via GitOps" | Portfolio dashboards |
| Promtail DaemonSet | [[tools/promtail]] | "Configured Promtail DaemonSet for Kubernetes pod + systemd journal log shipping to Loki" | Standard DaemonSet config |
| OTel instrumentation | [[tools/nextjs]] | "Instrumented Next.js application with OpenTelemetry SDK (instrumentation.ts hook)" | Single app |
| Faro RUM + log proxy | [[tools/nextjs]] | "Integrated Grafana Faro RUM via /log-proxy Next.js rewrite to avoid CORS" | Portfolio traffic |
| prom-client metrics | [[tools/nextjs]] | "Exposed Prometheus metrics endpoint (/api/metrics) with custom application metrics" | Single app |
| Steampipe SQL FDW | [[tools/steampipe]] | "Deployed Steampipe as cloud inventory SQL datasource for Grafana" | Dev/portfolio environment |
| Dual-layer CloudWatch + K8s | [[observability-stack]] | "Implemented dual-layer observability: CloudWatch (pre-deploy) + K8s-native (post-deploy)" | Two CloudWatch dashboards |

## Security

| What Was Built | Wiki Page | Resume Language | Honesty Boundary |
|---|---|---|---|
| Least-privilege IAM (conditional grants) | [[cdk-kubernetes-stacks]] | "Implemented conditional IAM grant pattern — permissions are no-op when props absent" | Single environment |
| KMS encryption (logs, S3, SQS) | [[cdk-kubernetes-stacks]] | "Enforced encryption at rest via KMS across CloudWatch Logs, S3, SQS" | One KMS key |
| NLB + CloudFront prefix list | [[concepts/cluster-networking]] | "Restricted NLB HTTP to CloudFront origin IPs via AWS Managed Prefix List" | Standard pattern |
| Zero-downtime origin secret rotation | [[aws-cloudfront]] | "Implemented zero-downtime TLS origin secret rotation via Traefik regex dual-validation" | Single secret |
| SSM-only access (no SSH) | [[aws-ssm]] | "Eliminated SSH attack surface — all EC2 access via SSM Session Manager" | Standard SSM pattern |
| Worker pool IAM segregation | [[concepts/cluster-networking]] | "Segregated worker pool IAM — general nodes lack Cluster Autoscaler write permissions" | Two pools only |

## AI Engineering

| What Was Built | Wiki Page | Resume Language | Honesty Boundary |
|---|---|---|---|
| ConverseCommand agentic loop | [[tools/aws-bedrock]] | "Implemented self-managed ConverseCommand tool-use loop with MCP Gateway integration" | Portfolio system |
| Extended Thinking (adaptive) | [[ai-engineering/inference-time-techniques]] | "Applied adaptive Extended Thinking (2K–16K token budget) via complexity signal scoring" | Bedrock API only, no fine-tuning |
| Bedrock Guardrails | [[tools/aws-bedrock]] | "Configured Bedrock Guardrails: content filters, topic denial, contextual grounding (0.7)" | Portfolio chatbot |
| KB RetrieveCommand | [[tools/aws-bedrock]] | "Integrated Bedrock Knowledge Base via explicit RetrieveCommand for context injection" | Pinecone + S3 source |
| S3 episodic memory | [[ai-engineering/self-healing-agent]] | "Implemented S3-backed episodic session memory for cross-invocation self-refinement" | Simple key-value, no vector store |
| Prompt caching | [[tools/aws-bedrock]] | "Implemented Bedrock prompt caching achieving ~90% cost reduction on Writer Lambda" | Single pipeline |
| Application Inference Profiles | [[tools/aws-bedrock]] | "Used Bedrock Application Inference Profiles for FinOps cost attribution per system" | Dev account |
| MCP tools via AgentCore | [[ai-engineering/self-healing-agent]] | "Integrated 6 MCP tools via AgentCore Gateway with Cognito M2M authentication" | Portfolio agent, DRY_RUN=true by default |

## Related Pages

- [[achievements]] — the numbers behind these mappings
- [[gap-awareness]] — what to NOT claim
- [[role-archetypes]] — which mappings to emphasise per role
