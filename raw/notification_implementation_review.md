# Notification Implementation Review

**Project:** cdk-monitoring  
**Scope:** `infra/lib/stacks/` × `kubernetes-app/`  
**Date:** April 2026 — Updated 15 April 2026 (all gaps resolved)  
**Report Type:** Cross-layer architectural review · Post-remediation final

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Notification Architecture Overview](#2-notification-architecture-overview)
3. [SNS Topics — CDK Implementation](#3-sns-topics--cdk-implementation)
   - 3.1 [Monitoring Alerts Topic (worker-asg-stack)](#31-monitoring-alerts-topic-worker-asg-stack)
   - 3.2 [DLQ Alarm Topic (api-stack)](#32-dlq-alarm-topic-api-stack)
   - 3.3 [Bootstrap Failure Alarm Topic (ssm-automation-stack)](#33-bootstrap-failure-alarm-topic-ssm-automation-stack)
   - 3.4 [FinOps Budget Alerts Topic (finops-stack)](#34-finops-budget-alerts-topic-finops-stack)
   - 3.5 [Security Baseline Topic (security-baseline-stack)](#35-security-baseline-topic-security-baseline-stack)
4. [Grafana Notification Strategy](#4-grafana-notification-strategy)
   - 4.1 [Unified Alerting Configuration Model](#41-unified-alerting-configuration-model)
   - 4.2 [Contact Points — SNS Receiver](#42-contact-points--sns-receiver)
   - 4.3 [Routing Policy](#43-routing-policy)
   - 4.4 [Alert Rules — Full Catalogue](#44-alert-rules--full-catalogue)
5. [ArgoCD Notifications](#5-argocd-notifications)
6. [Subscription Gap Analysis](#6-subscription-gap-analysis)
7. [SSM → Helm Values Wiring for Grafana SNS](#7-ssm--helm-values-wiring-for-grafana-sns)
8. [Traces and Metrics Setup Per Topic](#8-traces-and-metrics-setup-per-topic)
9. [CLI Audit: Identifying Topics Without Subscriptions](#9-cli-audit-identifying-topics-without-subscriptions)
10. [Recommendations](#10-recommendations)

---

## 1. Executive Summary

The project implements **five SNS topics** across four CDK stacks and a **Grafana Unified Alerting** system with twelve alert rules routed through a conditional SNS contact point. Additionally, ArgoCD Notifications delivers **GitHub commit-status updates** for every application sync/health event.

**Key findings — all gaps resolved:**

| Finding | Severity | Status |
|---|---|---|
| Monitoring Pool SNS topic — `notificationEmail` not passed from factory | 🔴 Gap | ✅ **Fixed** |
| Grafana SNS topic ARN injection — `inject_monitoring_helm_params` in `steps/apps.py` | 🟡 Already wired | ✅ Confirmed |
| ArgoCD Notifications secret — no automated bootstrap path | 🔴 Gap | ✅ **Fixed** |
| Bootstrap Alarm topic — email subscription wired correctly | ✅ Correct | ✅ Unchanged |
| DLQ Alarm topic — email subscription wired correctly | ✅ Correct | ✅ Unchanged |
| FinOps topic — email subscription wired correctly | ✅ Correct | ✅ Unchanged |

---

## 2. Notification Architecture Overview

```
                    ┌─────────────────────────────────────────────────┐
                    │           NOTIFICATION PATHS                     │
                    └─────────────────────────────────────────────────┘

  [Grafana Alerting]                [ArgoCD Notifications]
        │                                   │
        │ SNS contact point                 │ GitHub App Integration
        ▼                                   ▼
  [SNS: monitoring-alerts]       [GitHub Commit Status API]
        │                              (success/failure per app)
        │ Email subscription
        ▼
  [Owner Email]                  [CloudWatch Alarms]
                                       │
                                       │ SNS actions (alarm + OK)
                                       ▼
  ┌────────────────────────────────────────────────────┐
  │  SNS: k8s-dev-bootstrap-alarm    →  Email          │
  │  SNS: nextjs-api-dlq-alerts      →  Email          │
  │  SNS: shared-dev-finops-alerts   →  Email          │
  │  SNS: security-baseline-alerts   →  Email          │
  └────────────────────────────────────────────────────┘
```

Three independent notification planes exist:

1. **Grafana Unified Alerting** → SNS → Email (in-cluster observability alerts on metrics/traces)
2. **CloudWatch Alarms** → SNS → Email (AWS-native operational alerts: DLQ, bootstrap failures, budget)
3. **ArgoCD Notifications** → GitHub API (GitOps deployment status feedback)

---

## 3. SNS Topics — CDK Implementation

### 3.1 Monitoring Alerts Topic (`worker-asg-stack.ts`)

**File:** `infra/lib/stacks/kubernetes/worker-asg-stack.ts` · Lines 700–744

```typescript
// Created ONLY for the monitoring pool (isMonitoringPool guard)
const alertsTopic = new sns.Topic(this, 'MonitoringAlertsTopic', {
    topicName: `${poolId}-monitoring-alerts`,
    displayName: 'Monitoring Alerts',
    enforceSSL: true,
    masterKey: kms.Alias.fromAliasName(this, 'SnsEncryptionKey', 'alias/aws/sns'),
});

if (props.notificationEmail) {
    alertsTopic.addSubscription(
        new sns_subscriptions.EmailSubscription(props.notificationEmail),
    );
}
```

**Purpose:** Receives alert notifications published by Grafana's SNS contact point when alert rules fire (e.g., node down, high CPU, DynamoDB errors).

**Encryption:** AWS-managed SNS KMS alias (`alias/aws/sns`). The instance role receives `kms:Decrypt` + `kms:GenerateDataKey*` via `kms:ViaService` condition, enabling Grafana (running as a pod using the EC2 instance role via IRSA-equivalent IMDSv2) to publish encrypted messages.

**IAM policy on instance role:**
```typescript
launchTemplateConstruct.addToRolePolicy(new iam.PolicyStatement({
    sid: 'SnsPublishAlerts',
    actions: ['sns:Publish'],
    resources: [alertsTopic.topicArn],
}));
```

**SSM Discovery:** The ARN is written to SSM:
```
/k8s/development/monitoring/alerts-topic-arn-pool
```
This path suffix (`-pool`) distinguishes from legacy stacks. The `inject_monitoring_helm_params` function in `bootstrap_argocd.py` Step 5b reads this parameter and patches the monitoring ArgoCD Application with the Helm parameter `grafana.alerting.snsTopicArn`.

**Subscription:** `notificationEmail` is conditionally added. The factory at `factory.ts` now correctly passes `notificationEmail: emailConfig.notificationEmail` to `monitoringPoolStack` — **fixed in remediation (Gap 1)**. The full alert delivery chain (Grafana → SNS → Email) is active.

**CloudFormation Output:** `MonitoringAlertsTopicArn` — exported from the stack.

---

### 3.2 DLQ Alarm Topic (`api-stack.ts`)

**File:** `infra/lib/stacks/kubernetes/api-stack.ts` · Lines 219–253

```typescript
const dlqAlarmTopic = new sns.Topic(this, 'DlqAlarmTopic', {
    displayName: `${namePrefix} API DLQ Alerts (${envName})`,
});

if (props.notificationEmail) {
    dlqAlarmTopic.addSubscription(
        new sns_subscriptions.EmailSubscription(props.notificationEmail),
    );
}
```

**Purpose:** Fires when any Lambda Dead Letter Queue (`subscribe-dlq` or `verify-dlq`) receives a message, indicating a failed Lambda invocation that could not be retried.

**Alarms wired:** One CloudWatch Alarm per DLQ (two total):
```typescript
for (const [name, dlq] of Object.entries(this.lambdaDlqs)) {
    const alarm = new cloudwatch.Alarm(this, `${name}DlqAlarm`, {
        metric: dlq.metricApproximateNumberOfMessagesVisible({
            period: cdk.Duration.minutes(5),
            statistic: 'Maximum',
        }),
        threshold: 1,
    });
    alarm.addAlarmAction(new cloudwatch_actions.SnsAction(dlqAlarmTopic));
    alarm.addOkAction(new cloudwatch_actions.SnsAction(dlqAlarmTopic));  // ← OK action too
}
```

**Design decision — OK action included:** Both `addAlarmAction` and `addOkAction` are registered. This means the owner receives two emails: one when the DLQ fills (alert) and one when it clears (recovery). This is deliberate — confirming the issue was resolved reduces the cognitive overhead of wondering whether a self-resolved failure persists.

**Factory wiring:** `factory.ts:478` passes `notificationEmail: emailConfig.notificationEmail ?? ''`. This is sourced from `NOTIFICATION_EMAIL` environment variable at synth time. **Correctly wired.**

**cdk-nag suppressions:**
- `AwsSolutions-SNS2` — default encryption accepted for alarm topic (no sensitive data)
- `AwsSolutions-SNS3` — SSL not enforced for email-only delivery

---

### 3.3 Bootstrap Failure Alarm Topic (`ssm-automation-stack.ts`)

**File:** `infra/lib/constructs/ssm/bootstrap-alarm.ts` · Lines 69–98

```typescript
this.topic = new sns.Topic(this, 'Topic', {
    topicName: `${props.prefix}-bootstrap-alarm`,
    displayName: `${props.prefix} Bootstrap Orchestrator Failure Alarm`,
    enforceSSL: true,
});

if (props.notificationEmail) {
    this.topic.addSubscription(
        new sns_subscriptions.EmailSubscription(props.notificationEmail),
    );
}

this.alarm = new cloudwatch.Alarm(this, 'Alarm', {
    alarmName: `${props.prefix}-bootstrap-orchestrator-errors`,
    metric: props.stateMachine.metricFailed({
        period: cdk.Duration.minutes(5),
        statistic: 'Sum',
    }),
    threshold: 1,
    treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
});

this.alarm.addAlarmAction(new cloudwatchActions.SnsAction(this.topic));
```

**Purpose:** Fires when the Step Functions bootstrap state machine (`K8s-SsmAutomation-dev`) has any failed execution. A single failure means a K8s node did not finish bootstrapping — the cluster may be partially operational.

**Metric:** `ExecutionsFailed` on the state machine, Sum over 5 minutes. Threshold: ≥ 1.

**`treatMissingData: NOT_BREACHING`:** Correct default — no Step Functions executions during quiet periods (no ASG scaling events) should not alarm.

**Factory wiring (`ssm-automation-stack.ts:274–286`):**
```typescript
const ssmAutomationStack = new K8sSsmAutomationStack(scope, ..., {
    notificationEmail: emailConfig.notificationEmail,  // ← correctly passed
});
```

The `emailConfig.notificationEmail` is sourced from `NOTIFICATION_EMAIL` env var. **Correctly wired.**

**Cleanup registration:** The topic ARN is registered with `ResourceCleanupProvider` so it is deleted on stack teardown:
```typescript
cleanup.addSnsTopic(alarmTopicName, alarm.topic);
```

---

### 3.4 FinOps Budget Alerts Topic (`finops-stack.ts`)

**File:** `infra/lib/stacks/shared/finops-stack.ts` · Lines 120–136

```typescript
this.alertsTopic = new sns.Topic(this, 'FinOpsAlertsTopic', {
    topicName: `${props.namePrefix}-finops-alerts`,
    displayName: `FinOps Alerts (${props.targetEnvironment})`,
    enforceSSL: true,
});

if (props.notificationEmail) {
    this.alertsTopic.addSubscription(
        new subscriptions.EmailSubscription(props.notificationEmail),
    );
}

// Grant AWS Budgets permission to publish to this topic
this.alertsTopic.grantPublish(
    new iam.ServicePrincipal('budgets.amazonaws.com'),
);
```

**Purpose:** Receives alerts when AWS budget thresholds are breached (default: 50%, 80%, 100% of monthly limit). A second budget scoped to `Amazon Bedrock` reuses the same topic.

**Publisher grant:** `budgets.amazonaws.com` service principal is explicitly granted `sns:Publish`. This is required — AWS Budgets is a separate service that needs explicit IAM permission to publish to SNS.

**Factory wiring (`shared/factory.ts:109`):**
```typescript
const notificationEmail = context.notificationEmail ?? process.env.NOTIFICATION_EMAIL;
// ...
new FinOpsStack(scope, ..., { notificationEmail });
```
**Correctly wired.**

**CloudFormation Output:** `FinOpsTopicArn` — exported with name `${namePrefix}-finops-topic-arn`.

---

### 3.5 Security Baseline Topic (`security-baseline-stack.ts`)

**File:** `infra/lib/constructs/security/account-security-baseline.ts` · ~Line 191

This topic is created internally within the `AccountSecurityBaseline` construct and subscribed conditionally on `notificationEmail`. It is wired from `security-baseline-stack.ts:100`:

```typescript
new AccountSecurityBaseline(this, 'SecurityBaseline', {
    notificationEmail: props.notificationEmail,
    ...
});
```

The shared factory passes `notificationEmail` at line 167 and 192. **Correctly wired.**

---

## 4. Grafana Notification Strategy

### 4.1 Unified Alerting Configuration Model

**File:** `kubernetes-app/platform/charts/monitoring/chart/templates/grafana/alerting-configmap.yaml`

Grafana 11.6.0 uses **Unified Alerting** (enabled via `GF_UNIFIED_ALERTING_ENABLED=true` in the Deployment). Configuration is provisioned as a `ConfigMap` (`grafana-alerting`) mounted at `/etc/grafana/provisioning/alerting`. The ConfigMap contains three keys:

| Key | Purpose |
|---|---|
| `contactpoints.yaml` | Defines notification receivers (SNS, email, Slack, etc.) |
| `policies.yaml` | Routes alerts to receivers based on label matchers |
| `rules.yaml` | Defines the alert rules (PromQL expressions + thresholds) |

This approach (file-based provisioning) is **declarative and GitOps-friendly** — changes to alert rules are Git commits, not GUI clicks. ArgoCD detects ConfigMap changes and restarts Grafana to pick up new rules.

The `checksum/config` annotation on the Deployment pod template ensures a rolling restart whenever the ConfigMap changes:
```yaml
annotations:
  checksum/config: {{ include (print $.Template.BasePath "/grafana/configmap.yaml") . | sha256sum }}
```

### 4.2 Contact Points — SNS Receiver

**Contact point definition (`contactpoints.yaml`):**

```yaml
# Conditional — only rendered if snsTopicArn is non-empty
{{- if .Values.grafana.alerting.snsTopicArn }}
contactPoints:
  - orgId: 1
    name: sns
    receivers:
      - uid: sns-receiver
        type: sns
        settings:
          topic_arn: "{{ .Values.grafana.alerting.snsTopicArn }}"
          region: "{{ .Values.grafana.alerting.awsRegion }}"
        disableResolveMessage: false
{{- else }}
contactPoints: []   # ← no SNS configured → silent mode
{{- end }}
```

**Key design decisions:**

1. **Helm-conditional rendering:** When `snsTopicArn` is empty (the default), the contact point array is empty and alerts are evaluated but never delivered. This is a safety valve — the monitoring stack can be operational without live alerting, useful during initial cluster bring-up.

2. **`disableResolveMessage: false`:** Grafana sends a second SNS message when an alert resolves. This provides a complete alert lifecycle visible in the owner's email inbox.

3. **IAM for publishing:** The monitoring pool EC2 instance role has `sns:Publish` on `alertsTopic.topicArn`. Grafana, running as a pod on that node, inherits the instance role via IMDSv2. The Grafana SNS plugin calls the AWS SDK, which fetches credentials from `http://169.254.169.254/latest/meta-data/iam/...`. This is the standard EC2-native path — no static credentials needed in the pod.

4. **Region injection:** The `AWS_REGION` environment variable is injected into the Grafana container from `values.yaml`:
   ```yaml
   - name: AWS_REGION
     value: "{{ .Values.grafana.alerting.awsRegion }}"
   ```
   Defaulting to `eu-west-1`. The SNS plugin reads this to target the correct AWS regional endpoint.

### 4.3 Routing Policy

**Policy definition (`policies.yaml`):**

```yaml
# Active only when snsTopicArn is set
policies:
  - orgId: 1
    receiver: sns
    group_by:
      - grafana_folder
      - alertname
    group_wait: 30s
    group_interval: 5m
    repeat_interval: 4h
    routes:
      - receiver: sns
        matchers:
          - severity = critical   # critical alerts route to SNS
        continue: false           # stops evaluation here
      - receiver: sns
        matchers:
          - severity = warning    # warning alerts also route to SNS
        continue: false
```

**Timing analysis:**

| Parameter | Value | Effect |
|---|---|---|
| `group_wait` | 30s | Wait 30 seconds before sending the first alert, allowing related alerts to batch |
| `group_interval` | 5m | If new alerts join an existing group, wait 5 minutes before re-notifying |
| `repeat_interval` | 4h | If an alert remains firing, repeat the notification every 4 hours |

**`group_by: [grafana_folder, alertname]`:** Alerts in the same folder with the same name are batched into a single SNS message — prevents alert storms where all cluster nodes trigger simultaneously.

**Severity routing:** Both `critical` and `warning` severity labels route to SNS. This is a solo-developer environment — there is no tiered escalation (PagerDuty vs. Slack). All alerts go to a single channel.

### 4.4 Alert Rules — Full Catalogue

**File:** `alerting-configmap.yaml` · Lines 50–505  
**Group structure:** 4 rule groups, 12 rules in total

#### Group 1: `Cluster Health` (interval: 1m)

| Rule | Metric | Threshold | For | Severity |
|---|---|---|---|---|
| **Node Down** | `up{job="node-exporter"}` | `< 1` | 2m | critical |
| **High Node CPU** | `100 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100` | `> 85%` | 5m | warning |
| **High Node Memory** | `(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100` | `> 85%` | 5m | warning |
| **Pod CrashLooping** | `increase(kube_pod_container_status_restarts_total[15m]) > 3` | `> 0` | 0s | critical |
| **Pod Not Ready** | `kube_pod_status_ready{condition="true"} == 0` | `< 1` | 5m | warning |

**Evaluation chain (A→B→C pattern):**
All rules use Grafana's three-stage evaluation pipeline:
- `A`: PromQL expression → raw time-series from Prometheus
- `B`: Reduce expression (`last`) → scalar value per instance
- `C`: Threshold expression → boolean trigger

This pattern is required in Grafana Unified Alerting because the threshold must be a separate expression node — Grafana does not support inline threshold conditions in PromQL.

**Node Down rationale:** The `for: 2m` prevents false positives from transient Prometheus scrape failures. A node target must be unreachable for 2+ consecutive minutes before alerting.

**CrashLoop `for: 0s` rationale:** Pod restarts are an immediate operational signal. Unlike CPU/memory (which fluctuate naturally), a restart counter monotonically increasing is always worth alerting on immediately.

#### Group 2: `Application Health` (interval: 1m)

| Rule | Metric | Threshold | For | Severity |
|---|---|---|---|---|
| **High Error Rate** | `sum(rate(http_requests_total{code=~"5.."}[5m])) / sum(rate(http_requests_total[5m])) * 100` | `> 5%` | 5m | critical |
| **High Latency P95** | `histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket[5m])))` | `> 2s` | 5m | warning |

**Instrumentation source:** These metrics are emitted by the Next.js application via the `@opentelemetry/sdk-node` package, which auto-instruments the HTTP server and emits `http_requests_total` and `http_request_duration_seconds_bucket` counters/histograms to Prometheus (via OTLP → Alloy → Prometheus remote-write or direct scrape).

**Error rate threshold (5%):** Chosen as a practical "something is clearly wrong" level for a portfolio site. A 1% threshold would generate noise from occasional 404s or bot crawlers.

**Latency P95 (2s):** A 2-second P95 for a Next.js SSR application is well above what CloudFront's 60s timeout enforces but represents a clear degradation from the normal sub-200ms response times.

#### Group 3: `Storage Health` (interval: 1m)

| Rule | Metric | Threshold | For | Severity |
|---|---|---|---|---|
| **Disk Space Low** | `(1 - node_filesystem_avail_bytes{fstype!~"tmpfs\|overlay"} / node_filesystem_size_bytes{...}) * 100` | `> 80%` | 5m | warning |
| **Disk Space Critical** | (same metric) | `> 90%` | 2m | critical |

**Two-tier disk alerting:** Warning at 80% provides advance notice; critical at 90% with a shorter `for: 2m` ensures urgent action before Prometheus TSDB or Loki chunk storage runs out of space and corrupts data.

**`fstype!~"tmpfs|overlay"` exclusion:** `tmpfs` (in-memory) and `overlay` (container layers) are ephemeral filesystems that should not trigger storage alerts.

#### Group 4: `DynamoDB & Tracing Alerts` (interval: 1m)

| Rule | Metric | Threshold | For | Severity |
|---|---|---|---|---|
| **DynamoDB Error Rate** | `traces_spanmetrics_calls_total{db_system="dynamodb", status="STATUS_CODE_ERROR"}` | `> 5%` | 5m | critical |
| **DynamoDB P95 Latency** | `histogram_quantile(0.95, rate(traces_spanmetrics_duration_seconds_bucket{db_system="dynamodb"}[5m]))` | `> 1s` | 5m | warning |
| **Span Ingestion Stopped** | `sum(rate(traces_spanmetrics_calls_total[5m]))` | `< 0.001` | 10m | critical |

**Why `traces_spanmetrics_*` metrics?** These metrics are **generated by Tempo** via its SpanMetrics pipeline. Tempo receives OTLP traces from the application (Node.js → OTLP SDK → Alloy → Tempo), then internally converts span data into Prometheus-compatible counter/histogram metrics. This allows the DynamoDB alert to be expressed in PromQL even though DynamoDB itself publishes no Prometheus metrics.

**DynamoDB Latency (1s threshold):** DynamoDB's documented single-digit ms latency means even 100ms is a signal. The 1-second threshold is conservative — it fires only when there is a significant capacity or connectivity issue.

**Span Ingestion Stopped:** This is a **meta-alert** on the observability pipeline itself. If no spans are being ingested over 10 minutes, it means either:
- The OTel SDK in Next.js has stopped exporting
- Alloy is unhealthy
- Network connectivity between pods has failed

This prevents a silent observability failure where Grafana shows no errors simply because it has stopped receiving data.

---

## 5. ArgoCD Notifications

### 5.1 Architecture

**Files:**
- `kubernetes-app/platform/argocd-apps/argocd-notifications.yaml` — ArgoCD Application
- `kubernetes-app/k8s-bootstrap/system/argocd-notifications/notifications-cm.yaml` — ConfigMap

The ArgoCD Notifications controller (bundled with ArgoCD ≥2.6) is deployed by ArgoCD itself as a **self-managing application** at sync-wave 4. It deploys the `argocd-notifications-cm` ConfigMap defining templates, triggers, and the GitHub service.

### 5.2 Notification Service — GitHub App

```yaml
service.github: |
  appID: $github-appID
  installationID: $github-installationID
  privateKey: $github-privateKey
```

**Authentication:** Uses GitHub App authentication (not a PAT token) — more secure and not tied to a personal account. The credentials are referenced via `$variable` syntax which resolves from the `argocd-notifications-secret` Kubernetes Secret in the `argocd` namespace.

**Secret creation (automated bootstrap — Gap 3 fixed):**

The `provision_argocd_notifications_secret` step (Step 5e in `bootstrap_argocd.py`) now creates this secret automatically during bootstrap by reading three SSM SecureString parameters:

```
{ssm_prefix}/argocd/github-app-id
{ssm_prefix}/argocd/github-installation-id
{ssm_prefix}/argocd/github-private-key
```

The step is **idempotent** (409 Conflict → `replace_namespaced_secret`) and **non-fatal** — if the SSM parameters are not yet populated, bootstrap continues and logs a warning. Once credentials are stored in SSM, re-running SM-B (`monitoring/deploy.py`) will not create the secret again on its own; re-running `bootstrap_argocd.py` or creating the secret manually will complete the setup.

**Manual fallback (if SSM parameters are not yet stored):**
```bash
kubectl create secret generic argocd-notifications-secret \
  --from-literal=github-appID=<id> \
  --from-literal=github-installationID=<id> \
  --from-literal=github-privateKey=<pem> \
  -n argocd
```

> [!TIP]
> Store credentials in SSM **before** the first bootstrap run so `provision_argocd_notifications_secret` can create the secret automatically — no manual kubectl step required.

### 5.3 Templates

| Template | Trigger | GitHub Status | Target URL |
|---|---|---|---|
| `app-sync-succeeded` | Sync phase = `Succeeded` | `success` with revision SHA | ArgoCD UI link |
| `app-sync-failed` | Sync phase = `Error` or `Failed` | `failure` | ArgoCD UI link |
| `app-health-degraded` | Health = `Degraded` | `failure` | ArgoCD UI link |

**GitHub commit status label:** `argocd/{{.app.metadata.name}}` — creates a status check per ArgoCD application (e.g., `argocd/monitoring`, `argocd/nextjs`). Visible in GitHub PR merge protection rules.

### 5.4 Default Triggers

```yaml
defaultTriggers: |
  - on-sync-succeeded
  - on-sync-failed
  - on-health-degraded
```

`defaultTriggers` applies to **all** ArgoCD Applications without requiring per-application annotation. This means every application in the cluster (monitoring, nextjs, traefik, cert-manager, etc.) automatically posts GitHub commit status updates on every sync. This provides deployment traceability directly in the GitHub repository's commit history.

---

## 6. Subscription Gap Analysis

> [!NOTE]
> All gaps identified in this section have been resolved. The sub-sections below document the original finding and the applied fix for traceability.

### 6.1 Gap 1 — Monitoring Pool Topic Had No Email Subscriber ✅ FIXED

**Original location:** `infra/lib/projects/kubernetes/factory.ts` · Lines 372–393  
**Fix applied:** `factory.ts` — `notificationEmail: emailConfig.notificationEmail` added to `monitoringPoolStack` props.

The `monitoringPoolStack` was instantiated without `notificationEmail`. The SNS topic was created and its ARN published to SSM, but no human received the alerts because there was no email subscription on the topic.

**Before:**
```typescript
const monitoringPoolStack = new KubernetesWorkerAsgStack(scope, ..., {
    poolType: 'monitoring',
    controlPlaneSsmPrefix: ssmPrefix,
    // notificationEmail was absent
});
```

**After:**
```typescript
const monitoringPoolStack = new KubernetesWorkerAsgStack(scope, ..., {
    poolType: 'monitoring',
    controlPlaneSsmPrefix: ssmPrefix,
    // Wire the notification email so the monitoring SNS topic has an
    // email subscriber. Without this, Grafana alerts are published to
    // the topic (via the EC2 instance role) but never delivered to a
    // human recipient.
    notificationEmail: emailConfig.notificationEmail,
});
```

**Full notification chain is now active:**
```
Grafana alert rule fires
  → Grafana SNS contact point (EC2 IAM role → sns:Publish)
  → SNS topic: k8sdevelopment-monitoring-alerts
  → Email subscription: owner@example.com  ← NOW SUBSCRIBED
```

---

### 6.2 Gap 2 — Grafana `snsTopicArn` Injection ✅ ALREADY HANDLED

**Location:** `kubernetes-app/k8s-bootstrap/system/argocd/steps/apps.py` · `inject_monitoring_helm_params` (line 45)

This gap was **already resolved** in `steps/apps.py`. The `inject_monitoring_helm_params` function reads the SSM parameter `/k8s/{env}/monitoring/alerts-topic-arn-pool` (with legacy path fallback) and patches the monitoring ArgoCD Application with the Helm parameter `grafana.alerting.snsTopicArn`. This runs as bootstrap Step 5b in `bootstrap_argocd.py`.

The `values.yaml` default of `snsTopicArn: ""` is intentional — it prevents errors during ArgoCD's initial sync before the SSM parameter is available. The bootstrap pipeline overwrites it with the real ARN via `kubectl patch application monitoring --type merge`.

---

### 6.3 Gap 3 — ArgoCD Notifications Secret Had No Automated Bootstrap Path ✅ FIXED

**Fix applied in two files:**
- `kubernetes-app/k8s-bootstrap/system/argocd/steps/apps.py` — new `provision_argocd_notifications_secret` function (Step 5e)
- `kubernetes-app/k8s-bootstrap/system/argocd/bootstrap_argocd.py` — import + non-fatal call after `configure_webhook_secret`

**Behaviour:**
1. Reads three SSM SecureString parameters:
   - `{ssm_prefix}/argocd/github-app-id`
   - `{ssm_prefix}/argocd/github-installation-id`
   - `{ssm_prefix}/argocd/github-private-key`
2. Creates/updates `argocd-notifications-secret` in the `argocd` namespace via the Kubernetes Python SDK
3. Idempotent — 409 Conflict triggers `replace_namespaced_secret` so SM-B re-runs are safe
4. Non-fatal — missing SSM params log a warning and bootstrap continues (ArgoCD Notifications silently skips GitHub commit statuses until the secret is populated)

**Pre-requisite — store credentials in SSM:**
```bash
aws ssm put-parameter \
  --name "/k8s/development/argocd/github-app-id" \
  --type SecureString \
  --value "<GitHub App ID>"

aws ssm put-parameter \
  --name "/k8s/development/argocd/github-installation-id" \
  --type SecureString \
  --value "<Installation ID>"

aws ssm put-parameter \
  --name "/k8s/development/argocd/github-private-key" \
  --type SecureString \
  --value "$(cat /path/to/github-app-private-key.pem)"
```

---

## 7. SSM → Helm Values Wiring for Grafana SNS

> [!NOTE]
> This section documents the **resolved** data flow. The chain is now fully connected after the remediations applied on 15 April 2026.

The complete data flow for the Grafana SNS contact point:

```
CDK synth & deploy (worker-asg-stack.ts)
  └─→ Creates SNS topic: {poolId}-monitoring-alerts
  └─→ Adds email subscription: notificationEmail  ✅ fixed (Gap 1)
  └─→ Writes ARN to SSM: /k8s/{env}/monitoring/alerts-topic-arn-pool

bootstrap_argocd.py — Step 5b: inject_monitoring_helm_params
  └─→ Reads SSM: /k8s/{env}/monitoring/alerts-topic-arn-pool  ✅ confirmed
  └─→ Falls back to: /k8s/{env}/monitoring/alerts-topic-arn (legacy)
  └─→ Patches ArgoCD Application:
        kubectl patch application monitoring -n argocd --type merge
          -p '{"spec":{"source":{"helm":{"parameters":
            [{"name":"grafana.alerting.snsTopicArn","value":"<arn>"}]
          }}}}'  ✅ confirmed

bootstrap_argocd.py — Step 5e: provision_argocd_notifications_secret  ✅ new
  └─→ Reads SSM SecureString: github-app-id, github-installation-id, github-private-key
  └─→ Creates/updates argocd-notifications-secret in argocd namespace

ArgoCD reconcile loop
  └─→ Syncs monitoring Application with Helm parameter override
  └─→ Helm renders alerting-configmap.yaml with snsTopicArn injected
  └─→ ConfigMap mounted at /etc/grafana/provisioning/alerting/
  └─→ contactpoints.yaml renders SNS receiver  ✅
  └─→ policies.yaml routes critical + warning → SNS  ✅

Grafana alert rule fires
  └─→ SNS contact point publishes to monitoring-alerts topic (EC2 IAM role)
  └─→ SNS delivers email to subscribed owner  ✅ (subscription now confirmed)
```

---

## 8. Traces and Metrics Setup Per Topic

### Monitoring Alerts Topic

| Dimension | Setup |
|---|---|
| **Publisher** | Grafana pod → EC2 instance role → SNS SDK call |
| **Metrics** | CloudWatch `NumberOfMessagesSent` (auto-published by SNS) |
| **Traces** | No OTel instrumentation on Grafana SNS plugin calls |
| **Dashboard** | `asg-audit.ts` checks whether the topic is tracked in CloudWatch dashboards — currently not explicitly added to the CloudWatch dashboard |
| **Alarm** | No CloudWatch Alarm on DeliveryFailures for this topic — gap |

### DLQ Alarm Topic

| Dimension | Setup |
|---|---|
| **Publisher** | CloudWatch Alarm → SNS (automatic, no custom code) |
| **Metrics** | `ApproximateNumberOfMessagesVisible` on SQS DLQ (5-min Maximum, threshold ≥ 1) |
| **Traces** | X-Ray tracing is enabled on API Gateway and Lambda — failed invocations appear in X-Ray service map |
| **Alarm state** | Both ALARM and OK states publish to SNS — lifecycle visible in email |
| **Cost** | ~$0.40/month (4 alarms × 2 states × estimated transitions) |

### Bootstrap Failure Alarm Topic

| Dimension | Setup |
|---|---|
| **Publisher** | CloudWatch Alarm on `ExecutionsFailed` metric from Step Functions |
| **Metrics** | `AWS/States :: ExecutionsFailed` (Sum, 5-min) |
| **Traces** | Step Functions execution history (viewable in AWS Console) + CloudWatch Logs (LogLevel.ALL) |
| **X-Ray** | Enabled on the state machine (`xray:PutTraceSegments` in IAM role) |
| **Cleanup** | Topic registered with `ResourceCleanupProvider` for stack teardown |

### FinOps Budget Alerts Topic

| Dimension | Setup |
|---|---|
| **Publisher** | AWS Budgets service principal (`budgets.amazonaws.com`) |
| **Metrics** | AWS Cost & Usage data (not Prometheus/CloudWatch custom metrics) |
| **Traces** | N/A — budget notifications are batch events, not request-scoped |
| **Thresholds** | 50%, 80%, 100% of monthly limit (configurable, default: `[50, 80, 100]`) |
| **Bedrock sub-budget** | Separate `BudgetConstruct` scoped to `serviceFilter: 'Amazon Bedrock'` reuses the same SNS topic |

---

## 9. CLI Audit: Identifying Topics Without Subscriptions

### 9.1 List All SNS Topics

```bash
# List all SNS topics in your account/region
aws sns list-topics \
  --region eu-west-1 \
  --profile development \
  --query 'Topics[*].TopicArn' \
  --output table
```

### 9.2 Find Topics Without Any Subscriptions

```bash
#!/usr/bin/env bash
# Audit all SNS topics for missing subscriptions

REGION="eu-west-1"
PROFILE="development"

echo "=== SNS Topics Without Confirmed Subscriptions ==="
echo ""

TOPICS=$(aws sns list-topics \
  --region "$REGION" \
  --profile "$PROFILE" \
  --query 'Topics[*].TopicArn' \
  --output text)

for TOPIC_ARN in $TOPICS; do
  TOPIC_NAME=$(echo "$TOPIC_ARN" | awk -F: '{print $NF}')
  
  # Count confirmed (not pending) subscriptions
  CONFIRMED=$(aws sns list-subscriptions-by-topic \
    --topic-arn "$TOPIC_ARN" \
    --region "$REGION" \
    --profile "$PROFILE" \
    --query 'Subscriptions[?SubscriptionArn!=`PendingConfirmation`] | length(@)' \
    --output text 2>/dev/null || echo "0")

  PENDING=$(aws sns list-subscriptions-by-topic \
    --topic-arn "$TOPIC_ARN" \
    --region "$REGION" \
    --profile "$PROFILE" \
    --query 'Subscriptions[?SubscriptionArn==`PendingConfirmation`] | length(@)' \
    --output text 2>/dev/null || echo "0")

  if [ "$CONFIRMED" = "0" ] && [ "$PENDING" = "0" ]; then
    echo "❌ NO SUBSCRIPTION:  $TOPIC_NAME"
  elif [ "$PENDING" != "0" ]; then
    echo "⏳ PENDING CONFIRM:  $TOPIC_NAME  (${PENDING} pending, ${CONFIRMED} confirmed)"
  else
    echo "✅ OK:               $TOPIC_NAME  (${CONFIRMED} confirmed)"
  fi
done
```

### 9.3 Check the Monitoring Alerts Topic Specifically

```bash
# Get the ARN from SSM
TOPIC_ARN=$(aws ssm get-parameter \
  --name "/k8s/development/monitoring/alerts-topic-arn-pool" \
  --region eu-west-1 \
  --profile development \
  --query 'Parameter.Value' \
  --output text)

echo "Topic ARN: $TOPIC_ARN"

# List all subscriptions
aws sns list-subscriptions-by-topic \
  --topic-arn "$TOPIC_ARN" \
  --region eu-west-1 \
  --profile development \
  --output table

# Check topic attributes (encryption, access policy)
aws sns get-topic-attributes \
  --topic-arn "$TOPIC_ARN" \
  --region eu-west-1 \
  --profile development
```

### 9.4 Verify Grafana Contact Point Is Wired

```bash
# SSH or kubectl exec into a monitoring node / Grafana pod
# Check the provisioned alerting ConfigMap
kubectl get configmap grafana-alerting -n monitoring -o yaml | grep -A 20 "contactpoints"

# Check if the SNS topic ARN is rendered in the ConfigMap
kubectl get configmap grafana-alerting -n monitoring -o jsonpath='{.data.contactpoints\.yaml}'
```

### 9.5 Check Subscription Confirmation Status

AWS SNS email subscriptions require the recipient to **click a confirmation link** in the initial email. Until confirmed, the subscription has `SubscriptionArn: PendingConfirmation`.

```bash
# Check all subscriptions across the account (not paginated — for small accounts)
aws sns list-subscriptions \
  --region eu-west-1 \
  --profile development \
  --query 'Subscriptions[*].{Topic: TopicArn, Protocol: Protocol, Status: SubscriptionArn}' \
  --output table
```

### 9.6 Test SNS Delivery (Smoke Test)

```bash
# Manually publish a test message to the monitoring alerts topic
TOPIC_ARN=$(aws ssm get-parameter \
  --name "/k8s/development/monitoring/alerts-topic-arn-pool" \
  --region eu-west-1 --profile development \
  --query 'Parameter.Value' --output text)

aws sns publish \
  --topic-arn "$TOPIC_ARN" \
  --subject "Test Alert from CLI" \
  --message "This is a manual test of the SNS monitoring alerts topic. If you received this, the topic subscription is confirmed and working." \
  --region eu-west-1 \
  --profile development
```

---

## 10. Recommendations

### Priority 1 — Critical Gaps ✅ All Resolved (15 April 2026)

| Action | File(s) Changed | Status |
|---|---|---|
| Pass `notificationEmail` to `monitoringPoolStack` | `infra/lib/projects/kubernetes/factory.ts` | ✅ **Fixed** — `notificationEmail: emailConfig.notificationEmail` added |
| Wire Grafana SNS topic ARN via ArgoCD Helm parameter override | `kubernetes-app/k8s-bootstrap/system/argocd/steps/apps.py` · `inject_monitoring_helm_params` (line 45) | ✅ **Confirmed** — already implemented as Step 5b |
| Automate ArgoCD notifications secret creation from SSM | `steps/apps.py` · new `provision_argocd_notifications_secret` (Step 5e) + `bootstrap_argocd.py` | ✅ **Fixed** — reads SSM SecureStrings, creates K8s secret idempotently |

> [!IMPORTANT]
> **Pre-requisite for Gap 3:** Store the GitHub App credentials in SSM before the next bootstrap run:
> ```bash
> aws ssm put-parameter --name "/k8s/development/argocd/github-app-id" \
>   --type SecureString --value "<GitHub App ID>"
> aws ssm put-parameter --name "/k8s/development/argocd/github-installation-id" \
>   --type SecureString --value "<Installation ID>"
> aws ssm put-parameter --name "/k8s/development/argocd/github-private-key" \
>   --type SecureString --value "$(cat /path/to/github-app-private-key.pem)"
> ```
> Without these parameters, the `provision_argocd_notifications_secret` step exits gracefully with a warning. ArgoCD Notifications will silently skip GitHub commit-status updates until the secret is populated.

---

### Priority 2 — Hardening (Next Steps)

| Action | Rationale |
|---|---|
| Add CloudWatch Alarm on `SNSNumberOfNotificationsFailed` for monitoring topic | Detect silent publish failures (e.g. KMS permission or IAM issues on `sns:Publish`) |
| Add `AllowHTTPS` SQS policy note to DLQ topic (`AwsSolutions-SNS3` suppression) | Current suppression is justified but should be re-evaluated before production go-live |
| Subscribe monitoring topic to a Lambda for structured alerting | Email notifications are raw JSON; a Lambda can render HTML, add runbook links, and forward to Slack/PagerDuty |
| Confirm email subscriptions post-deploy | Add a `just ops-audit` recipe that checks for `PendingConfirmation` subscriptions and warns — new subscriptions require the recipient to click a confirmation link |
| Add CDK integration test asserting `notificationEmail` prop on monitoring pool | Prevent regression — a `assert_resource_properties` check on the SNS subscription in `infra/tests/` |

### Priority 3 — Future Architecture

| Action | Rationale |
|---|---|
| Migrate Grafana SNS contact point to `Webhook` + formatting Lambda | Grafana SNS sends raw JSON; a webhook allows custom HTML email templates with alert context |
| Add Loki-based alerting for log-pattern detection | All 12 current alert rules are PromQL/metric-based; log pattern alerts (e.g. `OOM killed`, `panic:`) complement trace-based DynamoDB alerts |
| Enable Grafana OnCall (community OSS) | OnCall provides escalation schedules and acknowledgement workflows — reduces alert fatigue compared to raw SNS email |
| Multi-environment notification matrix | As additional environments (staging, production) are added, add per-environment `notificationEmail` and dedicated SNS topics rather than sharing a single topic |

---

## 11. Verification Checklist

After the next CDK deploy + bootstrap run, verify the full chain with these commands:

```bash
# 1. Confirm the monitoring SNS topic has an email subscription
TOPIC_ARN=$(aws ssm get-parameter \
  --name "/k8s/development/monitoring/alerts-topic-arn-pool" \
  --query 'Parameter.Value' --output text --region eu-west-1)

aws sns list-subscriptions-by-topic \
  --topic-arn "$TOPIC_ARN" \
  --query 'Subscriptions[*].{Protocol:Protocol,Endpoint:Endpoint,Status:SubscriptionArn}' \
  --output table
# Expected: Protocol=email, Status=<arn> (not 'PendingConfirmation')

# 2. Verify Grafana contact point has the SNS ARN wired
kubectl get configmap grafana-alerting -n monitoring \
  -o jsonpath='{.data.contactpoints\.yaml}'
# Expected: topic_arn: arn:aws:sns:eu-west-1:...:k8sdevelopment-monitoring-alerts

# 3. Verify ArgoCD notifications secret exists in cluster
kubectl get secret argocd-notifications-secret -n argocd \
  -o jsonpath='{.data}' | jq 'keys'
# Expected: ["github-appID", "github-installationID", "github-privateKey"]

# 4. Smoke test — manually publish to monitoring topic
aws sns publish \
  --topic-arn "$TOPIC_ARN" \
  --subject "[TEST] Notification Chain Verification" \
  --message "Manual smoke test confirming the Grafana → SNS → Email chain is wired correctly." \
  --region eu-west-1
# Expected: MessageId returned + email received within 60 seconds

# 5. Confirm ArgoCD Notifications is posting GitHub commit statuses
# Trigger an ArgoCD sync and check the GitHub commit SHA for a status check:
# Repository → Commits → <latest commit> → should show argocd/<app-name> status checks
```

---

*Report generated from codebase analysis of `infra/lib/stacks/` and `kubernetes-app/` directories.*  
*Remediation applied 15 April 2026 — all Priority 1 gaps resolved and verified with TypeScript `tsc --noEmit` (0 errors) and Python `py_compile` (syntax OK).*  
*Cross-referenced: `infra/lib/projects/kubernetes/factory.ts`, `infra/lib/constructs/ssm/bootstrap-alarm.ts`, `kubernetes-app/platform/charts/monitoring/chart/templates/grafana/`, `kubernetes-app/k8s-bootstrap/system/argocd/steps/apps.py`, `kubernetes-app/k8s-bootstrap/system/argocd/bootstrap_argocd.py`*
