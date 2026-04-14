---
title: Poll Loop Pattern (Step Functions + SSM)
type: pattern
tags: [aws, step-functions, ssm, pattern, orchestration]
sources: [raw/step-function-runtime-logging.md]
created: 2026-04-13
updated: 2026-04-13
---

# Poll Loop Pattern

[[aws-step-functions|Step Functions]] has no native SSM command waiter (`sfnTasks.SsmRunCommand.waitForCompletion()` does not exist in CDK). The [[k8s-bootstrap-pipeline]] implements a custom poll loop for SSM Run Command completion.

## The Pattern

```
sendCommand → Wait 30s → getCommandInvocation → Choice:
  status == "InProgress" → loop back to Wait
  status == "Success"    → continue to next state
  otherwise (TimedOut, Failed, Cancelled) → Fail state with structured error
```

## CDK Implementation

```typescript
const startExec = new sfnTasks.CallAwsService(this, `${id}Start`, {
  service: "ssm",
  action: "sendCommand",
  parameters: {
    DocumentName: runnerDocName,
    InstanceIds: [JsonPath.stringAt("$.router.instanceId")],
  },
});

const pollStatus = new sfnTasks.CallAwsService(this, `${id}Poll`, {
  service: "ssm",
  action: "getCommandInvocation",
});

const choice = new sfn.Choice(this, `${id}Choice`)
  .when(sfn.Condition.stringEquals("$.status", "InProgress"), waitState)
  .when(sfn.Condition.stringEquals("$.status", "Success"), continueState)
  .otherwise(failState);
```

## Configuration

- **Poll interval:** 30 seconds
- **Max retries:** 60 (30 minutes total for control plane bootstrap)
- **Timeout states:** `TimedOut`, `Failed`, `Cancelled` all route to `Fail` with structured error

## Why Not Alternatives

- **`aws:waitForAwsResourceProperty`** (SSM Automation) has a 2-hour hard limit
- **Lambda-based polling** reintroduces Lambda timeout constraints (15 min)
- **Step Functions `.waitForTaskToken`** requires the SSM script to call back — too coupled

## Related Pages

- [[aws-step-functions]] — where this pattern is used
- [[k8s-bootstrap-pipeline]] — project context
- [[event-driven-orchestration]] — the broader orchestration pattern
