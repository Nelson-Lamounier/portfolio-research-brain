---
title: AWS Step Functions
type: tool
tags: [aws, step-functions, orchestration, serverless]
sources: [raw/step-function-runtime-logging.md]
created: 2026-04-13
updated: 2026-04-13
---

# AWS Step Functions

State machine service used in the [[k8s-bootstrap-pipeline]] to orchestrate SSM Run Command executions on EC2 instances. Chosen over Lambda chains, EventBridge Pipes, and CodePipeline (see [[adr-step-functions-orchestration]]).

## Why Step Functions Over Alternatives

| Requirement | Lambda chains | Step Functions |
|-------------|--------------|----------------|
| Conditional branching | Manual routing in code | Native `Choice` states with JSONPath |
| Parallel execution | No native support | Native `Parallel` state |
| Long-running tasks | 15-min Lambda hard limit | No timeout limit (bootstrap takes ~30 min) |
| Failure handling | Silent swallowed errors | `Catch` clauses with structured error messages |
| Observability | Custom logging only | Visual console shows every state transition |
| State passing | Manual parameter reads/writes | First-class JSON state machine context |

## Usage in This Project

### SM-A — Bootstrap Orchestrator

Defined in `infra/lib/constructs/ssm/bootstrap-orchestrator.ts`. Orchestrates cluster infrastructure:

```
InvokeRouter Lambda → UpdateInstanceId → BootstrapControlPlane (poll loop)
→ Parallel: RejoinGeneralPool + RejoinMonitoringPool → SUCCEED
```

### SM-B — Config Orchestrator

Defined in `infra/lib/constructs/ssm/config-orchestrator.ts`. Orchestrates application config injection:

```
ResolveControlPlane → DeployNextjs → DeployMonitoring → DeployStartAdmin
→ DeployAdminApi → DeployPublicApi → SUCCEED/FAIL
```

## Custom Poll Loop Pattern

Step Functions has no native SSM command waiter. The [[poll-loop-pattern]] is custom-built:

```
sendCommand → Wait 30s → getCommandInvocation → Choice:
  InProgress → loop back to Wait
  Success → continue
  Failed/TimedOut/Cancelled → Fail state
```

Up to 60 retries (30 min total) for the control plane bootstrap step.

## CDK Pattern

Uses `sfnTasks.CallAwsService` for direct SSM API calls:

```typescript
const startExec = new sfnTasks.CallAwsService(this, `${id}Start`, {
  service: "ssm",
  action: "sendCommand",
  parameters: {
    DocumentName: runnerDocName,
    InstanceIds: [JsonPath.stringAt("$.router.instanceId")],
  },
});
```

## Logging

| Log Group | Content |
|-----------|---------|
| `/aws/vendedlogs/states/k8s-dev-bootstrap-orchestrator` | SM-A state transitions (7-day retention) |
| `/aws/vendedlogs/states/k8s-dev-config-orchestrator` | SM-B state transitions (7-day retention) |

**Known gap:** SSM stdout is not embedded in Step Functions history. Cross-reference `CommandId` from state output against the SSM log group.

## Related Pages

- [[k8s-bootstrap-pipeline]] — project using Step Functions
- [[aws-ssm]] — execution layer called by Step Functions
- [[event-driven-orchestration]] — SM-A → EventBridge → SM-B
- [[poll-loop-pattern]] — custom SSM command polling
