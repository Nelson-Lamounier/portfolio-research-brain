# Infrastructure Testing Architecture — Deep-Dive Review

> **Document scope**: `infra/tests/` — 50 test files, ~8,000 lines of TypeScript.  
> **Audience**: Author (Nelson) and future contributors.  
> **Purpose**: Capture the "why" behind every testing decision, explain concepts implemented, and document the relationship between the test suite and the production `infra/` codebase.

---

## Table of Contents

1. [Overview & Purpose](#1-overview--purpose)
2. [The Testing Pyramid — Three Tiers](#2-the-testing-pyramid--three-tiers)
3. [Toolchain & Configuration](#3-toolchain--configuration)
   - 3.1 [jest.config.js — Unit Test Runner](#31-jestconfigjs--unit-test-runner)
   - 3.2 [jest.integration.config.js — Integration Runner](#32-jestintegrationconfigjs--integration-runner)
   - 3.3 [jest-setup.ts — Global Setup](#33-jest-setupts--global-setup)
   - 3.4 [jest-worker-setup.js — The Monorepo CWD Fix](#34-jest-worker-setupjs--the-monorepo-cwd-fix)
4. [The Fixture Layer — Shared Infrastructure](#4-the-fixture-layer--shared-infrastructure)
   - 4.1 [constants.ts — Centralised Magic Values](#41-constantsts--centralised-magic-values)
   - 4.2 [mock-resources.ts — Reusable AWS Stubs](#42-mock-resourcests--reusable-aws-stubs)
   - 4.3 [test-app.ts — Factory Helpers](#43-test-appts--factory-helpers)
   - 4.4 [assertions.ts — Shared Assertion Library](#44-assertionsts--shared-assertion-library)
5. [Unit Tests — Deep Dive by Domain](#5-unit-tests--deep-dive-by-domain)
   - 5.1 [Factory Layer](#51-factory-layer)
   - 5.2 [Kubernetes Stack Tests](#52-kubernetes-stack-tests)
   - 5.3 [Self-Healing Stack Tests](#53-self-healing-stack-tests)
   - 5.4 [Bedrock Stack Tests](#54-bedrock-stack-tests)
   - 5.5 [Shared Stack Tests](#55-shared-stack-tests)
   - 5.6 [Construct Tests](#56-construct-tests)
   - 5.7 [Lambda Handler Tests](#57-lambda-handler-tests)
   - 5.8 [Utility & Naming Tests](#58-utility--naming-tests)
6. [Integration Tests — SSM-Anchored Live Verification](#6-integration-tests--ssm-anchored-live-verification)
   - 6.1 [Strategy & Design Decisions](#61-strategy--design-decisions)
   - 6.2 [base-stack](#62-base-stack)
   - 6.3 [control-plane-stack](#63-control-plane-stack)
   - 6.4 [worker-asg-stack](#64-worker-asg-stack)
   - 6.5 [data-stack](#65-data-stack)
   - 6.6 [edge-stack](#66-edge-stack)
   - 6.7 [golden-ami-stack](#67-golden-ami-stack)
   - 6.8 [ssm-automation-runtime](#68-ssm-automation-runtime)
   - 6.9 [s3-bootstrap-artefacts](#69-s3-bootstrap-artefacts)
   - 6.10 [bootstrap-orchestrator](#610-bootstrap-orchestrator)
   - 6.11 [bluegreen](#611-bluegreen)
   - 6.12 [self-healing agent](#612-self-healing-agent)
7. [Key Design Patterns](#7-key-design-patterns)
   - 7.1 [SSM as the Source of Truth](#71-ssm-as-the-source-of-truth)
   - 7.2 [Diagnostic-First Assertions](#72-diagnostic-first-assertions)
   - 7.3 [Module-Level `beforeAll` Caching](#73-module-level-beforeall-caching)
   - 7.4 [`satisfies` over `as const`](#74-satisfies-over-as-const)
   - 7.5 [No Conditionals in `it()` Blocks](#75-no-conditionals-in-it-blocks)
   - 7.6 [Env Vars Before Imports](#76-env-vars-before-imports)
8. [How the Tests Accelerate CDK Deployments](#8-how-the-tests-accelerate-cdk-deployments)
9. [CI Integration](#9-ci-integration)
10. [Coverage Map — File by File](#10-coverage-map--file-by-file)
11. [Known Gaps & Future Work](#11-known-gaps--future-work)

---

## 1. Overview & Purpose

### What problem does this test suite solve?

CDK is an infrastructure-as-code tool that synthesises TypeScript into CloudFormation JSON. The risk profile of this codebase is high:
- A **misconfigured Security Group** exposes the cluster to the internet.
- A **missing SSM parameter** breaks every downstream stack that imports it.
- An **incorrect IAM policy** causes runtime `AccessDenied` failures that only surface after a 10-minute `cdk deploy`.
- A **broken CloudFormation template** (e.g., a `Fn::Join` that produces invalid JSON) fails at deploy time, not at synthesis time.

The test suite exists to catch all of these categories **before any AWS call is made**, collapsing a potential 10–20 minute feedback loop into a **sub-60-second local test run**.

### The two-phase guarantee

The test suite provides two distinct guarantees:

| Phase | Mechanism | What it proves |
|---|---|---|
| **Synthesis correctness** | Unit tests (`Template.fromStack`) | The CloudFormation template _will_ be correct if deployed |
| **Deployment correctness** | Integration tests (AWS SDK) | The deployed resources _are_ correct in live AWS |

Together they form a continuous verification loop: unit tests gate the CI pipeline, integration tests gate the CD pipeline.

---

## 2. The Testing Pyramid — Three Tiers

```
                    ┌───────────────────────────────┐
                    │  INTEGRATION TESTS (16 files) │  ← Real AWS API calls
                    │  jest.integration.config.js   │  ← 60-second timeout
                    └───────────────────────────────┘
               ┌───────────────────────────────────────────┐
               │        UNIT TESTS (32 files)              │  ← Template.fromStack
               │        jest.config.js                     │  ← <60s total suite
               └───────────────────────────────────────────┘
          ┌─────────────────────────────────────────────────────┐
          │             FIXTURE LAYER (5 files)                 │  ← Shared DI helpers
          │  constants / mock-resources / test-app / assertions │
          └─────────────────────────────────────────────────────┘
```

### Why this separation?

#### Unit tests — speed and isolation
CDK unit tests instantiate stacks entirely in memory. They do not call AWS APIs — crucially, they do **not** need credentials, connectivity, or a deployed environment. A `cdk synth` that takes 8 seconds in the shell completes in milliseconds here because the CDK construct tree is evaluated in-process.

This makes unit tests viable for a **developer inner loop**: run `yarn test:stacks` on every file save and get instant feedback.

#### Integration tests — reality verification
CloudFormation has idiosyncrasies that synthesis cannot catch: eventual-consistency delays, service-limit enforcement, cross-account Route 53 delegation, NLB attribute propagation. Integration tests close this gap by calling real AWS APIs against the live environment, verifying that what CloudFormation deployed matches what the stack declared it would deploy.

These tests run **only after a successful CDK deployment** in the CI pipeline (`_deploy-kubernetes.yml`), acting as an automated smoke test / acceptance gate.

#### Fixture layer — DRY dependency injection
Every stack test requires the same boilerplate: create a CDK `App`, inject a VPC (via context), inject mock Security Groups, inject mock KMS keys. Without a shared fixture layer, this 30–50 line prologue would be duplicated 32 times, creating maintenance sprawl.

---

## 3. Toolchain & Configuration

### 3.1 `jest.config.js` — Unit Test Runner

```js
// infra/jest.config.js
module.exports = {
  testMatch: ['**/tests/unit/**/*.test.ts'],
  transform: { '^.+\\.tsx?$': 'ts-jest' },
  moduleNameMapper: {
    '^esbuild$': '<rootDir>/tests/__mocks__/esbuild.js',
  },
  globalSetup: './tests/jest-setup.ts',
  workerIdleMemoryLimit: '512MB',
  testEnvironment: 'node',
  setupFiles: ['./tests/jest-worker-setup.js'],
};
```

**Key decisions:**

- **`testMatch` glob** explicitly scopes to `tests/unit/**` — integration tests are excluded and cannot accidentally run during unit test invocation.
- **`esbuild` mock** — several stacks (e.g., Lambda inline bundling constructs) use CDK's NodejsFunction, which calls `esbuild` at synth time to bundle handler code. In a test environment, this bundling must be intercepted. The mock replaces the `esbuild` module with a stub that returns an empty bundle — ensuring the test focuses on IAM/resource configuration rather than bundle output.
- **`workerIdleMemoryLimit: '512MB'`** — CDK construct trees are memory-intensive. This setting prevents Jest workers from accumulating memory across test files, avoiding OOM kills during the full 32-file suite.
- **`setupFiles`** — points to `jest-worker-setup.js`, which runs inside each worker process before tests execute.

### 3.2 `jest.integration.config.js` — Integration Runner

```js
// infra/jest.integration.config.js
module.exports = {
  testMatch: ['**/tests/integration/**/*.integration.test.ts'],
  testTimeout: 60000,  // 60 seconds per test
  maxWorkers: 1,       // Sequential — avoid API throttling
  globalSetup: './tests/jest-setup.ts',
  setupFiles: ['./tests/jest-worker-setup.js'],
};
```

**Key decisions:**

- **Distinct `testMatch`** — the `.integration.test.ts` suffix prevents accidental inclusion in unit test runs. The double qualifier (directory + filename suffix) is belt-and-suspenders.
- **`testTimeout: 60000`** — AWS API calls (particularly `GetParametersByPath` with pagination, `DescribeLoadBalancers`, `GetHostedZone`) can take 3–15 seconds. The default Jest 5-second timeout would cause false-negative failures.
- **`maxWorkers: 1`** — integration tests run sequentially to avoid hammering the AWS API from multiple concurrent processes, which would cause throttling errors that could be confused with real infrastructure failures.

### 3.3 `jest-setup.ts` — Global Setup

```typescript
// infra/tests/jest-setup.ts
import * as path from 'path';
import * as fs from 'fs';

export default async function globalSetup(): Promise<void> {
  jest.setTimeout(30_000);

  // Ensure Lambda asset directory exists for NodejsFunction synth
  const assetDir = path.join(__dirname, '..', 'cdk.out', 'assets');
  if (!fs.existsSync(assetDir)) {
    fs.mkdirSync(assetDir, { recursive: true });
  }
}
```

**Why is the `cdk.out/assets` directory needed?**

CDK's `NodejsFunction` construct writes bundled Lambda assets to `cdk.out/assets/` during synthesis. If this directory does not exist, the construct throws a filesystem error before any CloudFormation template is produced. The global setup ensures this directory always exists, even in a fresh CI workspace where `cdk synth` has never been run.

### 3.4 `jest-worker-setup.js` — The Monorepo CWD Fix

```javascript
// infra/tests/jest-worker-setup.js
const path = require('path');

/**
 * Jest workers inherit the CWD from the parent process, which in a monorepo
 * is typically the repo root. CDK constructs that use `path.relative(__dirname, ...)`
 * or read `cdk.json` assume CWD is the package root (`infra/`).
 *
 * This setupFile runs inside each worker before any test and resets CWD to
 * the infra package directory, ensuring consistent path resolution.
 */
module.exports = async () => {
  const infraRoot = path.resolve(__dirname, '..', '..');
  process.chdir(infraRoot);
};
```

**The problem this solves — monorepo CWD drift:**

When you run `yarn test` from the repository root (e.g., via `just test-stacks` which sets `cwd` to the workspace root), Jest's parent process starts with `CWD = /portfolio/cdk-monitoring`. However, Jest spawns worker processes to run tests in parallel. These workers inherit the parent's CWD.

CDK constructs use `path.resolve(__dirname, ...)` to locate `cdk.json`, Lambda handler entry points, and S3 asset directories. If the CWD is the repo root rather than `infra/`, these path resolutions fail silently — producing wrong paths that cause either synthesis errors or, worse, tests that pass locally but fail in CI (where the runner may use a different CWD).

The `jest-worker-setup.js` script corrects this by **explicitly `chdir`-ing into `infra/`** at the start of every worker process, making the test environment deterministic regardless of where Jest was invoked from.

> This is a non-obvious but critical fix. Without it, the test suite would produce environment-dependent results — breaking the CI guarantee.

---

## 4. The Fixture Layer — Shared Infrastructure

The five files in `infra/tests/fixtures/` are the foundation of the entire test suite. They implement the **dependency injection pattern** for CDK tests — extracting all boilerplate into reusable helpers.

### 4.1 `constants.ts` — Centralised Magic Values

```typescript
// Key exports
export const TEST_ENV_EU: cdk.Environment = {
  account: '123456789012',
  region: 'eu-west-1',
};

export const TEST_ENV_US: cdk.Environment = {
  account: '123456789012',
  region: 'us-east-1',
};

export const VPC_CONTEXT_KEY = 'vpc-provider:account=123456789012:...';
export const MOCK_VPC_ID = 'vpc-12345678';
```

**Why centralise constants?**

CDK performs **environment-aware lookups** (`Vpc.fromLookup`, `HostedZone.fromLookup`) by embedding environment context (account/region) into a lookup key. If a test file uses account `111111111111` but the fixture-registered context uses `123456789012`, the lookup produces a dummy placeholder VPC instead of the mock VPC — causing synthesis to fail.

By centralising these values, all 32 unit test files share the **same account/region context**, ensuring that every `Vpc.fromLookup` resolves to the same mock VPC registered in the CDK App context.

### 4.2 `mock-resources.ts` — Reusable AWS Stubs

```typescript
/**
 * Creates a mock VPC in a helper CDK stack.
 * Returns the IVpc interface — compatible with all stack props.
 */
export function createMockVpc(scope: Construct): ec2.IVpc { ... }

/**
 * Creates a mock Security Group in the given scope.
 */
export function createMockSecurityGroup(
    scope: Construct,
    id: string,
): ec2.ISecurityGroup { ... }

/**
 * Creates a mock KMS Key for encryption testing.
 */
export function createMockKmsKey(scope: Construct): kms.IKey { ... }
```

**The core concept: why not just `ec2.Vpc.fromLookup()`?**

`Vpc.fromLookup()` synthesises real AWS resource IDs into the CloudFormation template. In a test, this produces `dummy-value-for-...` placeholders (because there is no deployed VPC to look up). Some CDK constructs treat these placeholders as valid IDs and proceed; others validate the format and throw validation errors during synthesis.

`mock-resources.ts` sidesteps this entirely: it creates **real CDK L2 construct instances** (backed by synthesisable CloudFormation resources) in a disposable helper stack. The `IVpc`, `ISecurityGroup`, and `IKey` interfaces returned are fully functional CDK objects — they have proper `.vpcId`, `.securityGroupId`, and `.keyArn` properties that produce valid CloudFormation references (`{ Ref: '...' }`).

This is the **correct way** to test stacks that receive dependency-injected resources: pass real CDK constructs rather than mocked AWS IDs.

### 4.3 `test-app.ts` — Factory Helpers

```typescript
/**
 * Create a CDK App pre-configured with the VPC context required for
 * Vpc.fromLookup() to resolve without hitting AWS.
 */
export function createTestApp(): cdk.App {
    return new cdk.App({
        context: {
            [VPC_CONTEXT_KEY]: MOCK_VPC_CONTEXT,
        },
    });
}

/**
 * Create a dependent stack (e.g., HelperStack → TargetStack) and
 * optionally inject mock resources from the helper into the target.
 *
 * This resolves cross-stack dependency injection in tests — the
 * same pattern the production factory uses.
 */
export function createStackWithHelper<H extends cdk.Stack, T extends cdk.Stack>(
    app: cdk.App,
    HelperConstructor: new (...args: unknown[]) => H,
    TargetConstructor: new (...args: unknown[]) => T,
    helperProps: cdk.StackProps,
    targetPropsFactory: (helper: H) => cdk.StackProps,
): { helper: H; target: T; template: Template } { ... }
```

**The factory pattern in tests — why was it needed?**

In production CDK, stacks pass resources to each other via **cross-stack references** (CloudFormation exports/imports). For example, `KubernetesBaseStack` creates a VPC and Security Groups, then passes them to `KubernetesControlPlaneStack` via its constructor props.

In tests, simply instantiating `KubernetesControlPlaneStack` and passing `undefined` for the VPC prop causes a synthesis error. You need a real CDK VPC object. But creating a full `KubernetesBaseStack` just to get a VPC is expensive and couples the control plane test to the base stack's implementation.

`createStackWithHelper` solves this by:
1. Creating a lightweight **helper stack** that only instantiates the specific resources needed (VPC, SG, KMS key) via `mock-resources.ts`.
2. Running the **target stack constructor** with those real CDK objects injected.
3. Returning both stacks and the synthesised `Template` for assertions.

This mirrors exactly how the production `KubernetesProjectFactory` wires stacks together — the test helper is a miniature version of the production factory pattern.

### 4.4 `assertions.ts` — Shared Assertion Library

```typescript
export class StackAssertions {
    constructor(private readonly template: Template) {}

    /**
     * Assert that no Security Group rule opens SSH (port 22) to the internet.
     * Enforces the Checkov rule CKV_AWS_25 at the test layer.
     */
    assertNoSshIngress(): void { ... }

    /**
     * Assert that all S3 buckets have server-side encryption enabled.
     */
    assertS3Encryption(): void { ... }

    /**
     * Assert that all S3 buckets have versioning enabled.
     */
    assertS3Versioning(): void { ... }

    /**
     * Assert that no IAM inline policies exist (prefer managed policies).
     */
    assertNoInlineIamPolicies(): void { ... }

    /**
     * Assert that all Lambda functions have a defined log retention period.
     */
    assertLambdaLogRetention(): void { ... }
}
```

**The dual-layer security enforcement concept:**

The `StackAssertions` class enforces security policies at the **unit test layer**. This is distinct from (but complementary to) the Checkov static analysis layer.

The distinction matters because:
- **Checkov** scans the synthesised CloudFormation JSON file and detects patterns using Python-based rules. It runs as a separate CI job.
- **`StackAssertions`** runs as part of the unit test suite and uses CDK's `Template` assertions API — it can express more complex assertions that depend on CDK-level logic (e.g., "no SG rule with port 22 that has a CIDR source of `0.0.0.0/0`") in a way that's directly readable by TypeScript developers.

By enforcing these rules in both layers, a security misconfiguration must evade **two independent checks** before it can reach a deployment.

---

## 5. Unit Tests — Deep Dive by Domain

### 5.1 Factory Layer

#### `project-registry.test.ts` (58 lines)

**What it tests:** The `project-registry` module, which maps `(Project, Environment)` tuples to the correct factory instance.

**Concepts implemented:**
- **Registry pattern validation** — verifies that `getProjectFactory(Project.KUBERNETES, Environment.DEVELOPMENT)` returns a factory with matching `.project` and `.environment` properties.
- **Input validation** — verifies that invalid project/environment strings throw descriptive errors (e.g., `throw /Invalid project.*invalid-project/`). This is contract-first design: the registry enforces its own invariants.
- **Exhaustive key coverage** — tests all three environment values (`DEVELOPMENT`, `STAGING`, `PRODUCTION`) to ensure no environment-specific branching was accidentally omitted.

**Why is this test needed?** The registry is the entry point for every GitHub Actions deployment workflow. If it maps the wrong factory to a project key, the wrong set of stacks would be deployed — a silent, catastrophic failure. This test provides a direct assertion on that mapping.

---

#### `projects/kubernetes/factory.test.ts` (174 lines)

**What it tests:** The `KubernetesProjectFactory` — the orchestration class that creates all 11 Kubernetes stacks in the correct dependency order.

**Concepts implemented:**

1. **Stack count assertion** — `expect(stacks).toHaveLength(11)` — an explicit guard against accidentally adding or removing stacks without updating the factory. This is the fastest possible way to detect a stack registration regression.

2. **Stack map key presence** — asserts that all 11 named keys (`data`, `base`, `goldenAmi`, `ssmAutomation`, `controlPlane`, `generalPool`, `monitoringPool`, `appIam`, `api`, `edge`, `observability`) are present in the `stackMap` object. This is **named-key contract testing** — callers of the factory depend on these exact key names.

3. **Negative assertions** — `expect(stackMap).not.toHaveProperty('worker')` and `not.toHaveProperty('monitoringWorker')` explicitly verify that **legacy stacks have been decommissioned**. This prevents regressions where deleted code is accidentally reintroduced.

4. **Deployment order validation** — tests the `stackNames` array index by index:
   ```typescript
   expect(stackNames[0]).toContain('Data');
   expect(stackNames[1]).toContain('Base');
   // ... through index 10
   ```
   This enforces the CDK dependency graph. CDK's `addDependency()` calls declare ordering constraints, but this test verifies that the factory actually respects that ordering in the returned array — which is what `_deploy-kubernetes.yml` iterates to determine which stacks to deploy sequentially.

5. **Cross-region deployment** — verifies that the `edge` stack is in `us-east-1` while all other stacks are in `eu-west-1`. CloudFront distributions require ACM certificates in `us-east-1`; this test ensures that regional targeting is not accidentally lost during refactoring.

6. **Environment isolation** — creates two factories (`DEVELOPMENT` and `PRODUCTION`) in separate `cdk.App` instances and verifies that their stack names contain the correct environment suffix. This prevents an environment suffix bug where all environments would deploy identically named stacks, causing them to clobber each other.

7. **Env-var-before-import pattern** — the file sets `process.env` values for `DOMAIN_NAME`, `HOSTED_ZONE_ID`, etc. _before_ the first `import` statement. This is necessary because the config module (`lib/config`) calls `fromEnv()` at **module load time** — if env vars are not set before the import cycle begins, the config throws a validation error before any test runs.

---

### 5.2 Kubernetes Stack Tests

#### `base-stack.test.ts` (898 lines) — The largest unit test file

**What it tests:** `KubernetesBaseStack` — the foundational networking stack that creates the VPC, NLB, Security Groups, KMS key, Route 53 zones, S3 log bucket, and 13 SSM parameters.

**Concepts implemented:**

**Security Group rule validation — a CDK-specific challenge:**
The Security Group rules in `KubernetesBaseStack` encode the entire cluster's network access model. 18 ingress rules govern which ports are accessible from which sources (VPC CIDR, pod CIDR, self-referencing SG, NLB prefix list).

CDK's `Template.hasResourceProperties` with `Match.objectLike` and `Match.arrayWith` allows partial matching — you assert that a rule _containing_ the expected properties exists, without requiring an exact match on the full CloudFormation resource. This is correct because CDK adds metadata (descriptions, IDs) that vary between runs.

```typescript
it('should have VPC CIDR ingress on port 6443 (K8s API server)', () => {
    template.hasResourceProperties('AWS::EC2::SecurityGroup', {
        SecurityGroupIngress: Match.arrayWith([
            Match.objectLike({
                FromPort: 6443,
                ToPort: 6443,
                IpProtocol: 'tcp',
                CidrIp: Match.stringLikeRegexp('^10\\.'),
            }),
        ]),
    });
});
```

**SSM parameter count assertion:**
```typescript
it('should create exactly 13 SSM parameters', () => {
    template.resourceCountIs('AWS::SSM::Parameter', 13);
});
```

This is a **regression guard** on the stack's public API. Every SSM parameter is a contract with downstream stacks. Adding or removing parameters without updating this test signals that the API surface has changed and all consumers (control plane, compute, worker ASG, IAM) must be updated too.

**KMS key rotation:**
```typescript
it('should enable automatic key rotation', () => {
    template.hasResourceProperties('AWS::KMS::Key', {
        EnableKeyRotation: true,
    });
});
```

AWS Security Hub finding `[KMS.4]` requires annual key rotation for CMKs. This test enforces that the CDK `enableKeyRotation: true` prop is always present, preventing the security control from being accidentally removed.

**NLB access logging:**
```typescript
it('should enable access logs on the NLB', () => {
    template.hasResourceProperties('AWS::ElasticLoadBalancingV2::LoadBalancer', {
        LoadBalancerAttributes: Match.arrayWith([
            Match.objectLike({
                Key: 'access_logs.s3.enabled',
                Value: 'true',
            }),
        ]),
    });
});
```

NLB access logs provide the audit trail for all traffic entering the cluster. This test ensures the attribute is always set — without it, traffic auditing would be silently disabled on redeployment.

---

#### `worker-asg-stack.test.ts` (684 lines)

**What it tests:** `KubernetesWorkerAsgStack` — the cattle-model ASG pool stack, tested parametrically for both `general` and `monitoring` pools.

**Key concept — parametric test suites:**

```typescript
const POOL_CONFIGS = [
    { poolType: 'general', expectedMinCapacity: 2, expectedMaxCapacity: 6 },
    { poolType: 'monitoring', expectedMinCapacity: 1, expectedMaxCapacity: 3 },
] as const;

describe.each(POOL_CONFIGS)('WorkerAsgStack — $poolType pool', ({ poolType, expectedMinCapacity, expectedMaxCapacity }) => {
    it('should have correct ASG capacity limits', () => { ... });
    it('should have pool-specific IAM policies', () => { ... });
    it('should include pool label in user data', () => { ... });
});
```

Running the same test body against both pool configurations with `describe.each` achieves two goals:
1. **Coverage parity** — both pools are guaranteed to pass the same set of assertions. A regression that breaks `general` but not `monitoring` (or vice versa) is caught.
2. **Explicit capacity contracts** — the `expectedMinCapacity: 2` for the general pool documents a **deliberate infrastructure decision** made to ensure scheduling capacity during node evictions. This value is not arbitrary; it was set after experiencing cascading scheduling failures with `minCapacity: 1`.

**User data validation — a subtle anti-pattern avoided:**

The ASG user data is a Bootstrap script that configures EC2 instances as Kubernetes nodes. Rather than testing the full user data content (which would be brittle — any formatting change would break tests), the test validates only the **invariants that matter operationally**:

```typescript
it('should include cluster join endpoint in user data', () => {
    template.hasResourceProperties('AWS::AutoScaling::LaunchTemplate', {
        LaunchTemplateData: {
            UserData: Match.objectLike({
                'Fn::Base64': Match.stringLikeRegexp(`SSM_PREFIX=/k8s/${env}`),
            }),
        },
    });
});
```

This tests the **semantic content** (the SSM prefix is correct for the environment) rather than the **syntactic content** (the exact byte-for-byte user data string). This makes the test resilient to cosmetic changes while still catching functional regressions.

---

#### `ssm-automation-stack.test.ts` (387 lines)

**What it tests:** `K8sSsmAutomationStack` — the stack that creates SSM Automation and Command documents for cluster bootstrapping.

**Key concepts:**

**Document content validation with `Match.objectLike`:**

SSM Automation documents are stored as JSON inside the CloudFormation `Content` property. CDK synthesises them as nested objects. Testing these requires asserting into the JSON structure:

```typescript
it('should configure onFailure: Abort for each step', () => {
    template.hasResourceProperties('AWS::SSM::Document', {
        Content: Match.objectLike({
            mainSteps: Match.arrayWith([
                Match.objectLike({ onFailure: 'Abort' }),
            ]),
        }),
    });
});
```

`onFailure: 'Abort'` is a **critical safety property**. If omitted, a failed bootstrap step would silently continue to the next step, potentially joining a broken node to the cluster. This test makes the failure mode explicit.

**Resource cleanup provider — the orphan deletion problem:**

```typescript
it('should create custom resources for SSM parameter cleanup', () => {
    template.resourceCountIs('AWS::CloudFormation::CustomResource', 14);
});
```

When a CDK stack is destroyed (`cdk destroy`), CloudFormation can only delete resources it created. SSM parameters and CloudWatch log groups created **dynamically at runtime** (by the bootstrap Lambda) are not in the CloudFormation template and are thus orphaned.

The `ResourceCleanupProvider` addresses this: a Custom Resource backed by a Lambda function that pre-emptively deletes these runtime-created resources when the stack is torn down. The test asserts:
1. The cleanup Lambda exists with Python 3.13 runtime.
2. Exactly 14 Custom Resource cleanup registrations are present (8 SSM params + 5 log groups + 1 SNS topic).
3. The Lambda has `DeleteLogGroup`, `DeleteParameter`, and `DeleteTopic` permissions.

This is an excellent example of **infrastructure lifecycle management** being tested — not just creation, but clean deletion.

---

#### `compute-stack.test.ts` (440 lines)

**What it tests:** `KubernetesComputeStack` — the control plane provisioning stack (Golden AMI pipeline, EC2 instance launch, user data, IAM role).

**Notable test pattern — `it.todo()`:**

```typescript
it.todo('should validate esbuild bundle output correctness');
it.todo('should verify Lambda handler has correct exports');
it.todo('should assert CloudWatch Logs configuration');
```

`it.todo()` is a **structured technical debt marker**. Jest reports these as pending tests (yellow in CI output), not failures. They document known test gaps without hiding them. These gaps represent the **runtime Lambda layer** — harder to unit test because they require the actual Lambda code to execute, not just CDK synthesis.

---

#### `observability-stack.test.ts` (245 lines)

**What it tests:** `KubernetesObservabilityStack` — the CloudWatch Dashboard stack that provides visibility before Prometheus/Grafana is live.

**Key concept — dashboard content validation:**

CloudWatch Dashboard bodies are CloudFormation `Fn::Join` arrays. CDK synthesises them as deeply nested token structures. The test uses a `getDashboardBody()` helper to flatten this into a searchable string:

```typescript
function getDashboardBody(resources: Record<string, Record<string, unknown>>): string {
    // CDK produces Fn::Join for the dashboard body
    const body = properties.DashboardBody;
    if (typeof body === 'string') return body;
    return JSON.stringify(body); // Flatten Fn::Join
}
```

This allows content assertions like:
```typescript
expect(dashboardBody).toContain('AWS/NetworkELB');
expect(dashboardBody).toContain('ActiveFlowCount');
```

**Conditional widget testing — CloudFront section:**

```typescript
it('should include CloudFront metrics when distributionId SSM path is provided', () => {
    const { template } = createObservabilityStack({
        cloudFrontDistributionIdSsmPath: '/nextjs/development/cloudfront/distribution-id',
    });
    expect(getDashboardBody(dashboard)).toContain('AWS/CloudFront');
});

it('should NOT include CloudFront metrics when distributionId is omitted', () => {
    const { template } = createObservabilityStack(); // no CloudFront arg
    expect(getDashboardBody(dashboard)).not.toContain('AWS/CloudFront');
});
```

This tests the **optional composition pattern** — the CloudWatch dashboard conditionally includes a CloudFront section only when a distribution ID is provided. This is a design decision that allows the observability stack to serve as a pre-deployment bootstrap dashboard (before CloudFront exists) and a full-stack operations dashboard (after CloudFront is deployed).

**SSM read-only assertion:**

```typescript
it('should NOT create any SSM parameters (reads only)', () => {
    template.resourceCountIs('AWS::SSM::Parameter', 0);
});
```

This negative assertion is architecturally significant: the observability stack reads SSM parameters (EBS volume IDs, NLB ARNs) at **deploy time** via `StringParameter.valueForStringParameter`. It must not create its own SSM parameters — doing so would conflict with the base stack's parameters. This test enforces that read-vs-write boundary.

---

#### `api-stack.test.ts`, `app-iam-stack.test.ts`, `data-stack.test.ts`

These follow similar patterns:
- **`api-stack.test.ts`** — validates API Gateway/Lambda configuration, ACM certificate references, and Route 53 record creation.
- **`app-iam-stack.test.ts`** — validates IAM role creation with correct trust policies, permissions boundary attachment, and SSM parameter publishing of role ARNs.
- **`data-stack.test.ts`** — validates DynamoDB table partition key schema, billing mode (PAY_PER_REQUEST), point-in-time recovery, and encryption settings.

---

### 5.3 Self-Healing Stack Tests

#### `agent-stack.test.ts`, `gateway-stack.test.ts`

**What they test:** The Bedrock-powered self-healing agent — the Step Functions state machine, Lambda remediation tool, and API Gateway webhook gateway.

**Key concept — Step Functions definition validation:**

```typescript
it('should have a state machine with correct states', () => {
    template.hasResourceProperties('AWS::StepFunctions::StateMachine', {
        DefinitionString: Match.objectLike({
            States: Match.objectLike({
                DiagnoseFailure: Match.objectLike({ Type: 'Task' }),
                RemediateFailure: Match.objectLike({ Type: 'Task' }),
                NotifySlack: Match.objectLike({ Type: 'Task' }),
            }),
        }),
    });
});
```

Step Functions state machine definitions are JSON embedded in CloudFormation. This test validates that the remediation workflow graph is structurally correct before deployment — catching state name typos, missing transitions, or incorrect resource ARNs.

---

### 5.4 Bedrock Stack Tests

Seven test files cover the AI/ML infrastructure:

| File | What it tests |
|---|---|
| `agent-stack.test.ts` | Bedrock Agent, Action Groups, Knowledge Base association |
| `ai-content-stack.test.ts` | AI content Lambda, prompt configuration |
| `api-stack.test.ts` | Admin API Gateway, Lambda integration, Cognito auth |
| `data-stack.test.ts` | DynamoDB tables for article storage |
| `kb-stack.test.ts` | Bedrock Knowledge Base, OpenSearch Serverless collection |
| `strategist-data-stack.test.ts` | Strategist DynamoDB tables |
| `strategist-pipeline-stack.test.ts` | EventBridge → Step Functions pipeline |

**Notable pattern — EventBridge rule validation:**

```typescript
it('should create an EventBridge rule for article ingestion', () => {
    template.hasResourceProperties('AWS::Events::Rule', {
        EventPattern: Match.objectLike({
            source: ['bedrock-article-pipeline'],
            'detail-type': ['ArticlePublished'],
        }),
        Targets: Match.arrayWith([
            Match.objectLike({
                Arn: Match.objectLike({ 'Fn::GetAtt': Match.arrayWith(['StateMachine']) }),
            }),
        ]),
    });
});
```

EventBridge rules are the wiring between the article publication event and the Step Functions pipeline. This test ensures the `source` and `detail-type` filter patterns match exactly what the publisher emits — a mismatch would silently drop all events.

---

### 5.5 Shared Stack Tests

#### `security-baseline-stack.test.ts`

**What it tests:** The account-level security baseline — AWS Config rules, Security Hub standards, GuardDuty, and IAM Password Policy.

**Key concept — AWS Config rule count:**

```typescript
it('should create all required AWS Config rules', () => {
    template.resourceCountIs('AWS::Config::ConfigRule', 8);
});
```

This count assertion acts as a **security control inventory**. If a Config rule is accidentally removed during refactoring, this test fails, alerting the author that the security posture has been reduced.

#### `finops-stack.test.ts`

**What it tests:** Budget alerts and cost allocation tags.

```typescript
it('should create a budget with correct monthly limit', () => {
    template.hasResourceProperties('AWS::Budgets::Budget', {
        Budget: Match.objectLike({
            BudgetLimit: { Amount: '50', Unit: 'USD' },
            TimeUnit: 'MONTHLY',
        }),
    });
});
```

This test documents the **intentional cost ceiling** for the development environment. It prevents the budget amount from being silently changed during stack refactoring.

---

### 5.6 Construct Tests

#### `ecr-repository.test.ts`

**What it tests:** The shared ECR repository construct — image scanning, lifecycle policies, and repository policy.

```typescript
it('should enable image scanning on push', () => {
    template.hasResourceProperties('AWS::ECR::Repository', {
        ImageScanningConfiguration: { ScanOnPush: true },
    });
});

it('should have lifecycle policy to expire untagged images after 7 days', () => {
    template.hasResourceProperties('AWS::ECR::Repository', {
        LifecyclePolicy: Match.objectLike({
            LifecyclePolicyText: Match.stringLikeRegexp('untaggedCountType'),
        }),
    });
});
```

ECR lifecycle policies prevent unbounded storage growth. Without a policy, every failed CI push accumulates untagged images indefinitely. This test enforces the policy's presence and its key term (`untaggedCountType`) without being brittle about the exact JSON structure.

#### `build-golden-ami-component.test.ts`

**What it tests:** The CDK custom construct wrapping EC2 Image Builder — component definition, distribution configuration, and pipeline schedule.

#### `ecs-cluster.test.ts`, `ecs-task-definition.test.ts`

**What they test:** The legacy ECS constructs retained from the ECS-era architecture. These remain in the test suite for two reasons:
1. The constructs are still referenced by the CDK codebase (even if unused in active stacks).
2. They document the design decisions from the migration from ECS to Kubernetes.

#### `budget-construct.test.ts`

**What it tests:** The reusable Budget CDK construct, separate from the stack-level FinOps test.

---

### 5.7 Lambda Handler Tests

#### `acm-certificate-dns-validation.test.ts`

**What it tests:** The Lambda function that handles custom ACM certificate DNS validation. This is the handler for the CDK Custom Resource that manages cross-account Route 53 CNAME records for ACM certificate validation.

**Why a separate test for a Lambda handler?**

CDK unit tests validate the infrastructure _around_ a Lambda. But the Lambda's **business logic** — reading an event, calling Route 53, handling errors — is independent of CDK and should be tested as pure TypeScript.

This test imports the Lambda handler function directly and calls it with mock events:

```typescript
import { handler } from '../../../../lib/lambda/acm-certificate-dns-validation/handler';

it('should create a DNS validation record on Create event', async () => {
    const event = makeMockCfnEvent({ RequestType: 'Create', ... });
    const result = await handler(event, mockContext);
    expect(mockRoute53.send).toHaveBeenCalledWith(expect.any(ChangeResourceRecordSetsCommand));
});
```

This pattern is the only way to test Lambda error paths (e.g., cross-account role assumption failures, Route 53 throttling) without deploying infrastructure.

---

### 5.8 Utility & Naming Tests

#### `naming.test.ts`

**What it tests:** The `flatName()` and `stackName()` utility functions used to generate all resource names across the codebase.

```typescript
it('should produce lowercase hyphenated names', () => {
    expect(flatName('k8s', 'base', 'development')).toBe('k8s-base-development');
});

it('should handle empty namespace', () => {
    expect(flatName('k8s', '', 'development')).toBe('k8s-development');
});
```

**Why test a naming utility?**

Resource names feed into SSM parameter paths, IAM role names, CloudFormation stack names, and S3 bucket names. A naming regression (e.g., `flatName` accidentally capitalising the first character) would:
1. Create new resources with different names.
2. Leave old resources orphaned (not in the new CloudFormation template).
3. Break all SSM parameter lookups that depend on the old names.

Naming is foundational — these tests are cheap insurance against cascading rename failures.

#### `tagging-guard.test.ts`

**What it tests:** The `TaggingGuard` construct, which validates that all CDK stacks include required cost-allocation tags before synthesis.

```typescript
it('should throw if required tag "Project" is missing', () => {
    expect(() => new TaggingGuard(stack, 'Guard', {
        requiredTags: ['Project', 'Environment'],
    })).toThrow(/Missing required tag: Project/);
});
```

AWS cost allocation requires consistent tagging across all resources. Without this guard, a stack could be deployed without tags, making cost attribution impossible. The test enforces that the guard itself cannot be silently bypassed.

---

## 6. Integration Tests — SSM-Anchored Live Verification

### 6.1 Strategy & Design Decisions

#### The fundamental principle — SSM as the source of truth

Every integration test follows the same top-level pattern:

```typescript
// Step 1: Load ALL SSM parameters published by this stack in ONE paginated call
const ssmParams = await loadSsmParameters();

// Step 2: All subsequent AWS API calls use SSM values — never hardcoded IDs
const vpcId = requireParam(ssmParams, SSM_PATHS.vpcId);
const { Vpcs } = await ec2.send(new DescribeVpcsCommand({ VpcIds: [vpcId] }));
```

**Why read from SSM first?**

CloudFormation stack outputs are the standard way to chain stack values. However, outputs require the `DescribeStacks` call to first retrieve the stack ARN, then the output value. SSM parameters, by contrast, are:
1. **Directly addressable** by a well-known path — no stack ARN needed.
2. **Versioned** — if a stack is redeployed and a resource changes, the SSM parameter is updated atomically.
3. **Discoverable** with `GetParametersByPath` — one API call retrieves all parameters under a prefix.
4. **The same wiring mechanism that production stacks use** — testing via SSM means the test exercises the same contract that downstream stacks depend on.

If a test loads a VPC ID from SSM and then calls `DescribeVpcs`, it is proving that:
- The stack created a VPC.
- The stack published its ID to SSM.
- The VPC ID in SSM is the correct one (resolves to a real, available VPC).

This is a three-layer assertion in one test.

#### The `requireParam` helper pattern

```typescript
function requireParam(params: Map<string, string>, path: string): string {
    const value = params.get(path);
    if (!value) throw new Error(`Missing required SSM parameter: ${path}`);
    return value;
}
```

This eliminates TypeScript's `!` non-null assertion entirely, replacing it with a descriptive runtime error. When an integration test fails with `Missing required SSM parameter: /k8s/development/vpcId`, the failure message immediately identifies whether the stack failed to deploy or failed to publish the parameter.

#### Module-level `beforeAll` — API call budget management

```typescript
// All shared state is module-level
let ssmParams: Map<string, string>;
let nlb: LoadBalancer;
let nlbSgIngress: IpPermission[];

beforeAll(async () => {
    ssmParams = await loadSsmParameters();
    // NLB, SG, flow logs — all fetched once
    const { LoadBalancers } = await elbv2.send(new DescribeLoadBalancersCommand(...));
    nlb = LoadBalancers![0];
    // ... etc
});

describe('VPC', () => {
    it('should exist', async () => {
        // Uses ssmParams directly — no API call here
        const vpcId = requireParam(ssmParams, SSM_PATHS.vpcId);
        const { Vpcs } = await ec2.send(new DescribeVpcsCommand({ VpcIds: [vpcId] }));
        expect(Vpcs).toHaveLength(1);
    });
});
```

A single `beforeAll` makes shared API calls once and caches results. Individual `it()` blocks use the cached data. This reduces AWS API call volume by a factor of 10–20x compared to making API calls inside each test, dramatically reducing:
- Test execution time.
- AWS API throttling risk.
- CloudWatch API quota consumption.

---

### 6.2 `base-stack.integration.test.ts` (1,214 lines)

**The largest integration test file, validating the foundational networking layer.**

**Sections tested:**
1. **SSM Parameters (13)** — all 13 parameters published by the base stack exist and have non-empty values.
2. **VPC** — exists and is in `available` state.
3. **VPC Flow Logs** — enabled, delivering to CloudWatch Logs, 3-day retention.
4. **Security Groups (×4)** — all four SGs exist and are attached to the correct VPC.
5. **Cluster Base SG Rules (18 rules)** — validates every ingress/egress rule:
   - Self-referencing rules (same SG): etcd (2379–2380), kubelet (10250), kube-controller-manager (10257), kube-scheduler (10259), Calico BGP (179), NodePort range (30000–32767), CoreDNS TCP (53), Calico Typha (5473), Traefik metrics (9100), Node Exporter metrics (9101).
   - UDP rules: VXLAN (4789), CoreDNS UDP (53).
   - VPC CIDR rules: K8s API server (6443).
   - Pod CIDR rules: API (6443), kubelet (10250), CoreDNS (53), metrics (9100, 9101).
6. **Control Plane SG**, **Ingress SG**, **Monitoring SG** — separate describe blocks each validating their specific rules.
7. **Elastic IP** — exists, is allocated, and matches the SSM value.
8. **NLB** — exists, is internet-facing, has `access_logs.s3.enabled: true`.
9. **NLB Target Groups** — HTTP (port 80) and HTTPS (port 443) target groups exist with correct health check paths.
10. **NLB Listeners** — exactly 2 listeners (80 and 443).
11. **S3 Log Bucket** — head bucket succeeds, encryption enabled, lifecycle policy present.
12. **Route 53 Hosted Zone** — private zone `k8s.internal` exists, has an A record at `k8s-api.k8s.internal` with 30-second TTL.
13. **KMS Key** — exists, is enabled, has automatic rotation enabled.

**Diagnostic formatters — production-quality failure messages:**

```typescript
function formatIpPermission(rule: IpPermission): string {
    const port = rule.FromPort === rule.ToPort
        ? `${rule.FromPort}`
        : `${rule.FromPort}-${rule.ToPort}`;
    const sources = [
        ...(rule.UserIdGroupPairs ?? []).map((p) => `SG:${p.GroupId}`),
        ...(rule.IpRanges ?? []).map((r) => `CIDR:${r.CidrIp}`),
        ...(rule.PrefixListIds ?? []).map((p) => `PrefixList:${p.PrefixListId}`),
    ];
    return `  • Port ${port} (${rule.IpProtocol}) — Sources: ${sources.join(', ') || '(none)'}`;
}
```

When a Security Group rule assertion fails, the error message includes the full list of actual rules in human-readable format:
```
Expected TCP ingress rule for port 6443, but none found.
Actual TCP ingress rules (5):
  • Port 22 (tcp) — Sources: SG:sg-abc123
  • Port 443 (tcp) — Sources: PrefixList:pl-def456
  • Port 10250 (tcp) — Sources: SG:sg-abc123
  • Port 10257 (tcp) — Sources: SG:sg-abc123
  • Port 10259 (tcp) — Sources: SG:sg-abc123
```

An engineer seeing this failure immediately knows that port 6443 is missing — without opening the AWS Console or running CLI commands.

---

### 6.3 `control-plane-stack.integration.test.ts`

**Sections:**
- Control plane EC2 instance exists and is running.
- Instance type matches the configured type (e.g., `t3.medium`).
- IAM instance profile is attached and has correct roles.
- User data contains the expected bootstrap commands.
- CloudWatch agent is installed (SSM Run Command result).
- Node is registered in the Kubernetes API (via SSM proxy to `kubectl get nodes`).

---

### 6.4 `worker-asg-stack.integration.test.ts`

**Sections:**
- Both ASGs (`general` and `monitoring`) exist.
- ASG desired capacity is within min/max bounds.
- Launch template references the correct AMI (from Golden AMI SSM parameter).
- Instances are healthy and "In Service".
- Tag propagation is correct (pool label present on instances).

---

### 6.5 `data-stack.integration.test.ts`

**Sections:**
- DynamoDB table exists.
- Table status is `ACTIVE`.
- Point-in-time recovery is enabled.
- Billing mode is `PAY_PER_REQUEST`.
- SSE is enabled with a customer-managed KMS key.

---

### 6.6 `edge-stack.integration.test.ts`

**Sections:**
- CloudFront distribution exists in `us-east-1`.
- Distribution is deployed (not `InProgress`).
- WAF WebACL is associated.
- ACM certificate is valid (status `ISSUED`).
- Alternate domain name matches the expected FQDN.
- S3 origin access control is configured (not legacy OAI).

---

### 6.7 `golden-ami-stack.integration.test.ts`

**Sections:**
- EC2 Image Builder pipeline exists.
- AMI SSM parameter exists and contains a valid AMI ID.
- AMI is available in the correct region.

---

### 6.8 `ssm-automation-runtime.integration.test.ts`

**Sections:**
- SSM Automation documents exist with correct names.
- Document schema version is `0.3` (required for Automation type).
- IAM automation role exists and has correct trust policy.
- Bootstrap SSM parameters (`control-plane-doc-name`, `worker-doc-name`) are published.

---

### 6.9 `s3-bootstrap-artefacts.integration.test.ts`

**Sections:**
- Scripts S3 bucket exists.
- Expected bootstrap scripts (`bootstrap-worker.py`, `bootstrap-control-plane.sh`) are present.
- Script content passes basic sanity checks (non-empty, contains expected shebang).
- Bucket has versioning enabled.
- Bucket has server-side encryption.

---

### 6.10 `bootstrap-orchestrator.integration.test.ts`

**Sections:**
- Step Functions state machine exists (sourced from SSM).
- State machine is in `ACTIVE` status.
- State machine definition contains the expected states.
- State machine has a recent execution (verifying it was triggered by the last deploy).
- Most recent execution succeeded.

---

### 6.11 `bluegreen.integration.test.ts`

**Sections:**
- Validates the blue-green deployment state via ArgoCD and NLB target groups.
- Confirms the active target group (blue vs green) matches the expected deployment slot.
- Verifies that the inactive target group has zero healthy targets (drain complete).

---

### 6.12 `self-healing/agent-stack.integration.test.ts`

**Sections:**
- Self-healing Step Functions state machine exists.
- Bedrock Agent is created and in `PREPARED` status.
- Lambda remediation function exists with correct runtime and environment variables.
- API Gateway webhook endpoint returns 200 for a probe request.

---

## 7. Key Design Patterns

### 7.1 SSM as the Source of Truth

Every integration test reads from SSM before making any other AWS API call. This pattern is called the **"SSM anchor"**:

```
SSM Parameter → AWS Resource ID → AWS API Verification
```

The benefit is that the test proves the **entire chain**: synthesis → deployment → parameter publishing → resource creation. A test that hardcodes an expected VPC ID would only prove the last step.

---

### 7.2 Diagnostic-First Assertions

Standard Jest assertions fail with:
```
Expected: defined
Received: undefined
```

The `require*` helpers in the integration tests fail with:
```
Expected TCP ingress rule for port 6443, but none found.
Actual TCP ingress rules (5):
  • Port 22 (tcp) — Sources: SG:sg-abc123
  ...
```

This transforms a debugging exercise (what _is_ in the SG?) into a single-line diagnosis. For a solo developer running CI at 2am, this matters enormously.

---

### 7.3 Module-Level `beforeAll` Caching

All shared API calls are made once in a top-level `beforeAll` and stored in module-level variables. Individual `it()` blocks **read** from these cached values; they do not make AWS API calls themselves.

```typescript
let ssmParams: Map<string, string>; // Module-level — shared across all describe blocks
let nlb: LoadBalancer;

beforeAll(async () => {
    ssmParams = await loadSsmParameters(); // ONCE
    nlb = await fetchNlb(ssmParams);       // ONCE
});

it('should have access logs enabled', () => {
    // Uses cached nlb — no API call
    expect(nlbAttributes.find(a => a.Key === 'access_logs.s3.enabled')?.Value).toBe('true');
});
```

---

### 7.4 `satisfies` over `as const`

TypeScript's `satisfies` operator validates a value against a type without widening it:

```typescript
// WRONG — loses type safety
const paths = ['vpcId', 'elasticIp'] as const;

// CORRECT — TypeScript will error if 'vpcId' is not a key of K8sSsmPaths
const paths = ['vpcId', 'elasticIp'] satisfies Array<keyof K8sSsmPaths>;
```

Using `satisfies Array<keyof K8sSsmPaths>` means that if a key is renamed in `K8sSsmPaths`, the test file will produce a TypeScript compile error rather than a silent runtime failure. This makes refactoring the SSM paths type-safe end-to-end.

---

### 7.5 No Conditionals in `it()` Blocks

Jest's `jest/no-conditional-in-test` rule (enforced by ESLint) prohibits `if`/`&&`/`||` inside `it()` blocks. This prevents test logic from hiding failures:

```typescript
// WRONG — if `rule` is undefined, the test passes silently
it('should have VPC CIDR rule for port 6443', () => {
    const rule = ingress.find(r => r.FromPort === 6443);
    if (rule) {
        expect(rule.IpRanges?.[0]?.CidrIp).toMatch(/^10\./);
    }
});

// CORRECT — uses a module-level helper that throws on failure
it('should have VPC CIDR rule for port 6443', () => {
    const rule = requireTcpIngressRule(ingress, 6443);
    expectCidrSource(rule, VPC_CIDR_PREFIX);
});
```

All conditional logic is extracted to module-level helper functions. The `it()` block itself reads linearly and cannot silently pass.

---

### 7.6 Env Vars Before Imports

The `factory.test.ts` sets environment variables before importing any modules:

```typescript
// Set env vars BEFORE any CDK/config imports
process.env.CDK_DEFAULT_ACCOUNT = '123456789012';
process.env.DOMAIN_NAME = 'dev.nelsonlamounier.com';

// Now safe to import
import * as cdk from 'aws-cdk-lib/core';
import { KubernetesProjectFactory } from '../../../../lib/projects/kubernetes';
```

This is necessary because the config module evaluates `fromEnv()` at **module initialisation time** — the moment the `import` statement executes, the config reads from `process.env`. If env vars are set after the import, they arrive too late and the config throws a `Missing required env var` error before any test runs.

---

## 8. How the Tests Accelerate CDK Deployments

### The time savings

| Activity | Without tests | With tests |
|---|---|---|
| Discover a missing SSM parameter | `cdk synth` (8s) + `cdk deploy` (5–15 min) | Unit test failure (<1s) |
| Discover a misconfigured SG rule | `cdk deploy` + visual AWS Console check | Unit test failure (<1s) |
| Discover a missing IAM permission | Deploy + test runtime failure (minutes) | Unit test failure (<1s) |
| Validate post-deploy state | Manual AWS Console inspection | Integration test (30–60s) |

### The parallelism benefit — unit test design

Because CDK unit tests instantiate stacks in memory, they can run in **parallel** across Jest workers. The 32 unit test files run simultaneously across 4 workers, completing in roughly the time it takes to run the slowest single file (~15s for `base-stack.test.ts` which has 898 lines).

Without this, sequential synthesis of 11 stacks would take ~90 seconds just for the base iteration, making the inner development loop impractically slow.

### The snapshot alternative — why Template.fromStack is preferred

CDK supports snapshot testing via `expect(Template.fromStack(stack)).toMatchSnapshot()`. Snapshots work but have a critical weakness: **they pin the entire CloudFormation template**, including CDK-generated logical IDs, metadata, and CDK version-specific artefacts. Every CDK upgrade invalidates all snapshots, requiring mass `--updateSnapshot` runs.

`Template.hasResourceProperties` + `Match.objectLike` targets only the semantically meaningful properties — the ones that can cause real infrastructure failures. This approach is:
1. **More resilient** to CDK version upgrades.
2. **More readable** — each assertion is self-documenting.
3. **More precise** — a snapshot change doesn't tell you _what changed_; a failing `hasResourceProperties` does.

---

## 9. CI Integration

### Unit tests in CI (`ci.yml`)

```yaml
# ci.yml — simplified
test-stacks:
  needs: [build]
  steps:
    - run: just test-stacks
      env:
        CDK_DEFAULT_ACCOUNT: ${{ secrets.CDK_DEFAULT_ACCOUNT }}
        CDK_DEFAULT_REGION: eu-west-1
        DOMAIN_NAME: ${{ secrets.DOMAIN_NAME }}
```

Unit tests run in the `test-stacks` job as part of every pull request. They provide the primary quality gate: no PR can merge if unit tests fail.

The `just test-stacks` recipe runs:
```
cd infra && yarn test --coverage --runInBand
```

`--runInBand` is used in CI (single worker) to avoid memory pressure in the GitHub Actions runner environment.

### Integration tests in CD (`_deploy-kubernetes.yml`)

```yaml
# _deploy-kubernetes.yml — simplified
integration-test-base:
  needs: [deploy-base]
  steps:
    - run: just ci-integration-test kubernetes development
      env:
        CDK_ENV: development
        AWS_REGION: eu-west-1
```

Integration tests run immediately after each stack deployment in the CD pipeline, validating the deployed state before proceeding to dependent stacks. If the integration test for `base-stack` fails, the pipeline halts — `control-plane-stack` is never deployed against a broken base.

This creates a **staged verification gate**: each deployment tier is verified before unlocking the next.

---

## 10. Coverage Map — File by File

| Test File | Production Subject | Key Assertions |
|---|---|---|
| `factories/project-registry.test.ts` | `lib/factories/project-registry` | Registry mapping, input validation |
| `projects/kubernetes/factory.test.ts` | `lib/projects/kubernetes` | 11 stacks, order, naming, regions |
| `stacks/kubernetes/base-stack.test.ts` | `KubernetesBaseStack` | 18 SG rules, 13 SSM params, NLB, KMS |
| `stacks/kubernetes/worker-asg-stack.test.ts` | `KubernetesWorkerAsgStack` | Parametric general/monitoring pools |
| `stacks/kubernetes/compute-stack.test.ts` | `KubernetesComputeStack` | Control plane EC2, user data |
| `stacks/kubernetes/ssm-automation-stack.test.ts` | `K8sSsmAutomationStack` | 5 SSM docs, cleanup provider (14 CRs) |
| `stacks/kubernetes/observability-stack.test.ts` | `KubernetesObservabilityStack` | 2 CW dashboards, conditional CloudFront |
| `stacks/kubernetes/api-stack.test.ts` | `KubernetesApiStack` | API GW, Lambda, ACM, Route53 |
| `stacks/kubernetes/app-iam-stack.test.ts` | `KubernetesAppIamStack` | IAM roles, trust policies, SSM export |
| `stacks/kubernetes/data-stack.test.ts` | `KubernetesDataStack` | DynamoDB, PITR, encryption |
| `stacks/self-healing/agent-stack.test.ts` | `SelfHealingAgentStack` | Step Functions, Bedrock, Lambda |
| `stacks/self-healing/gateway-stack.test.ts` | `SelfHealingGatewayStack` | API Gateway webhook |
| `stacks/bedrock/agent-stack.test.ts` | `BedrockAgentStack` | Bedrock agent, action groups, KB |
| `stacks/bedrock/ai-content-stack.test.ts` | `BedrockAiContentStack` | AI Lambda, prompts |
| `stacks/bedrock/api-stack.test.ts` | `BedrockApiStack` | Admin API, Cognito auth |
| `stacks/bedrock/data-stack.test.ts` | `BedrockDataStack` | DynamoDB tables |
| `stacks/bedrock/kb-stack.test.ts` | `BedrockKbStack` | Knowledge Base, OpenSearch |
| `stacks/bedrock/strategist-data-stack.test.ts` | `StrategistDataStack` | Strategist DDB |
| `stacks/bedrock/strategist-pipeline-stack.test.ts` | `StrategistPipelineStack` | EventBridge → Step Functions |
| `stacks/shared/security-baseline-stack.test.ts` | `SecurityBaselineStack` | 8 Config rules, GuardDuty, SH |
| `stacks/shared/finops-stack.test.ts` | `FinOpsStack` | Budget, cost tags |
| `stacks/shared/cognito-auth-stack.test.ts` | `CognitoAuthStack` | User pool, app client |
| `stacks/shared/crossplane-stack.test.ts` | `CrossplaneStack` | Provider config, IRSA |
| `shared/vpc-stack.test.ts` | `SharedVpcStack` | VPC, subnets, flow logs |
| `constructs/storage/ecr-repository.test.ts` | `EcrRepository` | Scan on push, lifecycle policy |
| `constructs/compute/build-golden-ami-component.test.ts` | `BuildGoldenAmiComponent` | Image Builder pipeline |
| `constructs/compute/ecs-cluster.test.ts` | `EcsClusterConstruct` | ECS cluster (legacy) |
| `constructs/compute/ecs-task-definition.test.ts` | `EcsTaskDefinitionConstruct` | ECS task (legacy) |
| `constructs/finops/budget-construct.test.ts` | `BudgetConstruct` | Budget alert |
| `lambda/acm-certificate-dns-validation.test.ts` | ACM validation handler | Route53 CNAME, error paths |
| `utilities/naming.test.ts` | `flatName`, `stackName` | All name formats |
| `utilities/tagging-guard.test.ts` | `TaggingGuard` | Required tag enforcement |

**Integration tests (16 files):**

| Integration File | Stack/System Validated |
|---|---|
| `kubernetes/base-stack.integration.test.ts` | VPC, NLB, SGs, KMS, Route53, S3, SSM |
| `kubernetes/control-plane-stack.integration.test.ts` | EC2 control plane, kubelet, kubectl |
| `kubernetes/worker-asg-stack.integration.test.ts` | ASGs, instances, AMI, tags |
| `kubernetes/data-stack.integration.test.ts` | DynamoDB, encryption, PITR |
| `kubernetes/edge-stack.integration.test.ts` | CloudFront, WAF, ACM, S3 OAC |
| `kubernetes/golden-ami-stack.integration.test.ts` | Image Builder, AMI SSM param |
| `kubernetes/ssm-automation-runtime.integration.test.ts` | SSM documents, IAM role |
| `kubernetes/s3-bootstrap-artefacts.integration.test.ts` | Scripts bucket, content |
| `kubernetes/bootstrap-orchestrator.integration.test.ts` | Step Functions, executions |
| `kubernetes/bluegreen.integration.test.ts` | ArgoCD, NLB target groups |
| `self-healing/agent-stack.integration.test.ts` | Bedrock agent, Step Functions, Lambda |

---

## 11. Known Gaps & Future Work

### `compute-stack.test.ts` — `it.todo()` cases

Three test cases are stubbed as `it.todo()`:
- Lambda handler export validation.
- esbuild bundle output correctness.
- CloudWatch Logs configuration.

These represent the **runtime Lambda layer** that is harder to unit test because it requires the actual handler code to execute. The remedy is to split the Lambda handler into a separately testable module and stub the CDK invoke in tests.

### Observability stack — Prometheus/Grafana coverage

The unit test for `observability-stack.test.ts` covers the **CloudWatch** dashboard (the pre-deployment fallback), but does not cover the in-cluster Prometheus/Grafana stack (which is Kubernetes-native, not CDK). A complementary `pytest` or Helm chart test suite at the `kubernetes-app` layer would complete this coverage.

### Integration test isolation — shared state risk

All integration tests are parametric on `CDK_ENV` but share the same AWS account. Parallel integration test runs across environments could theoretically race on SSM parameter reads. Currently, integration tests are run sequentially by environment in CI; this should be documented explicitly in the `_deploy-kubernetes.yml` pipeline comments.

### Snapshot coverage for Bedrock stacks

The Bedrock stack tests use `hasResourceProperties` for rule assertions, but lack total resource count assertions (equivalent to `template.resourceCountIs(...)`). Adding count assertions would catch accidental resource additions (e.g., an inadvertent extra Lambda function) that partial-match assertions would miss.

---

*Document generated: 2026-04-14 — Nelson Lamounier*  
*Cross-references: `devops_cicd_architecture_review.md` §15–17, `kubernetes_system_design_review.md`, `infra/lib/stacks/kubernetes/README.md`*
