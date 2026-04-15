# Self-Healing Agent — LLM System Design Review

**Scope:** `infra/lib/stacks/self-healing/`, `bedrock-applications/self-healing/src/`
**Date:** 2026-04-15
**Reviewer:** Antigravity

---

## Table of Contents

1. [System Design Pattern](#1-system-design-pattern)
2. [Architecture Overview](#2-architecture-overview)
3. [How the Model is Called](#3-how-the-model-is-called)
4. [The System Prompt](#4-the-system-prompt)
5. [The Dynamic Prompt Builder](#5-the-dynamic-prompt-builder)
6. [Tool Discovery — MCP Gateway Integration](#6-tool-discovery--mcp-gateway-integration)
7. [The Agentic Loop](#7-the-agentic-loop)
8. [Knowledge Base — Does This System Use One?](#8-knowledge-base--does-this-system-use-one)
9. [Session Memory (S3-backed Episodic Store)](#9-session-memory-s3-backed-episodic-store)
10. [Security Analysis](#10-security-analysis)
11. [Cost Monitoring & FinOps](#11-cost-monitoring--finops)
12. [Prompt Engineering & Evolvability](#12-prompt-engineering--evolvability)
13. [Relevant Gaps & Recommendations](#13-relevant-gaps--recommendations)
14. [Adaptation & Reasoning Techniques Review](#14-adaptation--reasoning-techniques-review)
15. [Full Gap Summary](#15-full-gap-summary)

---

## 1. System Design Pattern

### Pattern: **Reactive Autonomous Agent with MCP Tool-Use Loop**

The self-healing agent is a fundamentally different pattern to the two previously reviewed systems:

| Feature | Article Pipeline | Chatbot | **Self-Healing Agent** |
|---|---|---|---|
| Pattern | Deterministic Workflow Agent | Managed RAG Agent | **Reactive Autonomous Agent** |
| Orchestration | Step Functions state machine | Bedrock managed runtime | **Self-managed agentic loop in Lambda** |
| Model API | `ConverseCommand` | `InvokeAgentCommand` | **`ConverseCommand` + tool_use loop** |
| Tools | None (direct agents) | None (KB retrieval built-in) | **6 MCP tools via AgentCore Gateway** |
| Knowledge Base | None used | Bedrock KB + Pinecone | **None — uses live infrastructure APIs** |
| Trigger | API Gateway | API Gateway | **EventBridge (CloudWatch Alarms)** |
| Prompt Source | Runtime-built, per-invocation | Deploy-time, static instruction | **Deploy-time system + runtime event prompt** |
| Determinism | High (fixed steps) | Medium (RAG-grounded) | **Low — model chooses tool sequence** |

### What "Reactive Autonomous Agent" Means

This pattern is fundamentally different from both previous systems:

- **Reactive**: Triggered by an external signal (CloudWatch Alarm → EventBridge). There is no human initiating a conversation.
- **Autonomous**: The model itself decides which tools to call, in what order, and when to stop. There is no state machine defining the remediation path.
- **Goal-directed**: The model is given an objective ("investigate this alarm and remediate if appropriate") and is free to explore the tool space to achieve it.

This is the most architecturally advanced and highest-risk LLM design in the portfolio. The model has real, write-access tools that can trigger Step Functions executions on production infrastructure.

---

## 2. Architecture Overview

```
CloudWatch Alarm → EventBridge Rule
                        │
                        ▼
              ┌─────────────────────┐
              │  Self-Healing Agent  │  (Lambda, NODEJS_22_X)
              │  ConverseCommand     │
              │  + tool_use loop     │
              └────────┬────────────┘
                       │
         ┌─────────────┼──────────────┐
         │             │              │
         ▼             ▼              ▼
   ┌──────────┐  ┌──────────┐  ┌──────────────┐
   │ S3 Mem.  │  │  Bedrock │  │  AgentCore   │
   │ (S3 R/W) │  │  Claude  │  │  Gateway     │
   │ sessions/│  │  Sonnet  │  │  (MCP 2025)  │
   └──────────┘  └──────────┘  └──────┬───────┘
                                       │
                  ┌────────────────────┼───────────────────┐
                  ▼                    ▼                    ▼
           ┌──────────┐        ┌────────────┐     ┌──────────────────┐
           │ diagnose │        │ check-node │     │ remediate-node   │
           │  -alarm  │        │  -health   │     │  -bootstrap      │
           │ (Lambda) │        │  (Lambda)  │     │  (Lambda)        │
           └──────────┘        └────────────┘     └──────────────────┘
                  │                    │                    │
                  ▼                    ▼                    ▼
           CloudWatch           SSM + kubectl       Step Functions SFN
           DescribeAlarms       on control plane    StartExecution

          + analyse-cluster-health (K8sGPT)
          + get-node-diagnostic-json (run_summary.json)
```

### Gateway Authentication Model

Every tool invocation is M2M-authenticated. The agent Lambda:
1. Calls `cognito-idp:DescribeUserPoolClient` at cold start to retrieve the client secret
2. Exchanges `client_id:client_secret` for a Cognito JWT via the `client_credentials` flow
3. Caches the JWT; refreshes 60s before expiry
4. Sends `Authorization: Bearer <token>` with every MCP Gateway call (tool discovery + invocation)

---

## 3. How the Model is Called

The model is invoked via the **Bedrock `ConverseCommand` API** — the same low-level API used by the article pipeline, not the managed `InvokeAgentCommand` used by the chatbot.

```typescript
// index.ts:726
const response = await bedrock.send(new ConverseCommand({
    modelId: EFFECTIVE_MODEL_ID,   // Application Inference Profile ARN
    system: systemPrompt,          // Static multi-block system instruction
    messages,                      // Accumulating conversation turns
    toolConfig,                    // All discovered MCP tool definitions
}));
```

**Model**: `eu.anthropic.claude-sonnet-4-6` (cross-region EU inference profile)

**Invocation target resolution** (index.ts:57):
```typescript
const EFFECTIVE_MODEL_ID = process.env.INFERENCE_PROFILE_ARN ?? FOUNDATION_MODEL;
```
The Application Inference Profile ARN takes precedence over the base model ID. This enables cost attribution per pipeline in AWS Cost Explorer and means the IAM policy must cover three resource ARNs:
1. The Application Inference Profile ARN (primary)
2. The cross-region inference profile (account-scoped)
3. The foundation model ARN in any region (cross-region routing target)

**No streaming**: `InvokeModel` (synchronous) not `InvokeModelWithResponseStream` is the primary action — the loop is turn-based, not streamed.

**No Extended Thinking**: Unlike the article pipeline, there is no `additionalModelRequestFields.thinking` configuration. The model reasons natively with tool planning.

---

## 4. The System Prompt

The system prompt is **deploy-time injectable**, passed as an environment variable:

```typescript
// agent-stack.ts:191
environment: {
    SYSTEM_PROMPT: props.systemPrompt,
    // ...
}
```

```typescript
// index.ts:59, 711
const SYSTEM_PROMPT = process.env.SYSTEM_PROMPT ?? 'You are an infrastructure remediation agent.';
const systemPrompt: SystemContentBlock[] = [{ text: SYSTEM_PROMPT }];
```

### What the System Prompt Contains

The actual system prompt value is set in the CDK factory (not visible in the reviewed files — it is a prop). The fallback (`'You are an infrastructure remediation agent.'`) reveals that the production prompt is passed at deploy time. What the architecture implies the prompt should contain:

1. **Role definition**: What the agent is (SRE remediation agent for a Kubernetes platform)
2. **Behavioural constraints**: When to act vs. when to only report
3. **Safety boundary**: When `DRY_RUN=true`, propose only; when `false`, execute
4. **Tool ordering guidance**: Diagnose before remediate (the bootstrap guidance block reinforces this)
5. **Failure classification**: How to distinguish transient vs. permanent failures

The static system prompt is intentionally **minimal and generic**. The heavy lifting of context-specific guidance is done by the **runtime prompt builder** and the **bootstrap diagnostic guidance block** injected dynamically.

---

## 5. The Dynamic Prompt Builder

This is one of the most sophisticated design decisions in the system. The `buildPrompt()` function constructs a rich, context-aware natural language prompt at runtime:

```typescript
// index.ts:254–295
function buildPrompt(event: AlarmEvent): string {
    const dryRunNote = DRY_RUN
        ? 'DRY RUN MODE: Propose remediation steps but do NOT execute them.'
        : 'Execute the appropriate remediation steps.';

    if (source === 'aws.cloudwatch') {
        const bootstrapGuidance = isBootstrapAlarm(alarmName)
            ? buildBootstrapDiagnosticGuidance()      // ← Injected conditionally
            : '';

        return [
            'A CloudWatch Alarm has fired.',
            `Alarm: ${alarmName}`,
            `New State: ${newState}`,
            `Reason: ${reason}`,
            dryRunNote,
            bootstrapGuidance,
            `Full event detail:\n${JSON.stringify(detail, null, 2)}`,
        ].filter(Boolean).join('\n');
    }
    // ...
}
```

### Bootstrap Diagnostic Guidance Block

When the alarm name matches known bootstrap patterns (`bootstrap-orchestrator`, `ssm-automation`, `step-function`, `k8s-bootstrap`), the agent injects a step-by-step diagnostic workflow:

```
─── SSM BOOTSTRAP FAILURE DETECTED ───
Follow this diagnostic workflow:

1. DIAGNOSE: Use `get_node_diagnostic_json` to fetch the run_summary.json
2. CLASSIFY: Determine if TRANSIENT (→ retry) or PERMANENT (→ report only)
3. REMEDIATE (transient only): Use `remediate_node_bootstrap`
4. VERIFY: Use `check_node_health` then `analyse_cluster_health`
───────────────────────────────────────
```

**Architectural significance**: This is a **hybrid design** — the LLM is autonomous, but for well-understood failure classes, the prompt injects a near-deterministic workflow. The model doesn't have to invent the diagnostic sequence from scratch; it is guided. This is a strong design choice that reduces token consumption and improves reliability.

### Previous Session Context Injection

If a previous session exists in S3 for this alarm, its outcome is appended:

```typescript
// index.ts:1009–1026
function buildPreviousSessionContext(session: SessionRecord): string {
    return [
        '─── PREVIOUS REMEDIATION ATTEMPT (do NOT repeat the same actions) ───',
        `Tools called: ${session.toolsCalled.join(', ')}`,
        `Outcome:`,
        session.result.slice(0, 2000),  // ← Truncated to 2000 chars
        '───────────────────────────────────────',
    ].join('\n');
}
```

This is a **primitive episodic memory mechanism**: the model is aware of what was previously attempted and is explicitly instructed not to repeat it. This prevents remediation loops.

---

## 6. Tool Discovery — MCP Gateway Integration

### Dynamic vs. Static Tools

This is a key architectural differentiator. Unlike every other agentic system that hardcodes tool definitions, this agent **dynamically discovers tools** at invocation time:

```typescript
// index.ts:408–463
async function discoverTools(): Promise<AgentTool[]> {
    // 1. Call MCP Gateway tools/list endpoint (authenticated)
    // 2. Transform MCP tool specs → Bedrock Tool format
    // 3. Fall back to getDefaultTools() if unavailable
}
```

**What `tools/list` returns**: The AgentCore Gateway (L2 construct, MCP 2025-03-26) exposes all registered Lambda targets via the MCP protocol's tool discovery endpoint. The agent receives the same 6 tools defined in the gateway stack, but they arrive at runtime — the Lambda code does not need to change if a new tool is added to the Gateway.

**Default tools (fallback)**: 6 hardcoded definitions in `getDefaultTools()` — these match exactly what the Gateway registers. The fallback exists for local testing without Gateway connectivity.

### The 6 Tools

| Tool Name | Lambda | What It Does | Write Access? |
|---|---|---|---|
| `diagnose_alarm` | `tool-diagnose-alarm` | `cloudwatch:DescribeAlarms` + `GetMetricData` | ❌ Read-only |
| `check_node_health` | `tool-check-node-health` | `kubectl get nodes` via SSM SendCommand on CP | ❌ Read-only |
| `analyse_cluster_health` | `tool-analyse-cluster-health` | K8sGPT + kubectl on CP via SSM | ❌ Read-only |
| `get_node_diagnostic_json` | `tool-get-node-diagnostic` | Reads `run_summary.json` via SSM | ❌ Read-only |
| `remediate_node_bootstrap` | `tool-remediate-bootstrap` | `states:StartExecution` on SFN | ✅ **WRITE** |
| `ebs_detach` | _(fallback only — no Lambda in gateway)_ | EBS volume detach | ✅ **WRITE** |

**Important observation**: `ebs_detach` is defined in `getDefaultTools()` but **does not have a registered Lambda target** in the gateway stack. It exists in the fallback definition but would never be invocable via the live Gateway (there is no corresponding `addLambdaTarget`). This is an inconsistency.

### MCP Protocol

```
POST https://<gateway-url>
Authorization: Bearer <cognito-jwt>
Content-Type: application/json

{ "jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": "discover" }
{ "jsonrpc": "2.0", "method": "tools/call", "params": { "name": "...", "arguments": {...} }, "id": "..." }
```

---

## 7. The Agentic Loop

The loop runs inside the Lambda function — there is no Step Functions state machine managing it. This is a pure LLM-driven loop:

```
┌─────────────────────────────────────────────────────┐
│ runAgentLoop(prompt, tools)                         │
│                                                     │
│  messages = [{ role: 'user', content: [prompt] }]  │
│                                                     │
│  for iteration in 0..MAX_ITERATIONS (10):           │
│    1. ConverseCommand → response                    │
│    2. Append assistant response to messages         │
│    3. if stopReason === 'tool_use':                 │
│       a. Extract all toolUse blocks                 │
│       b. invokeTool(name, input) → result           │
│       c. Append toolResults as user message         │
│       d. continue                                   │
│    4. else (stopReason === 'end_turn'):             │
│       return { text, toolsCalled }                  │
│                                                     │
│  MAX_ITERATIONS exceeded → return WARN message      │
└─────────────────────────────────────────────────────┘
```

**Token tracking per iteration**: Input and output tokens are logged after every `ConverseCommand` call:
```typescript
log('INFO', `Iteration ${iteration} completed`, {
    inputTokens: response.usage?.inputTokens,
    outputTokens: response.usage?.outputTokens,
});
```

**Conversation history accretion**: The `messages[]` array accumulates every turn. On a 10-iteration loop with 6 tools this could become very large. There is no conversation truncation.

**Hard stop at 10 iterations**: `MAX_ITERATIONS = 10` — after 10 Bedrock calls the loop aborts with a warning. This is the primary runaway execution guard alongside the token budget alarm.

---

## 8. Knowledge Base — Does This System Use One?

**No. This system does not use a Bedrock Knowledge Base or any vector store.**

This is an important architectural distinction. Where the chatbot uses RAG against a Pinecone-backed KB to answer questions about portfolio documentation, the self-healing agent uses **live infrastructure APIs** as its information source:

| Information Need | How Resolved |
|---|---|
| What failed? | EventBridge event payload (`alarmName`, `reason`) |
| What is the alarm configured to watch? | `diagnose_alarm` tool → `cloudwatch:DescribeAlarms` |
| Did the node join the cluster? | `check_node_health` tool → `kubectl get nodes` via SSM |
| What step failed in bootstrap? | `get_node_diagnostic_json` tool → `run_summary.json` |
| Is the cluster healthy after remediation? | `analyse_cluster_health` tool → K8sGPT / kubectl |

The model's "knowledge" comes entirely from tool responses — it is grounded in real-time infrastructure state, not a static document corpus. This is the correct design for an operational remediation agent.

### Why No KB Is Correct Here

A KB would be inappropriate because:
- Infrastructure state changes by the minute — a KB snapshot would be stale
- Remediation requires **current** configuration, not documentation
- The failure classification taxonomy (`AMI_MISMATCH`, `KUBEADM_FAIL`, etc.) is injected directly into the prompt via `buildBootstrapDiagnosticGuidance()`, not retrieved from a KB
- The tools themselves are the "information retrieval" layer

---

## 9. Session Memory (S3-backed Episodic Store)

The agent implements a **simple episodic memory** via S3:

**Key format**: `sessions/{sanitised-alarm-name}/{ISO-timestamp}.json`

**Session record**:
```typescript
interface SessionRecord {
    alarmName: string;
    timestamp: string;        // ISO
    correlationId: string;
    prompt: string;           // Full prompt sent to the model
    toolsCalled: string[];    // Deduplicated list
    result: string;           // Agent's final text response
    dryRun: boolean;
}
```

**Lifecycle**: S3 lifecycle rule expires objects after `memoryRetentionDays` (default: 30 days).

**Load logic**: Lists up to 10 objects, sorts descending by key (ISO timestamps sort lexicographically), loads the most recent. Only the **most recent** session is loaded — there is no multi-session summarisation.

**Write logic**: Saved after `runAgentLoop` completes, whether the loop succeeded or failed.

This is functionally a **primitive episodic memory** for the specific pattern of: "This alarm has fired before. Here's what was tried. Don't do it again."

---

## 10. Security Analysis

### 10.1 Strengths

| Control | Implementation |
|---|---|
| **EventBridge self-exclusion** | `anything-but: { prefix: "${namePrefix}-agent" }` prevents the agent's own token-budget alarm from triggering itself |
| **DRY_RUN flag** | Deploy-time boolean (`enableDryRun: true` by default) prevents write tool execution |
| **Cognito M2M auth** | Every Gateway call requires a valid JWT from the `client_credentials` flow |
| **SQS DLQ** | Failed agent invocations are captured rather than silently lost |
| **Lambda retry: 2** | EventBridge target retries twice on timeout/error before DLQ |
| **Reserved concurrency** | Optional cap on simultaneous Bedrock invocations |
| **Token budget alarm** | CloudWatch alarm fires if input+output tokens > `tokenBudgetPerHour` in 1 hour |
| **Application Inference Profile** | Per-pipeline cost attribution and spending visibility |
| **S3 session memory** | Encrypted (`S3_MANAGED`), public access blocked, SSL enforced |
| **DLQ encryption** | `SQS_MANAGED` encryption on the dead letter queue |
| **Max 10 iterations** | Hard cap prevents infinite tool-use loops |

### 10.2 Security Gaps

---

**SH-S1: SYSTEM_PROMPT is an environment variable — visible in Lambda configuration**

```typescript
// agent-stack.ts:191
environment: {
    SYSTEM_PROMPT: props.systemPrompt,  // ← Plain Lambda env var
}
```

Lambda environment variables are visible to anyone with `lambda:GetFunction` IAM permission. If the system prompt contains behavioural constraints, security directives, or role boundaries, they are fully readable by any IAM principal with that permission. This is the same risk noted in the chatbot review for API keys.

**Recommendation**: Store the system prompt in SSM Parameter Store (SecureString or Standard) and load it at cold start via `ssm:GetParameter`. This adds one cold-start call but protects the prompt configuration.

---

**SH-S2: Tool IAM policies use wildcard resources (`resources: ['*']`) for SSM and EC2**

```typescript
// gateway-stack.ts:243
actions: ['ssm:SendCommand', 'ssm:GetCommandInvocation'],
resources: ['*'],
```

Three tool Lambdas (`check-node-health`, `analyse-cluster-health`, `get-node-diagnostic-json`) have `ssm:SendCommand` on `*`. SSM SendCommand with `*` resources allows running arbitrary commands on **any** SSM-managed instance in the account, not just K8s nodes. The CDK-Nag suppressions acknowledge this as design-required (instance IDs are dynamic), but it remains a blast radius concern.

**Recommendation**: Scope by tag condition. SSM SendCommand supports `aws:ResourceTag` conditions:
```typescript
new iam.PolicyStatement({
    actions: ['ssm:SendCommand'],
    resources: ['*'],
    conditions: {
        StringEquals: {
            'ssm:resourceTag/project': 'k8s-cluster',
        },
    },
})
```
This restricts SendCommand to instances tagged with the cluster project tag, preventing lateral movement to unrelated EC2 instances.

---

**SH-S3: `ebs_detach` tool defined in fallback but has no Gateway Lambda registration**

The default tools include `ebs_detach` with a write operation (EBS volume detach), but there is no `addLambdaTarget` in `gateway-stack.ts` for this tool. If the model selects this tool via the fallback path (when Gateway is unavailable), `invokeTool` will POST to the Gateway which will return an error. The model may retry or hallucinate a response.

**Risk**: Inconsistency between the model's tool inventory and the Gateway's actual tool registry creates undefined behaviour. The model is told it has a tool it cannot actually execute.

**Recommendation**: Either register `ebs_detach` as a full Gateway Lambda target, or remove it from `getDefaultTools()`.

---

**SH-S4: In-memory deduplication cache does not survive Lambda cold starts**

```typescript
// index.ts:199
const deduplicationCache = new Map<string, number>();
```

The dedup cache is module-level — it persists across warm invocations within the same container, but is cleared on cold start. If two identical EventBridge events arrive during a cold start, both will pass the dedup check. EventBridge retries on Lambda throttling could trigger duplicate remediations.

**Recommendation**: For production hardening, move deduplication to DynamoDB with a conditional write (TTL-indexed item). This provides true cross-invocation idempotency.

---

**SH-S5: No prompt injection validation on the EventBridge event payload**

The full `JSON.stringify(detail, null, 2)` of the CloudWatch event is injected into the prompt:

```typescript
// index.ts:282
`Full event detail:\n${JSON.stringify(detail, null, 2)}`,
```

If an attacker can control the CloudWatch alarm `reason` field (e.g., via a synthesised alarm or a namespace injection via alarm description), they could inject text that attempts to manipulate the model's behaviour. This is a **prompt injection** surface.

**Recommendation**: Sanitise or truncate the injected payload:
1. Limit `JSON.stringify` output to a max character count (e.g., 3000 chars)
2. Strip or escape markdown/instruction-like patterns from the `reason` field before injection
3. Consider wrapping the event detail in an XML-like boundary tag that the system prompt instructs the model to treat as untrusted data

---

**SH-S6: No WAF or rate limiting on the EventBridge trigger**

Unlike the chatbot, there is no API Gateway in the ingress path — the trigger is a direct EventBridge rule. Alarms in AWS cannot be rate-limited at the EventBridge level. An alarm storm (many alarms firing simultaneously) will trigger parallel agent invocations that each call Bedrock:
- Concurrency risk: multiple expensive ConverseCommand calls running in parallel
- Token risk: each invocation with MAX_ITERATIONS=10 could consume 100K+ tokens

The token budget alarm catches this after the fact, but by then cost has already been incurred.

**Recommendation**: Implement an SQS queue between EventBridge and the Lambda:
```
EventBridge → SQS FIFO queue (with MessageDeduplicationId = alarmName#eventTime)
           → Lambda (concurrency = 1, batch size = 1)
```
This provides true rate limiting via SQS visibility timeout and prevents alarm storms from launching parallel Bedrock invocations.

---

**SH-S7: SNS remediation reports are unencrypted**

```typescript
// agent-stack.ts:365–374
NagSuppressions.addResourceSuppressions(this.reportsTopic, [{
    id: 'AwsSolutions-SNS2',
    reason: 'Remediation report topic — no sensitive data, default encryption sufficient',
}])
```

The remediation report published to SNS contains:
- The full CloudWatch alarm name
- Tool names called (revealing infrastructure topology)
- Correlation IDs
- Potentially the full agent response (including `run_summary.json` content with instance IDs)

This is infrastructure-sensitive data. Email subscribers receive this content in plaintext. If the email endpoint is breached, it reveals cluster topology and bootstrap failure patterns.

**Recommendation**: Enable KMS encryption on the SNS topic and redact instance IDs / internal ARNs from the published report.

---

## 11. Cost Monitoring & FinOps

This system has the **most complete FinOps implementation** of all three reviewed Bedrock systems. Assessment:

### 11.1 What Is Implemented

| Mechanism | Implementation |
|---|---|
| **Per-invocation token logging** | `inputTokens` + `outputTokens` logged after every `ConverseCommand` call (structured JSON) |
| **CloudWatch Metric Filters** | `MetricFilter` extracts `inputTokens` and `outputTokens` from log entries → custom namespace metrics |
| **Token Budget Alarm** | `CloudWatch.Alarm` on `InputTokens + OutputTokens` sum in 1-hour window; threshold configurable |
| **Application Inference Profile** | Per-pipeline cost attribution in AWS Cost Explorer (tagged: project, cost-centre, component) |
| **Reserved Concurrency** | Optional cap on simultaneous agent invocations (`reservedConcurrency` prop) |
| **DLQ for failed invocations** | Prevents retry storms from compounding cost |

### 11.2 FinOps Gaps

**SH-C1: Token budget alarm only fires AFTER cost is incurred**

The token budget alarm monitors a 1-hour window. A runaway agent invocation (10 iterations × 6 tools × large prompts) could consume 200K+ tokens before the alarm fires at end-of-hour. The alarm is a retrospective signal, not a real-time gate.

**Recommendation**: Add a per-invocation token limit enforced inside the loop:
```typescript
let totalTokensConsumed = 0;
const PER_INVOCATION_TOKEN_LIMIT = 50_000;

// After each ConverseCommand call
totalTokensConsumed += (response.usage?.inputTokens ?? 0) + (response.usage?.outputTokens ?? 0);
if (totalTokensConsumed > PER_INVOCATION_TOKEN_LIMIT) {
    log('WARN', 'Per-invocation token limit exceeded, aborting loop');
    break;
}
```

**SH-C2: Conversation history grows unboundedly — token cost compounds**

The `messages[]` array accumulates all turns. By iteration 8, the prompt includes: original prompt + 8 assistant turns + 8 tool result turns. The input token count grows quadratically with tool invocations. There is no conversation truncation or summarisation.

**Recommendation**: Implement a sliding window on the conversation history — keep the original user prompt, the system prompt, and the last N turns:
```typescript
const MAX_HISTORY_TURNS = 6; // Keep last 3 assistant+user pairs
if (messages.length > MAX_HISTORY_TURNS + 1) {
    messages.splice(1, messages.length - MAX_HISTORY_TURNS - 1);
}
```

**SH-C3: No Bedrock budget alarm (monthly spend cap)**

There is a per-hour token alarm but no monthly AWS Budgets alarm monitoring Bedrock spend for this pipeline. A sustained alarm storm over days could generate significant cost before the monthly report.

---

## 12. Prompt Engineering & Evolvability

### 12.1 How Prompts Are Currently Managed

The system prompt is a deploy-time prop — to change it, you update the CDK factory and redeploy. The runtime prompt is built entirely in `buildPrompt()` and `buildBootstrapDiagnosticGuidance()`.

### 12.2 Prompt Evolvability Assessment

| Dimension | Assessment |
|---|---|
| **System prompt changeability** | ⚠️ Requires CDK redeploy. No hot-swap mechanism. |
| **Bootstrap guidance changeability** | ⚠️ Hardcoded in `index.ts:645–670`. Requires code change + deploy. |
| **Alarm pattern detection** | ⚠️ Hardcoded array in `index.ts:619–624`. New alarm patterns require code change. |
| **Tool descriptions** | ✅ Tools are discovered dynamically from Gateway — tool descriptions can evolve without Lambda changes |
| **DRY_RUN toggle** | ✅ Environment variable — change requires re-deploy but no code change |
| **Previous session injection** | ✅ Automatic — evolves with alarm history |

### 12.3 Prompt Improvement Recommendations

**P1 — System prompt should define failure classification taxonomy**

The bootstrap guidance block defines `AMI_MISMATCH`, `KUBEADM_FAIL`, `CALICO_TIMEOUT` etc. These should also be defined in the system prompt so the model has a global understanding of the failure taxonomy, not only when a bootstrap alarm fires.

**P2 — Add few-shot examples for the two critical decision points**

The most important reasoning the model must do:
1. TRANSIENT or PERMANENT failure classification
2. Whether to call `remediate_node_bootstrap` or report-only

Both decisions have real consequences. Few-shot examples anchoring these decisions would reduce variance:
```
# Example: TRANSIENT failure
Failure code: S3_FORBIDDEN (bootstrap script download timed out)
Decision: TRANSIENT — S3 eventual consistency issue, safe to retry
Action: [remediate_node_bootstrap]

# Example: PERMANENT failure
Failure code: AMI_MISMATCH (instance AMI ID does not match expected)
Decision: PERMANENT — requires operator intervention, do NOT retry
Action: [report to operator]
```

**P3 — Bootstrap alarm pattern detection should be SSM-configurable**

```typescript
// index.ts:619–624
const BOOTSTRAP_ALARM_PATTERNS = [
    'bootstrap-orchestrator',
    'ssm-automation',
    'step-function',
    'k8s-bootstrap',
];
```

This array is hardcoded. When new alarm naming conventions are added, this code must be changed and redeployed. Consider loading the pattern list from SSM Parameter Store at cold start.

---

## 13. Relevant Gaps & Recommendations

### Priority Gaps

**SH-S1: System prompt in plaintext Lambda env var** 🔴 High — Security

**SH-S2: SSM SendCommand wildcard — no tag-based scope** 🔴 High — Security

**SH-S3: `ebs_detach` in fallback tools but no Gateway Lambda** 🟡 Medium — Reliability

**SH-S4: In-memory dedup cache lost on cold start** 🟡 Medium — Reliability

**SH-S5: Prompt injection via EventBridge event payload** 🔴 High — Security

**SH-S6: No SQS rate limiting between EventBridge and Lambda (alarm storms)** 🔴 High — Reliability + Cost

**SH-S7: SNS remediation reports unencrypted / infrastructure data in email** 🟡 Medium — Security

**SH-C1: No per-invocation token gate (budget alarm is post-hoc)** 🟡 Medium — Cost

**SH-C2: Conversation history grows unboundedly** 🟡 Medium — Cost + Reliability

**SH-C3: No monthly Bedrock budget alarm** 🟢 Low — Cost

---

## 14. Adaptation & Reasoning Techniques Review

---

### 14.1 Technique Assessment

---

#### A. What System Design Role Does Reasoning Play Here?

The self-healing agent is an **autonomous decision-maker**, not a generator or a responder. Every reasoning step directly influences a real-world action. The quality of the model's reasoning directly determines:
- Whether a transient failure is correctly classified (retry → success)
- Whether a permanent failure is correctly withheld from retry (prevent loop)
- Whether the correct tool is called in the correct order

Reasoning quality = operational reliability. This is the highest-stakes reasoning context in the portfolio.

---

#### B. Extended Thinking / Inference-Time Scaling

**Status: ❌ Absent — and notably absent given the use case.**

The article pipeline implements `additionalModelRequestFields.thinking` with an adaptive budget. The self-healing agent uses the same `ConverseCommand` API but does not enable Extended Thinking.

For an agent that must classify failure modes (TRANSIENT vs. PERMANENT) with real write consequences, Extended Thinking would:
- Allow the model to reason about failure patterns before committing to a tool selection
- Reduce false negatives (calling `remediate_node_bootstrap` on a permanent failure)

**Gap SH-R1 — Extended Thinking not enabled.** For the `remediate_node_bootstrap` tool specifically — the highest-risk write operation — a short thinking budget (1000–2000 tokens) before confirming the remediation decision would add a meaningful safety layer:

```typescript
// Before calling remediate_node_bootstrap, the model should think:
// "Is this failure code in the TRANSIENT class? Has the previous session
//  already attempted this? Is dry_run active?"
additionalModelRequestFields: {
    thinking: { type: 'enabled', budget_tokens: 2000 },
}
```

---

#### C. Chain-of-Thought (CoT) Prompting

**Status: ⚠️ Partial — implicit via bootstrap guidance, not explicit.**

The bootstrap guidance block injects a step-by-step diagnostic workflow (DIAGNOSE → CLASSIFY → REMEDIATE → VERIFY). This functions as **implicit CoT**: the model is guided through a reasoning chain by the prompt structure.

What is missing is **explicit CoT instruction** in the system prompt: "Before calling any remediation tool, reason about the failure class explicitly and state your classification."

**Gap SH-R2 — No explicit CoT instruction before write tool invocation.** Adding "Think step by step before calling any write tools" to the system prompt, along with a structured reasoning format, would surface the model's classification reasoning in the logs.

---

#### D. Self-Consistency / Multi-Sample

**Status: 🚫 Not applicable at this stage.**

Self-consistency (sampling the model N times and taking the majority vote) is not applicable in a reactive remediation loop where latency and cost matter more than response quality variance.

---

#### E. Sequential Revision / Self-Refinement

**Status: ⚠️ Partial — via session memory; no within-session revision.**

The S3 session memory provides **cross-invocation** self-refinement: the model sees what previous attempts did and is instructed not to repeat them. This is a form of episodic learning.

Within a single invocation, there is no **within-session revision**: the model cannot step back from a tool result and reconsider its approach. The loop is forward-only.

**Gap SH-R3 — No within-session self-reflection step.** After each tool result, rather than immediately continuing to the next tool call, the model could be prompted to summarise what it has learned:

```
user: [tool result for get_node_diagnostic_json]
user: "Based on this diagnostic result, what is your failure classification? 
       TRANSIENT or PERMANENT? Reason through it before proceeding."
```

This is a structured multi-turn revision pattern that prevents hasty tool chaining.

---

#### F. Search Against a Verifier

**Status: ⚠️ Partial — `check_node_health` acts as post-remediation verifier.**

The bootstrap guidance block instructs the model to call `check_node_health` after `remediate_node_bootstrap` to verify that the node joined the cluster. This is a **search-against-a-verifier** pattern: remediation → verification → report.

However:
- The verifier step is *suggested* in the prompt, not *enforced* by the loop
- The model could produce a `end_turn` response after calling `remediate_node_bootstrap` without verifying
- There is no retry mechanism if the verifier fails

**Gap SH-R4 — Verification step is advisory, not enforced.** The loop has no hard gate that requires a verification call before accepting a `end_turn` response.

---

#### G. Reward Modelling / Outcome Signal

**Status: ❌ Absent — no automated quality scoring on remediation outcomes.**

The session records in S3 contain the tools called and the model's final text response, but there is no structured outcome signal:
- Did the alarm clear after remediation? (CloudWatch `OK` state)
- How long did it take for the node to reach `Ready`?
- Did a second alarm for the same resource fire within 1 hour (remediation failure)?

**Gap SH-R5 — No remediation outcome tracking.** A CloudWatch Events rule listening for the same alarm transitioning from `ALARM → OK` after a self-healing invocation would provide the ground truth signal:

```typescript
// Outcome tracking pseudo-flow
// 1. On agent invocation: store { alarmName, correlationId, invokedAt } in DynamoDB
// 2. On alarm → OK: query DynamoDB for recent invocation, compute durationToResolve
// 3. Emit CloudWatch metric: RemediationSuccess=1 / RemediationFailure=1
// 4. Use as longitudinal quality signal for prompt evolution
```

Without this, you cannot know whether the self-healing agent is actually healing anything.

---

### 14.2 New Gaps from Reasoning Analysis

| # | Gap | Category | Severity | Effort |
|---|---|---|---|---|
| SH-R1 | Extended Thinking not enabled for high-stakes tool decisions | Inference-time reasoning | 🟡 Medium | Low |
| SH-R2 | No explicit CoT instruction before write tool invocation | CoT prompting | 🟡 Medium | Trivial |
| SH-R3 | No within-session self-reflection step after tool results | Self-refinement | 🟡 Medium | Low |
| SH-R4 | Verification step (`check_node_health`) advisory, not enforced | Search-against-verifier | 🔴 High | Medium |
| **SH-R5** | **No remediation outcome tracking — no signal whether agent fixed anything** | **Reward Modelling** | **🔴 High** | **Medium** |

---

## 15. Full Gap Summary

| # | Gap | Severity | Effort |
|---|---|---|---|
| SH-S1 | System prompt in plaintext Lambda env var | 🔴 High | Low |
| SH-S2 | SSM SendCommand wildcard — no tag-based scope | 🔴 High | Low |
| SH-S3 | `ebs_detach` in fallback tools, no Gateway Lambda | 🟡 Medium | Low |
| SH-S4 | In-memory dedup cache lost on cold start | 🟡 Medium | Medium |
| SH-S5 | Prompt injection surface via EventBridge payload | 🔴 High | Low |
| SH-S6 | No SQS rate limiting — alarm storms spawn parallel Bedrock calls | 🔴 High | Medium |
| SH-S7 | SNS remediation reports unencrypted, contain infra data | 🟡 Medium | Low |
| SH-C1 | No per-invocation token gate (budget alarm is post-hoc only) | 🟡 Medium | Low |
| SH-C2 | Conversation history grows unboundedly — compounding token cost | 🟡 Medium | Low |
| SH-C3 | No monthly Bedrock budget alarm | 🟢 Low | Trivial |
| SH-R1 | Extended Thinking not used for high-stakes classification decisions | 🟡 Medium | Low |
| SH-R2 | No explicit CoT instruction in system prompt before write tools | 🟡 Medium | Trivial |
| SH-R3 | No within-session self-reflection step after tool results | 🟡 Medium | Low |
| SH-R4 | Post-remediation verification step advisory, not loop-enforced | 🔴 High | Medium |
| **SH-R5** | **No outcome tracking — cannot measure whether remediation succeeded** | **🔴 High** | **Medium** |
