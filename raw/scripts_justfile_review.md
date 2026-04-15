# Scripts & Task Runner Architectural Review

**Project**: `cdk-monitoring` — Solo-Developer AWS/Kubernetes Portfolio  
**Scope**: `justfile` · `scripts/lib/` · `scripts/local/` · `scripts/dynamodb/` · `scripts/*.sh` · `scripts/*.py`  
**Author**: Nelson Lamounier  
**Review Date**: April 2026

---

## Table of Contents

1. [Overview & Architectural Philosophy](#1-overview--architectural-philosophy)
2. [The `justfile` — Task Runner as CLI Contract](#2-the-justfile--task-runner-as-cli-contract)
   - 2.1 [Why `just` Over npm Scripts or Make](#21-why-just-over-npm-scripts-or-make)
   - 2.2 [Recipe Groups & Namespace Design](#22-recipe-groups--namespace-design)
   - 2.3 [CI/CD Integration Pattern](#23-cicd-integration-pattern)
   - 2.4 [Key Design Decisions](#24-key-design-decisions)
3. [Shared Library — `scripts/lib/`](#3-shared-library--scriptslib)
   - 3.1 [`logger.ts` — Structured Console Output](#31-loggerts--structured-console-output)
   - 3.2 [`aws-helpers.ts` — Auth & Config Abstraction](#32-aws-helpersts--auth--config-abstraction)
4. [Local Diagnostic Scripts — `scripts/local/`](#4-local-diagnostic-scripts--scriptslocal)
   - 4.1 [`control-plane-troubleshoot.ts` — The Flagship Diagnostic](#41-control-plane-troubleshootts--the-flagship-diagnostic)
   - 4.2 [`ssm-automation.ts` — SSM Execution Inspector](#42-ssm-automationts--ssm-execution-inspector)
   - 4.3 [`asg-audit.ts` — Infrastructure Coverage Auditor](#43-asg-audits--infrastructure-coverage-auditor)
   - 4.4 [`ebs-lifecycle-audit.ts` — Volume Persistence Verification](#44-ebs-lifecycle-audits--volume-persistence-verification)
   - 4.5 [`cfn-troubleshoot.ts` — CloudFormation Stack Analyser](#45-cfn-troubleshootts--cloudformation-stack-analyser)
   - 4.6 [`cloudwatch-logs.ts` / `cloudwatch-log-audit.ts`](#46-cloudwatch-logsts--cloudwatch-log-audits)
   - 4.7 [`cw-last-query.ts` — CloudWatch Insights Runner](#47-cw-last-queryts--cloudwatch-insights-runner)
   - 4.8 [`sns-orphans.ts` — SNS Subscription Orphan Detection](#48-sns-orphansts--sns-subscription-orphan-detection)
   - 4.9 [`gh-dispatch.ts` — GitHub Actions Trigger Utility](#49-gh-dispatchts--github-actions-trigger-utility)
   - 4.10 [`control-plane-autofix.ts` — Automated Repair Agent](#410-control-plane-autofixts--automated-repair-agent)
   - 4.11 [`diagnostics/ssm-bootstrap-diagnose.sh`](#411-diagnosticsssm-bootstrap-diagnosesh)
5. [DynamoDB Migration Scripts — `scripts/dynamodb/`](#5-dynamodb-migration-scripts--scriptsdynamodb)
   - 5.1 [`migrate-articles-to-dynamodb.ts`](#51-migrate-articles-to-dynamodbts)
   - 5.2 [`verify-migration.ts`](#52-verify-migrationts)
   - 5.3 [`add-tag-index.ts`](#53-add-tag-indexts)
6. [Root Shell Scripts](#6-root-shell-scripts)
   - 6.1 [`fix-control-plane-cert.sh` — Certificate SAN Emergency Fix](#61-fix-control-plane-certsh--certificate-san-emergency-fix)
   - 6.2 [`cluster-health.sh` — Quick Cluster Snapshot](#62-cluster-healthsh--quick-cluster-snapshot)
7. [Knowledge Base Tooling — `scripts/kb-drift-check.py`](#7-knowledge-base-tooling--scriptskb-drift-checkpy)
8. [Cross-Cutting Design Patterns](#8-cross-cutting-design-patterns)
9. [Integration with CI/CD Pipelines](#9-integration-with-cicd-pipelines)
10. [Summary & Assessment](#10-summary--assessment)

---

## 1. Overview & Architectural Philosophy

The `scripts/` directory and the `justfile` task runner form the **operational backbone** of the project. They exist to solve a fundamental problem in infrastructure engineering: **the gap between what CI/CD automates and what a human operator needs to investigate, repair, or migrate when automation breaks down**.

### The Core Problem

When you run `kubectl get nodes` and the cluster is in an unknown state at 2 AM, you need:

1. A **single entry point** that doesn't require you to remember 20 different AWS CLI flags.
2. **Contextual diagnostics** — not raw data, but an opinionated analysis that surfaces the most likely root cause first.
3. **Automatic remediation** for well-understood failure modes, with a safe fallback to "show me exactly what went wrong."

The `justfile` + `scripts/` combination solves all three. The `justfile` is the **stable interface** — it never changes its recipe names even when the underlying implementation evolves. The scripts are the **implementation** — typed, testable, and purpose-built for each operational concern.

### Design Pillars

| Pillar | Mechanism |
|--------|-----------|
| **Environment Parity** | CI pipelines call `just <recipe>` identically to local development |
| **Type Safety** | All scripts are TypeScript with `strict: true`, preventing a class of runtime crashes common in shell scripts |
| **Observability** | Every script logs to both stdout (coloured) and a timestamped file via `startFileLogging()` |
| **Composability** | Shared `lib/` utilities prevent auth logic, argument parsing, and AWS client creation from being duplicated across 11 scripts |
| **Self-Documentation** | Every script accepts `--help` and prints a structured usage guide; the `justfile` comments every recipe group |

---

## 2. The `justfile` — Task Runner as CLI Contract

### 2.1 Why `just` Over npm Scripts or Make

The choice of [`just`](https://github.com/casey/just) over `npm scripts` or `Makefile` is deliberate and has concrete engineering benefits:

**vs. npm Scripts (`package.json`)**

| Concern | npm scripts | `just` |
|---------|------------|--------|
| Multi-step recipes | Requires `&&` chains or external scripts | Native recipe dependencies (`just deploy` → calls `just synth`) |
| Comments | Not supported in JSON | Full comment support — every recipe is self-documenting |
| Argument passing | `-- --flag` workaround | Native variable interpolation `just deploy stack=$STACK` |
| Cross-package execution | Requires `--filter` or `--cwd` flags | Single `justfile` at monorepo root covers all packages |
| Tab completion | None | Native shell completion available |

**vs. Makefile**

| Concern | Makefile | `just` |
|---------|---------|--------|
| Prerequisite tracking | File-based — targets re-run based on file modification times | Command-based — always re-runs, predictable in infrastructure contexts |
| Variable syntax | `$(VAR)` / `${VAR}` conflicts with shell | Clean variable syntax, no escaping confusion |
| Error messages | Cryptic `make: *** [Makefile:52: target] Error 1` | Descriptive with context |
| Windows support | Requires WSL | Native cross-platform |
| Learning curve | High — non-obvious whitespace rules (tabs vs spaces) | Minimal |

**The key insight**: In a CDK monorepo, you run `just` recipes many times per day from multiple contexts (terminal, CI runner, VS Code task). The tool needs to be **frictionless**. `just` achieves this.

### 2.2 Recipe Groups & Namespace Design

The `justfile` is organized into **six recipe groups**, each covering a distinct operational concern:

```
cdk       — CDK synthesis, diff, deployment, and stack management
ci        — CI pipeline entry points (lint, test, type-check)
test      — Unit and integration test runners  
k8s       — Kubernetes cluster operations (kubeconfig, ArgoCD, Helm)
ops       — Operational scripts (diagnostics, migrations, audits)
infra     — Raw AWS infrastructure inspection helpers
```

This grouping mirrors the **separation of concerns** in the broader project:

- `cdk` recipes map to `infra/` CDK code
- `k8s` recipes map to `kubernetes-app/` (ArgoCD/Helm)
- `ops` recipes map to `scripts/local/` (TypeScript diagnostics)
- `ci` and `test` recipes map to `infra/tests/` and GitHub Actions

**Example: CDK Group**

```justfile
# Synthesise a single stack without deploying
[group('cdk')]
synth stack='':
    cd infra && npx cdk synth {{stack}}

# Deploy a specific stack — uses CDK_DEFAULT_ACCOUNT from env
[group('cdk')]
deploy stack profile='dev-account':
    AWS_PROFILE={{profile}} cd infra && npx cdk deploy {{stack}} \
        --require-approval never \
        --no-rollback
```

The `stack` and `profile` parameters have defaults, allowing developers to call `just synth` (synthesises everything) or `just deploy compute-stack` (scoped deployment).

**Example: Ops Group**

```justfile
# Run the full control plane diagnostic
[group('ops')]
diagnose profile='dev-account':
    npx tsx scripts/local/control-plane-troubleshoot.ts --profile {{profile}}

# Audit CloudWatch dashboards vs live infrastructure
[group('ops')]
asg-audit profile='dev-account':
    npx tsx scripts/local/asg-audit.ts --profile {{profile}}
```

This means a developer debugging a cluster issue types `just diagnose` rather than remembering: `npx tsx scripts/local/control-plane-troubleshoot.ts --profile dev-account --region eu-west-1`.

### 2.3 CI/CD Integration Pattern

Every GitHub Actions workflow that triggers infrastructure work calls `just` recipes, never raw commands:

```yaml
# .github/workflows/_deploy-kubernetes.yml
- name: Deploy CDK stacks
  run: just deploy-kubernetes ${{ inputs.environment }}

# .github/workflows/ci.yml  
- name: Run unit tests
  run: just test-stacks

# .github/workflows/_deploy-ssm-automation.yml
- name: Post-deploy verification
  run: just verify-ssm ${{ inputs.stack_name }}
```

**Why this matters**: If the underlying CDK command changes (e.g., moving from `cdk deploy` to `cdk deploy --hotswap`), you change **one line in the `justfile`**. All 12+ GitHub Actions workflows automatically inherit the change without any YAML modification. This is the **"single source of truth for execution"** pattern.

### 2.4 Key Design Decisions

**Decision 1: AWS_PROFILE resolution at recipe level**

Rather than embedding `export AWS_PROFILE=dev-account` in every command, the `justfile` accepts `profile` as a positional parameter with a sensible default. This means:

- Local developers with multiple AWS accounts never accidentally deploy to the wrong account
- CI workflows pass `profile=ci` which maps to OIDC-assumed roles (no static credentials)
- The same recipe works in both contexts

**Decision 2: `--require-approval never` for deployment recipes**

CDK's interactive approval gate is incompatible with CI automation. The `justfile` explicitly passes `--require-approval never` on all deployment recipes. This is safe because:

- All infrastructure changes go through pull request review before CI deploys
- The actual human approval gate is the GitHub PR, not the CDK prompt
- Post-deploy integration tests (`infra/tests/integration/`) provide the automated safety net

**Decision 3: Recipes as documentation**

Every recipe in the `justfile` has a comment explaining:
- What it does (the action)
- When to use it (the context)
- What it requires (pre-conditions)

This turns `just --list` into a self-describing operations manual — particularly valuable when returning to the project after weeks of absence.

---

## 3. Shared Library — `scripts/lib/`

The `lib/` directory contains two files that underpin every TypeScript script in the project. Their existence is the single most important architectural decision in the scripting layer — without them, each of the 11 scripts would duplicate ~120 lines of boilerplate.

### 3.1 `logger.ts` — Structured Console Output

**File**: `scripts/lib/logger.ts` (173 lines)

**Problem it solves**: Unstructured `console.log` output in long-running diagnostic scripts is noise. When a script runs 25 checks and prints 400 lines, you need visual hierarchy to locate the failure instantly.

**Implementation**:

The logger provides two layers of output:

**Layer 1: Semantic log functions**

```typescript
log.header('Control Plane Troubleshooter');     // Large visual separator
log.step(1, 4, 'Inspecting SSM parameters...'); // Numbered progress indicator
log.success('All 6 SSM parameters found');      // Green checkmark
log.warn('Certificate SAN mismatch detected');  // Yellow warning
log.fatal('Cannot proceed — instanceId missing'); // Red, process.exit(1)
log.config('Configuration', { Region: 'eu-west-1', Auth: 'OIDC' }); // Config table
log.summary('Diagnostic Complete', { Checks: '25', Failed: '2' });  // Summary table
log.nextSteps(['Fix cert: just run fix-cert', 'Re-run: just diagnose']); // Actionable
```

Each function applies ANSI colour codes (via `log.red()`, `log.green()`, `log.cyan()`, etc.) that are composable — allowing inline colouring within longer strings.

**Layer 2: File-based logging**

```typescript
const logFile = startFileLogging('ssm-automation');
// ... all console output is now also written to:
// scripts/local/diagnostics/.troubleshoot-logs/ssm-automation-2026-04-14T15:32:00.log

stopFileLogging(); // Restores original console methods
```

The implementation **monkey-patches** `console.log`, `console.warn`, and `console.error` to intercept output and write it to a timestamped file. This is a deliberate design choice over a wrapper approach — it means *all* output is captured, including output from third-party AWS SDK calls and any nested function calls that happen to use `console` directly.

**Why file logging?**

When an SSM Automation script runs in CI and fails at step 3 of 12, the CI log is ephemeral (GitHub Actions uploads it to S3 and shows it in the UI). But when debugging locally, you want to `diff` the output of two diagnostic runs to see what changed between an ASG replacement cycle. The timestamped log files enable exactly this.

**Design pattern: Separation of presentation from logic**

The logger is purely presentational — it never makes decisions or throws meaningful errors. Script logic remains in the script itself. This enables:

- Scripts can be tested without worrying about console output format
- The logger can be replaced with a JSON-line logger for structured log aggregation without changing any script logic

### 3.2 `aws-helpers.ts` — Auth & Config Abstraction

**File**: `scripts/lib/aws-helpers.ts` (244 lines)

**Problem it solves**: The project uses two fundamentally different authentication mechanisms:

1. **Local development**: Named AWS CLI profiles (`--profile dev-account`)
2. **CI/CD pipelines**: OIDC-assumed IAM roles (no named profile, credentials in `AWS_*` environment variables)

Without abstraction, every script would need an `if (process.env.GITHUB_ACTIONS)` branch, duplicated 11 times.

**The `resolveAuth()` function**:

```typescript
export function resolveAuth(profile: string | undefined): AuthResult {
  // CI detection: GITHUB_ACTIONS env var is always set by GitHub Actions runners
  const isCI = Boolean(process.env['GITHUB_ACTIONS']);
  
  if (isCI) {
    return { mode: 'OIDC', credentials: undefined }; // SDK picks up ambient credentials
  }
  
  if (profile) {
    return { mode: `profile:${profile}`, credentials: fromIni({ profile }) };
  }
  
  // Fallback: default credential chain (ambient credentials, EC2 instance profile, etc.)
  return { mode: 'default-chain', credentials: undefined };
}
```

**The `parseArgs()` function**:

The project implements its own CLI argument parser rather than using `yargs` or `commander`. This is a pragmatic decision:

- Adds **zero dependencies** to the scripts package
- The scripts have a small, fixed set of arguments — a full CLI framework is overkill
- The custom parser generates identical `--help` output format across all scripts, creating a consistent developer experience

```typescript
const args = parseArgs([
  { name: 'profile', description: 'AWS CLI profile', hasValue: true },
  { name: 'region',  description: 'AWS region', hasValue: true, default: 'eu-west-1' },
  { name: 'env',     description: 'Environment: development, staging, production', 
    hasValue: true, default: 'development' },
  { name: 'fix',     description: 'Attempt automatic certificate repair', 
    hasValue: false, default: false },
], 'Control Plane Troubleshooter — diagnose K8s control plane after ASG replacement');
```

Calling `npx tsx scripts/local/control-plane-troubleshoot.ts --help` prints:

```
Usage: control-plane-troubleshoot [OPTIONS]

  Control Plane Troubleshooter — diagnose K8s control plane after ASG replacement

Options:
  --profile  <value>   AWS CLI profile
  --region   <value>   AWS region [default: eu-west-1]
  --env      <value>   Environment: development, staging, production [default: development]
  --fix                Attempt automatic certificate repair
```

**The `buildAwsConfig()` function**:

Composes `resolveAuth()` + `parseArgs()` output into a single SDK config object:

```typescript
export function buildAwsConfig(args: Record<string, unknown>): AwsConfig {
  const profile = args['profile'] as string | undefined;
  const region  = (args['region'] as string) ?? 'eu-west-1';
  const auth    = resolveAuth(profile);
  return { region, profile, credentials: auth.credentials };
}
```

Every script can then construct any AWS SDK client with three lines:

```typescript
const config = buildAwsConfig(args);
const ssm = new SSMClient({ region: config.region, credentials: config.credentials });
const ec2 = new EC2Client({ region: config.region, credentials: config.credentials });
```

---

## 4. Local Diagnostic Scripts — `scripts/local/`

### 4.1 `control-plane-troubleshoot.ts` — The Flagship Diagnostic

**File**: 1,737 lines | **Complexity**: High | **Purpose**: Deep control plane health analysis

This is the most complex and most important script in the suite. It was written in response to a class of production failures unique to the project's architecture: **ASG-based Kubernetes control plane replacement**.

**The Problem It Solves**

The project runs Kubernetes on a single EC2 instance managed by an Auto Scaling Group (1 min / 1 max / 1 desired). When AWS replaces the instance (due to health check failure, spot interruption, or manual refresh), the SSM Automation bootstraps a new control plane. Three failure modes can occur:

1. **SSM Parameter staleness**: The `instance-id` parameter in SSM still points to the old terminated instance
2. **EBS volume misattachment**: The etcd data volume isn't re-attached to the new instance
3. **Certificate SAN mismatch**: The API server certificate has SANs for the old instance's IPs; with the new IP, kubelet TLS verification fails and nodes cannot join

Without this script, diagnosing which of the three failure modes occurred requires manually navigating AWS Console across 4+ services (EC2, SSM, Systems Manager, CloudWatch Logs) which takes ~20 minutes.

With the script: `just diagnose` → ~90 seconds → structured verdict.

**Four-Phase Architecture**

The script executes four phases sequentially, each producing a set of `CheckResult` objects with `passed`, `detail`, and `severity` fields:

```
Phase 1: Infrastructure
  ├── SSM Parameters (6 checks): instance-id, endpoint, IPs, AMI, k8s version
  ├── EC2 Instance (3 checks): state, IP addresses, EBS volume lifecycle
  └── ASG Configuration (2 checks): capacity, instance health

Phase 2: SSM Automation History  
  ├── Recent execution listing (last N executions)
  ├── Per-execution step-level failure analysis
  └── Failure message extraction with severity tagging

Phase 3: DR Certificate & Backup State
  ├── IMDS metadata (private IP, public IP, instance type, AZ)
  ├── API server certificate SAN extraction and current-IP check
  ├── PKI directory file count
  ├── admin.conf / super-admin.conf existence
  ├── Bootstrap summary JSON parsing (run_summary.json)
  └── kubeadm-config podSubnet validation

Phase 4: Kubernetes Cluster Diagnostics (optional via --skip-k8s)
  ├── API server health check (kube-healthz endpoint)
  ├── Node status (kubectl get nodes)
  ├── Pod status across all namespaces
  ├── Calico CNI marker file presence
  ├── Kubelet service status and recent logs
  └── CloudWatch bootstrap log stream inspection
```

**Key Technical Decisions**

*SSM RunCommand as remote shell executor*: All phases that need to inspect the instance (Phases 3 and 4) execute shell commands via `AWS-RunShellScript` rather than requiring SSH access. This means:
- No bastion host or SSH keys are required
- Works even if the instance is in a private subnet with no public IP
- All output is captured via `GetCommandInvocation` API

*Structured output parsing*: Phase 3 injects named markers into the shell script output (`META_PRIVATE_IP=...`, `CERT_EXISTS=...`, `=== DR_STATE ===`) and parses them out of the response. This is the TypeScript equivalent of a protocol — the remote shell and the local TypeScript parser share an implicit contract.

*Severity tiers*: Failures are tagged `critical`, `warning`, or `info`. The final summary groups them by severity, allowing operators to ignore informational items and focus on critical failures.

*`--fix` flag*: The script accepts a `--fix` flag that triggers automatic certificate regeneration if a SAN mismatch is detected (delegates to `control-plane-autofix.ts`). This transforms the script from a diagnostic tool into a repair tool when the operator is confident.

*`--skip-k8s` flag*: If the instance is reachable via SSM but the API server is completely broken, Phase 4 will time out on every check (120s timeout per SSM command × 6 checks = 12 minutes). The `--skip-k8s` flag lets operators get the Phase 1–3 results immediately and decide whether Phase 4 is worth running.

**What It Outputs**

```
  Control Plane Troubleshooter
  ════════════════════════════
  
  Configuration:
    Environment: development
    Auth: profile:dev-account
    Region: eu-west-1
  
  ── Phase 1: Infrastructure ──────────────────────
  ✓  SSM: /k8s/development/instance-id           → i-0abc1234567
  ✓  SSM: /k8s/development/control-plane-endpoint → 10.0.1.52
  ✓  EC2: Instance state                          → State: running
  ✗  DR: Certificate SANs  [CRITICAL]
       ⚠ MISMATCH: Cert SANs [10.0.1.40, 54.12.x.x] do NOT include current IP 10.0.1.52

  Root Cause Analysis:
  ┌─ Critical: Certificate SAN mismatch detected
  │  The API server certificate was restored from backup with old IPs.
  │  The new instance has IP 10.0.1.52 which is NOT in the cert SANs.
  └─ Recommended fix: just fix-cert OR just diagnose --fix

  Next Steps:
  1) Run: just fix-cert      (regenerates cert for new IP)
  2) Or:  just diagnose --fix (automated repair)
  3) After fix, run: just diagnose --skip-k8s to verify Phase 1-3
```

### 4.2 `ssm-automation.ts` — SSM Execution Inspector

**File**: 822 lines | **Purpose**: Post-mortem analysis of SSM Automation runs

**The Problem It Solves**

SSM Automation executions write step-level output but the AWS Console truncates step output to 2,500 characters — exactly at the point where bootstrap scripts often fail (deep in `kubeadm init` output). This script provides **unbounded log access** using a dual retrieval strategy.

**Dual Log Retrieval Strategy**

```
Priority 1: CloudWatch Logs (unlimited)
  ├── Discovers streams via commandId prefix
  ├── Paginates with nextForwardToken (500 events/page)
  └── Separates stdout and stderr streams

Priority 2: GetCommandInvocation API (24 KB)
  ├── Triggered when CWL streams return 0 events
  ├── Extracts instanceId from step output JSON
  └── Warns if output URL is present (>24 KB truncation)
```

The fallback chain is explicitly documented in the function signature:

```typescript
/**
 * ## Output strategy (in priority order):
 *   1. CloudWatch logs — full paginated output (500 events/page)
 *   2. GetCommandInvocation fallback — up to 24 KB when CWL has no streams
 *   3. Native SSM step outputs — always shown (may be truncated at 2500 chars)
 */
async function inspectExecution(...): Promise<{totalSteps: number; failedSteps: number}>
```

**Log Group Auto-Resolution**

The script infers which CloudWatch Log Group to read based on the SSM document name:

```typescript
function resolveLogGroup(logGroupBase, logGroupOverride, documentName): string {
  const nameLC = (documentName ?? '').toLowerCase();
  if (nameLC.includes('deploy'))    return `${logGroupBase}/deploy`;
  if (nameLC.includes('bootstrap')) return `${logGroupBase}/bootstrap`;
  return `${logGroupBase}/bootstrap`; // safe default
}
```

This mirrors the actual CloudWatch Log Group structure created by the SSM constructs in `infra/lib/stacks/ssm/`:
- `/ssm/k8s/development/bootstrap` — control-plane/worker bootstrap runs
- `/ssm/k8s/development/deploy` — secrets deployment runs

**Human-Readable Execution Overview**

```
  ╔══ Execution 1/3 ════════════════════════════════════════
  ║  ID: exec-0abc1234567890abc
  ║  Document: k8s-dev-bootstrap-control-plane
  ║  Status: Failed
  ║  Started: 2026-04-11T02:15:30Z
  ║  Duration: 8m 42s
  ║  Failure: Step "install-calico" failed: kubeadm token create returned exit code 1
  ╚════════════════════════════════════════════════════════
  
  ✗  Step 4/7: install-calico (aws:runCommand)
     Status: Failed
     Failure: kubeadm token create returned exit code 1
     Failure Type: Command
     RunCommand ID: cmd-0xyz789
     [CWL] + kubeadm token create
     [CWL] error: Post "https://10.0.1.52:6443/api/v1/...": dial tcp 10.0.1.52:6443: connect: connection refused
```

This output tells the operator exactly which step failed, why it failed, and what the remote shell printed — without any manual AWS Console navigation.

### 4.3 `asg-audit.ts` — Infrastructure Coverage Auditor

**File**: 449 lines | **Purpose**: Verify all AWS resources are covered by CloudWatch dashboards

**The Problem It Solves**

As the infrastructure grows (new Lambda functions, new ASGs, new CloudFront distributions), it's easy for monitoring coverage to drift. A new Lambda is deployed but never added to a CloudWatch dashboard. The `asg-audit.ts` script detects this drift by cross-referencing live AWS resources against dashboard widget definitions.

**Multi-Resource Inventory**

The script inventories:
- All Auto Scaling Groups (ASGs)
- All Network Load Balancers (NLBs)
- All Lambda functions (excluding CDK internal `awscdk-*`, `CustomResource-*`, `LogRetention-*`)
- All CloudFront distributions
- All Step Functions state machines
- All SSM Parameters
- All EBS volumes tagged `managed-by=cdk`

**Dashboard Cross-Reference**

For each CloudWatch dashboard, it parses the dashboard body JSON and extracts the resource identifiers used in metrics widgets:

```typescript
for (const metricRow of metrics) {
  for (let i = 0; i < metricRow.length; i++) {
    const val = metricRow[i];
    if (val === 'AutoScalingGroupName') asgSet.add(metricRow[i+1]);
    if (val === 'LoadBalancer')         nlbSet.add(metricRow[i+1]);
    if (val === 'FunctionName')         lambdaSet.add(metricRow[i+1]);
    if (val === 'DistributionId')       cloudFrontSet.add(metricRow[i+1]);
    if (val === 'StateMachineArn')      stateMachineSet.add(metricRow[i+1]);
  }
}
```

**Orphan Detection Report**

```
================================================
     Unmonitored Orphan Resources
================================================

🚨 WARNING: Missing Dashboard Integrations
  ├─ ASGs              : k8s-dev-monitoring-worker-asg
  ├─ NLBs              : None
  ├─ Lambdas           : k8s-dev-bedrock-remediation
  ├─ CloudFront        : None
  └─ StepFunctions     : arn:aws:states:eu-west-1:123456789012:stateMachine:k8s-dev-bootstrap-orchestrator
```

This output is the **input to the next sprint** — it drives the creation of new CloudWatch dashboard widgets.

**Parallel API Calls**

The main function fires all 8 API calls simultaneously using `Promise.all()`:

```typescript
const [asgResult, dashboardResult, parameterResult, ebsResult, 
       nlbResult, lambdaResult, cloudFrontResult, sfnResult] = await Promise.all([
  listAllASGs(asgClient),
  listAllDashboards(dashboardClient),
  listParemeters(ssmClient),       // note: original typo preserved
  listCloudFormationEbsVolumes(ec2Client),
  listAllNlbs(elbClient),
  listAllLambdas(lambdaClient),
  listAllCloudFronts(cloudFrontClient),
  listAllStateMachines(sfnClient),
]);
```

This reduces total API latency from ~8 × (sequential API round-trips) to ~(max single API round-trip) — typically from ~16s to ~2s.

### 4.4 `ebs-lifecycle-audit.ts` — Volume Persistence Verification

**File**: 23,846 bytes | **Purpose**: Audit EBS volume `DeleteOnTermination` flags

**The Problem It Solves**

The project's Kubernetes control plane persists etcd state on a dedicated EBS volume. This volume **must not** have `DeleteOnTermination: true` — if it does, every ASG instance replacement would wipe the cluster state. This script audits all CDK-managed EBS volumes and flags any that are configured with ephemeral lifecycle semantics.

**Why This Matters**

EBS `DeleteOnTermination` is set at launch time via the instance's block device mapping. Changing it after launch requires an EC2 API call (`ModifyInstanceAttribute`). If it's wrong, you won't find out until an instance replacement happens — typically during a production incident.

The script runs as a pre-deployment check (`just pre-deploy-check`) to catch this class of misconfiguration before it causes a data-loss incident.

### 4.5 `cfn-troubleshoot.ts` — CloudFormation Stack Analyser

**File**: 17,484 bytes | **Purpose**: Extract meaningful failure reasons from CloudFormation deployments

**The Problem It Solves**

CloudFormation stack failures are notoriously opaque. The AWS Console shows a long list of resource events, but the actual root-cause resource (the first one that failed, triggering the rollback cascade) is buried under 30+ "ROLLBACK_IN_PROGRESS" events for resources that were just rolled back sympathetically.

`cfn-troubleshoot.ts` filters the event stream to show only:
1. The first `CREATE_FAILED` / `UPDATE_FAILED` event (the actual root cause)
2. Any `ROLLBACK_FAILED` events (secondary issues during recovery)
3. The stack-level failure message, which often contains IAM or resource limit context

**Integration with `justfile`**

```justfile
[group('ops')]
cfn-troubleshoot stack profile='dev-account':
    npx tsx scripts/local/cfn-troubleshoot.ts \
        --stack {{stack}} \
        --profile {{profile}}
```

Invoked automatically by CI steps when a CDK deployment returns a non-zero exit code.

### 4.6 `cloudwatch-logs.ts` / `cloudwatch-log-audit.ts`

**Purpose**: Two complementary CloudWatch log tools

**`cloudwatch-logs.ts`** — Interactive log tail for any CloudWatch Log Group:

```
npx tsx scripts/local/cloudwatch-logs.ts \
  --log-group /k8s/development/bootstrap \
  --stream-prefix cmd-0abc1234 \
  --since 2h
```

Used when you know which log group to look at but need to tail it without switching to the AWS Console.

**`cloudwatch-log-audit.ts`** — Aggregate log analysis:

Scans one or more CloudWatch Log Groups for error patterns, groups them by frequency, and produces a summary report. Used for:
- Identifying recurring errors across 100+ bootstrap runs
- Spotting transient errors that CloudWatch Alarms miss because they don't cross the threshold window

### 4.7 `cw-last-query.ts` — CloudWatch Insights Runner

**File**: 14,668 bytes | **Purpose**: Run pre-defined CloudWatch Logs Insights queries

**The Problem It Solves**

CloudWatch Logs Insights queries take 30–60 seconds and have a complex query syntax. This script stores a library of frequently-used queries (error rate by log group, kubeadm step timing analysis, kubelet restart events) and runs them with a single CLI command.

```bash
just cw-query --preset kubeadm-timing --since 7d
```

Equivalent to manually building, submitting, and paginating a CloudWatch Insights query — without the 5-click Console workflow.

### 4.8 `sns-orphans.ts` — SNS Subscription Orphan Detection

**File**: 8,556 bytes | **Purpose**: Detect SNS subscriptions without active CloudWatch alarm backing

**Context**: The initial CloudWatch monitoring strategy (before the Prometheus/Grafana stack was deployed) used SNS topics + email subscriptions as the alerting mechanism. As alarms evolved, some SNS subscriptions became "orphaned" — the alarm they were connected to was deleted but the subscription remained, causing spurious or silent notifications.

This script lists all SNS topics, cross-references them with CloudWatch alarms, and identifies topics with no associated alarms — candidates for cleanup.

### 4.9 `gh-dispatch.ts` — GitHub Actions Trigger Utility

**File**: 2,819 bytes | **Purpose**: Programmatically trigger GitHub Actions workflow dispatches

**Use Case**: Some workflows (e.g., `_deploy-kubernetes.yml`) are set to `workflow_dispatch` trigger only — they require a manual trigger. From the local environment, triggering them requires the GitHub CLI or the web UI.

This script provides a typed, authenticated alternative:

```typescript
await triggerWorkflow({
  repo: 'Nelson-Lamounier/cdk-monitoring',
  workflow: '_deploy-kubernetes.yml',
  ref: 'develop',
  inputs: { environment: 'development', stack: 'worker-asg-stack' },
});
```

The script uses `GITHUB_TOKEN` from the environment, supporting both local (personal access token) and CI (GITHUB_TOKEN secret) contexts.

### 4.10 `control-plane-autofix.ts` — Automated Repair Agent

**File**: 30,750 bytes | **Purpose**: Automated remediation of known control plane failure patterns

**The Problem It Solves**

`control-plane-troubleshoot.ts` diagnoses. `control-plane-autofix.ts` repairs. It encodes the runbook for the three most common failure modes into executable automation:

**Failure Mode 1: Certificate SAN Mismatch (post-ASG replacement)**

```
1. Stop kube-apiserver static pod (crictl rm)
2. Remove stale apiserver.crt and apiserver.key
3. Run: kubeadm init phase certs apiserver --apiserver-cert-extra-sans=<current IPs>
4. Restart kubelet
5. Wait for node Ready condition
6. Update SSM parameter: /k8s/development/control-plane-endpoint
```

**Failure Mode 2: kubeadm-config podSubnet missing**

```
1. Regenerate kubeadm-config ConfigMap with correct podSubnet (192.168.0.0/16)
2. Re-apply via kubectl
```

**Failure Mode 3: Node not joining (worker side)**

```
1. Fetch current bootstrap token: kubeadm token create --print-join-command
2. Publish to SSM: /k8s/development/worker-join-command
3. Triggerworker bootstrap SSM Automation
```

**Safety Features**:

- Before any repair, the script runs the full Phase 1–3 diagnostic and aborts if the instance is unreachable
- All repair steps are logged with timestamps
- A post-repair Phase 4 diagnostic runs automatically to confirm the repair succeeded
- The `--dry-run` flag prints commands without executing them

### 4.11 `diagnostics/ssm-bootstrap-diagnose.sh`

**File**: 15,625 bytes | **Purpose**: Bash counterpart to `control-plane-troubleshoot.ts`

This shell script predates the TypeScript diagnostic suite and was written when the TypeScript scripts were still in development. It covers similar ground (SSM parameters, EC2 state, certificate SANs) but outputs raw text rather than structured `CheckResult` objects.

**Why it still exists**: 

1. It can be run directly on the control plane instance via `bash` — no Node.js required
2. It's embedded in the `diagnostics/.troubleshoot-logs/` directory, co-located with the log output it generates
3. It serves as the **emergency fallback** when the TypeScript scripts fail (e.g., due to a Node.js version mismatch on the CI runner)

---

## 5. DynamoDB Migration Scripts — `scripts/dynamodb/`

These scripts manage the data layer for the `start-admin` article management system. They are one-time migration scripts, but their architecture follows the same patterns as the operational scripts.

### 5.1 `migrate-articles-to-dynamodb.ts`

**File**: 23,832 bytes | **Purpose**: Migrate article data from local JSON/file storage to DynamoDB

**Architecture**: Three-phase ETL pipeline:

```
Phase 1: Extract
  ├── Read articles from source (JSON files or existing DynamoDB table)
  └── Validate schema against ArticleDetail interface

Phase 2: Transform
  ├── Generate DynamoDB primary key: pk=ARTICLE#<slug>, sk=METADATA
  ├── Add GSI keys for tag-based queries: gsi1pk=TAG#<tag>, gsi1sk=<published_at>
  └── Serialize all fields with DynamoDB-native type annotations

Phase 3: Load
  ├── Batch write in groups of 25 (DynamoDB BatchWriteItem limit)
  ├── Implement exponential backoff on ProvisionedThroughputExceededException
  └── Report successful/failed writes with retry counts
```

**Why DynamoDB over PostgreSQL or other relational stores?**

The article access pattern is strictly key-based (`GET /articles/<slug>`) and tag-filtered (`GET /articles?tag=kubernetes`). There are no complex joins. DynamoDB's single-table design with GSIs perfectly matches this:

- `pk=ARTICLE#kubernetes-deep-dive` → O(1) article retrieval
- `gsi1pk=TAG#kubernetes` → O(log n) tag-filtered article listing

The operational simplicity of DynamoDB (no connection pooling, no database server to manage) also aligns with the project's "minimal operational surface area" philosophy.

### 5.2 `verify-migration.ts`

**File**: 7,796 bytes | **Purpose**: Post-migration validation

After `migrate-articles-to-dynamodb.ts` completes, `verify-migration.ts` runs a series of read queries to confirm:

1. Item count matches expected (compare source count to DynamoDB scan count)
2. Spot-check 3–5 articles by primary key — verify all fields present
3. GSI queries return expected results for known tags
4. No duplicate `pk` entries (would indicate a migration logic bug)

This script is invoked automatically in the CI pipeline after migration:

```yaml
- name: Run migration
  run: just migrate-articles --env development

- name: Verify migration
  run: just verify-migration --env development
```

### 5.3 `add-tag-index.ts`

**File**: 6,332 bytes | **Purpose**: Retroactively add tag GSI entries for existing articles

When the tag-filtering feature was added after the initial migration, all existing articles lacked `gsi1pk` / `gsi1sk` attributes. This script scans the DynamoDB table, finds items without the GSI keys, and backfills them — enabling tag-based queries without a full re-migration.

---

## 6. Root Shell Scripts

### 6.1 `fix-control-plane-cert.sh` — Certificate SAN Emergency Fix

**File**: 274 lines | **Language**: Bash

**The Problem**: After ASG instance replacement, the API server certificate has SANs for the old instance's IPs. The new instance's kubelet TLS verification fails. Nodes cannot join.

**Why Bash Instead of TypeScript?**

This script predates `control-plane-autofix.ts` and was written as an emergency repair tool. Bash was chosen because:

1. **No runtime dependencies** — available on any Linux system, no Node.js required
2. **Direct SSM CLI usage** — easier to read and modify in a high-stress incident than TypeScript SDK abstractions
3. **Minimal surface area** — 274 lines is easy to audit quickly

**The Repair Sequence**

```bash
Step 1: Fetch instance ID from SSM (/k8s/development/instance-id)
Step 2: Diagnose current state via SSM RunCommand
  ├── Extract current private/public IPs via IMDS
  ├── Dump certificate SANs via openssl
  └── Check node registration via kubectl
Step 3: If SAN mismatch detected:
  ├── Delete stale apiserver.crt and apiserver.key
  ├── kubeadm init phase certs apiserver --apiserver-cert-extra-sans=<IPs>
  ├── Restart kube-apiserver static pod
  └── Restart kubelet
Step 4: Post-fix:
  ├── Label node as control-plane
  ├── Remove uninitialized taint
  ├── Uninstall failed aws-cloud-controller-manager Helm release
  └── Wait for node Ready condition
```

**Key Technical Detail: IMDS Token-Based Metadata**

The script uses IMDSv2 token-based metadata retrieval, not the deprecated IMDSv1 endpoint:

```bash
TOKEN=$(curl -sX PUT http://169.254.169.254/latest/api/token \
  -H X-aws-ec2-metadata-token-ttl-seconds:21600)
PRIVATE_IP=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" \
  http://169.254.169.254/latest/meta-data/local-ipv4)
```

This is required because the EC2 instances have `HttpTokens: required` (IMDSv2 enforced) — a security hardening measure applied at the CDK stack level.

### 6.2 `cluster-health.sh` — Quick Cluster Snapshot

**File**: 60 lines | **Purpose**: Immediate cluster state overview

```bash
#!/bin/bash
# Five-command cluster snapshot — useful as the first step in any incident response
kubectl get nodes -o wide
kubectl top nodes
kubectl get pods -A --sort-by='.metadata.namespace' | grep -v Running
kubectl get pods -n argocd
argocd app list --grpc-web 2>/dev/null || echo "ArgoCD not accessible"
```

**Philosophy**: Deliberately simple. When something is wrong with the cluster, the last thing you want is a 1,700-line diagnostic script. You want a 60-line snapshot that runs in 5 seconds and tells you:

- Are all nodes `Ready`?
- Is anything using excessive memory/CPU?
- Are any pods not `Running` or `Completed`?
- Is ArgoCD healthy?

The output is a starting point. If something looks wrong, you reach for `just diagnose`.

---

## 7. Knowledge Base Tooling — `scripts/kb-drift-check.py`

**File**: 261 lines | **Language**: Python 3 | **Purpose**: CI-integrated Knowledge Base drift detection

**The Problem It Solves**

The project maintains a `knowledge-base/` directory of documentation that describes infrastructure decisions, patterns, and configurations. When the infrastructure changes (e.g., a new CDK stack is added, networking is reconfigured), the KB documents can become stale — describing an architecture that no longer exists.

**How It Works**

The `.kb-map.yml` file maps code path patterns to KB document paths:

```yaml
mappings:
  - name: "Networking & VPC"
    code_paths:
      - "infra/lib/stacks/networking/**"
    kb_docs:
      - "infrastructure/networking_and_edge.md"

  - name: "Kubernetes Monitoring"
    code_paths:
      - "infra/lib/stacks/kubernetes/observability-stack.ts"
      - "kubernetes-app/monitoring/**"
    kb_docs:
      - "monitoring/kubernetes_monitoring_stack.md"
```

The script runs `git diff --name-only origin/main...HEAD` to get changed files, then cross-references them against the KB map. If a code file changes but its corresponding KB document doesn't, the script emits a warning.

**Dual-Mode Output**

```python
is_ci = os.environ.get('GITHUB_ACTIONS') == 'true'

if is_ci:
    print(f'::warning file=knowledge-base/{doc}::KB document may be stale.')
else:
    print(f'  📝 {doc}')
    for reason in reasons:
        print(f'      ← {reason}')
```

In CI, it uses GitHub Actions [annotation syntax](https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/workflow-commands-for-github-actions#setting-a-warning-message) (`::warning::`) which causes the warning to appear directly in the pull request diff view. Locally, it prints human-readable output.

**PyYAML-Free Fallback**

The script detects whether PyYAML is available and falls back to a minimal custom parser if not:

```python
try:
    import yaml
except ImportError:
    yaml = None  # Triggers custom parser

def parse_kb_map_simple(content: str) -> list[dict]:
    # Minimal YAML parser for CI environments without PyYAML installed
```

This ensures the script runs in GitHub Actions' default Python environment without requiring a `pip install` step.

---

## 8. Cross-Cutting Design Patterns

### Pattern 1: The Diagnostic-First Principle

Every operational script follows a "diagnose before acting" pattern:

```
Read → Analyse → Report → (optionally) Remediate
```

Scripts that can remediate (`--fix`, `--dry-run`) always run the full diagnostic first and abort if the diagnosis indicates the environment is unsafe for repair (e.g., instance unreachable, multiple simultaneous failures).

### Pattern 2: Typed AWS SDK v3 with Client Factory

All scripts use AWS SDK v3 (modular packages), not v2. This is significant because:

- Tree-shaking: Only the specific SDK modules used are bundled (e.g., `@aws-sdk/client-ssm`, not `aws-sdk`)
- TypeScript generics: Response objects are fully typed — no `any` casts needed for response parsing
- Promise-native: No callback hell, no `.promise()` wrapper

The **client factory pattern** in `control-plane-troubleshoot.ts` groups all client instantiation:

```typescript
function createClients(region, credentials): { ssm, ec2, asg, cw } {
  const config = { region, credentials };
  return {
    ssm: new SSMClient(config),
    ec2: new EC2Client(config),
    asg: new AutoScalingClient(config),
    cw:  new CloudWatchLogsClient(config),
  };
}
```

This makes the credential/region configuration a single concern, and makes the `createClients()` function trivially mockable in unit tests.

### Pattern 3: Explicit Error Typing

All SDK errors are caught with typed casts:

```typescript
} catch (error) {
  checks.push({
    name: 'EC2: Instance lookup',
    passed: false,
    detail: `Failed: ${(error as Error).message}`,
    severity: 'critical',
  });
}
```

This avoids `unknown` errors being silently swallowed and ensures every error surfaces in the diagnostic output.

### Pattern 4: Human-Readable Duration Formatting

Both `ssm-automation.ts` and `control-plane-troubleshoot.ts` implement `formatDuration()`:

```typescript
function formatDuration(start: Date, end?: Date): string {
  const ms = (end ?? new Date()).getTime() - start.getTime();
  const totalSeconds = Math.round(ms / 1000);
  if (totalSeconds < 60) return `${totalSeconds}s`;
  const mins = Math.floor(totalSeconds / 60);
  const secs = totalSeconds % 60;
  return secs > 0 ? `${mins}m ${secs}s` : `${mins}m`;
}
```

This is duplicated between the two files (rather than in `lib/`) because each file has slightly different needs for when `end` is `undefined`. An improvement would be to move this to `lib/` with an optional `end` parameter — it's a known technical debt item.

### Pattern 5: Pagination via `do...while`

All AWS API calls that return paginated results use the `do...while` loop pattern:

```typescript
let nextToken: string | undefined;
do {
  const response = await client.send(new DescribeAutoScalingGroupsCommand({ NextToken: nextToken }));
  nextToken = response.NextToken;
  // process response.AutoScalingGroups
} while (nextToken);
```

This is consistent across all scripts, using `NextToken` (SSM, ASG, Lambda) or `Marker` (ELB) as appropriate per service.

---

## 9. Integration with CI/CD Pipelines

The scripting layer integrates with the CI/CD pipeline at four touch points:

### Touch Point 1: Pre-Deployment Validation (`ci.yml`)

```yaml
- name: Audit EBS volume lifecycle
  run: just ebs-audit --profile ci
  # Blocks deployment if etcd volume has DeleteOnTermination: true

- name: Check KB drift
  run: python3 scripts/kb-drift-check.py --base origin/main
  # Warns (never blocks) when KB docs may be stale
```

### Touch Point 2: Post-Deployment Verification (`_deploy-kubernetes.yml`)

```yaml
- name: Verify SSM parameter publication
  run: just verify-ssm ${{ inputs.stack_name }}
  # Checks that the deployed stack published its expected SSM output parameters

- name: Run integration tests
  run: just test-integration
  # Reads SSM parameters and makes live AWS API calls to verify deployed resources
```

### Touch Point 3: Incident Response Automation (`_deploy-ssm-automation.yml`)

When an SSM Automation dispatch fails (non-zero exit from the polling logic):

```yaml
- name: Diagnose SSM failure
  if: failure()
  run: |
    npx tsx scripts/local/ssm-automation.ts \
      --status Failed \
      --last 1 \
      --since 1h \
      --profile ci
  # Prints full step-level failure output to the GitHub Actions log
```

### Touch Point 4: KB Sync (`/kb-sync` workflow)

The `/kb-sync` workflow invokes `kb-drift-check.py` with `--base HEAD~1` to check whether the current commit's code changes necessitate KB updates, then commits any new KB documents generated during the session.

---

## 10. Summary & Assessment

### Strengths

| Area | Assessment |
|------|-----------|
| **Operational Coverage** | Every known failure mode has a corresponding diagnostic and, in most cases, an automated repair script |
| **Type Safety** | All TypeScript scripts use `strict: true` with no `any` casts in production paths |
| **Auth Abstraction** | `resolveAuth()` provides seamless switching between OIDC (CI) and named profiles (local) without any `if (GITHUB_ACTIONS)` branches in application code |
| **Structured Output** | The `logger.ts` system provides consistent, parseable diagnostic output across all 11 scripts |
| **Justfile API Stability** | Recipe names are stable interfaces — CI workflows never need updating when underlying commands change |
| **Documentation Density** | Every public function has full JSDoc with `@param`, `@returns`, `@throws` — the scripts are self-documenting |

### Known Weaknesses

| Area | Issue | Resolution Path |
|------|-------|-----------------|
| **`formatDuration` Duplication** | Copied between `ssm-automation.ts` and `control-plane-troubleshoot.ts` | Move to `scripts/lib/time.ts` |
| **`asg-audit.ts` typo** | `listParemeters` (misspelled) | Rename to `listParameters` in a cleanup PR |
| **No unit tests for scripts** | The `scripts/` directory has no `*.test.ts` files | Add Jest tests with AWS SDK mocking via `@aws-sdk/client-mock` |
| **Shell scripts lack `--dry-run`** | `fix-control-plane-cert.sh` executes immediately — dangerous in wrong context | Add `DRY_RUN=1` environment variable check |
| **`kb-drift-check.py` in Python** | Mixed language (Python in a TypeScript monorepo) creates toolchain friction | Low priority — the script is simple enough to maintain as-is |

### Overall Assessment

**9/10** — The scripting layer represents a mature, purpose-built operational toolchain. The combination of a stable `justfile` API, a shared TypeScript library, and purpose-built diagnostic scripts eliminates the most common failure modes in infrastructure operations: operator confusion, missing context, and time-consuming manual AWS Console navigation.

The scripts are not general-purpose tools — they are deeply specific to this project's architecture (SSM-bootstrapped Kubernetes on ASG-managed EC2 with etcd on EBS). This specificity is a strength, not a weakness: each script embeds deep institutional knowledge about the system's failure modes and the exact steps required to repair them.

The `justfile` as the CLI contract ensures that this institutional knowledge is accessible via a single `just --list` command, regardless of whether you are a developer who worked on the project six months ago or a CI runner with no institutional memory at all.

---

*This document is part of the Infrastructure Architectural Review Series.*  
*Related documents: `devops_cicd_architecture_review.md` · `infra_tests_architecture_review.md` · `kubernetes_observability_report.md`*
