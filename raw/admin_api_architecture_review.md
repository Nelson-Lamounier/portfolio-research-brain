# `admin-api` — Full Architectural Review

## 1. Overview

The `admin-api` is a **Backend-for-Frontend (BFF)** service built with **Hono** (a lightweight Node.js web framework). It is the exclusive data gateway for the `start-admin` TanStack application — the admin dashboard used to manage all portfolio content and infrastructure observability.

| Attribute        | Detail |
|-----------------|--------|
| **Framework**   | Hono v4 + `@hono/node-server` |
| **Runtime**     | Node.js ESM (`"type": "module"`) |
| **Auth**        | Cognito JWT (JWKS, validated via `jose`) |
| **Database**    | DynamoDB via `@aws-sdk/lib-dynamodb` |
| **Storage**     | S3 for article drafts and content blobs |
| **Compute**     | Lambda invocations (article & strategist pipelines) |
| **Observability** | CloudWatch (`BedrockMultiAgent`, `BedrockChatbot`, `SelfHealing`) |
| **Cost Tracking** | AWS Cost Explorer (always `us-east-1`) |
| **Credentials** | EC2 Instance Profile (IMDS) — zero secrets in code |
| **Deployment**  | Kubernetes (K3s), config injected via K8s Secrets/ConfigMaps |

---

## 2. Architecture Diagram

```
start-admin (TanStack)
         │  Bearer JWT
         ▼
  ┌─────────────┐
  │  admin-api  │  (Hono, K8s pod)
  │  :3000      │
  └──────┬──────┘
         │
         ├── Cognito JWKS ──► Auth validation
         │
         ├── DynamoDB ──────► articles, applications, resumes, comments
         │
         ├── S3 ────────────► drafts/*.md, article content blobs
         │
         ├── Lambda ─────────► article-pipeline-trigger
         │                     job-strategist-pipeline-trigger
         │
         └── CloudWatch/CE ──► FinOps metrics & cost data
```

---

## 3. Route Map (7 Routers)

| Mount Path                   | File            | Primary Responsibility |
|------------------------------|-----------------|------------------------|
| `/api/admin/articles`        | `articles.ts`   | Content CRUD, GSI status queries, pipeline trigger |
| `/api/admin/applications`    | `applications.ts` | Job application CRUD, batch delete, coaching |
| `/api/admin/pipelines`       | `pipelines.ts`  | Fire-and-forget + sync Lambda invocations |
| `/api/admin/resumes`         | `resumes.ts`    | Resume lifecycle, activation, S3 presign |
| `/api/admin/drafts`          | `drafts.ts`     | S3 PutObject → triggers article pipeline via S3 event |
| `/api/admin/finops`          | `finops.ts`     | CloudWatch metrics + Cost Explorer billing data |
| `/api/admin/comments`        | `comments.ts`   | Comment moderation queue (approve/reject/delete) |

> All routes are protected by the Cognito JWT middleware mounted **once** at the top-level `app` in `index.ts`.

---

## 4. DynamoDB Data Model

### 4.1 Key Schema

The service uses a **single-table design** with the composite key pattern `pk` (partition) + `sk` (sort).
A GSI (`gsi1pk` / `gsi1sk`) supports status-based querying without full table scans.

### 4.2 Entity Access Patterns

#### Articles

| Item Type        | `pk`                | `sk`         | `gsi1pk`             |
|-----------------|---------------------|--------------|----------------------|
| Article metadata | `ARTICLE#<slug>`    | `METADATA`   | `ARTICLE#<status>` (e.g., `ARTICLE#published`) |
| Article counters | `ARTICLE#<slug>`    | `COUNTERS`   | —                    |

**Access patterns:**
- `GET /articles` → Query `GSI1` where `gsi1pk = ARTICLE#published`
- `GET /articles/:slug` → `GetItem(pk=ARTICLE#<slug>, sk=METADATA)`
- `PUT /articles/:slug` → `UpdateItem` metadata fields
- `DELETE /articles/:slug` → `DeleteItem`

#### Applications

| Item Type           | `pk`                      | `sk`                        | `gsi1pk`                  |
|--------------------|---------------------------|-----------------------------|---------------------------|
| Application metadata| `APPLICATION#<slug>`      | `METADATA`                  | `APPLICATION#<status>`    |
| Analysis result    | `APPLICATION#<slug>`      | `ANALYSIS#<ulid>`           | —                         |
| Interview record   | `APPLICATION#<slug>`      | `INTERVIEW#<stage>`         | —                         |

**Access patterns:**
- `GET /applications` → Query `GSI1` where `gsi1pk = APPLICATION#<status>`
- `GET /applications/:slug` → `GetItem` + optional sort-key prefix query
- `DELETE /applications` (batch) → `BatchWriteItem` for all items with `pk = APPLICATION#<slug>`

#### Resumes

| Item Type    | `pk`              | `sk`       | `gsi1pk`          |
|-------------|-------------------|------------|-------------------|
| Resume record| `RESUME#<uuid>`   | `METADATA` | `RESUME#<status>` (e.g., `RESUME#active`) |

**Access patterns:**
- `GET /resumes` → Query `GSI1` where `gsi1pk = RESUME#active`
- `POST /resumes/activate/:id` → `UpdateItem` on target + `UpdateItem` to deactivate previous active

#### Comments

| Item Type       | `pk`              | `sk`                          | `gsi1pk`           |
|----------------|-------------------|-------------------------------|-------------------|
| Comment record  | `ARTICLE#<slug>`  | `COMMENT#<timestamp>#<uuid>` | `COMMENT#pending`  |

**Access patterns:**
- `GET /comments/pending` → Query `GSI1` where `gsi1pk = COMMENT#pending`
- `POST /comments/:id/moderate` → `UpdateItem` sets `status` + updates `gsi1pk` to `COMMENT#approved` or `COMMENT#rejected`
- `DELETE /comments/:id` → `DeleteItem` + conditional counter decrement

---

## 5. Route-by-Route Deep Dive

### 5.1 `articles.ts` — Content Management

**Pattern:** GSI-first query, async Lambda trigger

```typescript
// List → GSI query by status (no scan)
QueryCommand({ IndexName: GSI1, KeyConditionExpression: 'gsi1pk = :pk' })

// Trigger article pipeline → fire-and-forget
LambdaClient.send(new InvokeCommand({ InvocationType: 'Event', ... }))
```

**Key behaviour:** After a `PUT /articles/:slug/publish`, the route asynchronously invokes the **article pipeline trigger Lambda**. The HTTP response returns `202` immediately — the pipeline runs in the background.

---

### 5.2 `applications.ts` — Job Application Management

**Pattern:** Multi-item batch delete, GSI-based filtering

```typescript
// Batch delete all items for a slug (metadata + analysis records)
BatchWriteItemCommand({ RequestItems: { [TABLE]: deleteRequests } })
```

**Key behaviour:**
- Supports filtering by `status` via the GSI.
- Batch delete is critical: it removes *all* sort-key variants (`METADATA`, `ANALYSIS#*`, `INTERVIEW#*`) in a single operation to prevent orphaned records.

---

### 5.3 `pipelines.ts` — Pipeline Trigger Proxy

**Pattern:** Dual invocation modes depending on caller needs

```typescript
// Fire-and-forget (async) — article pipeline
InvokeCommand({ InvocationType: 'Event' })

// Synchronous (RequestResponse) — when slug is needed immediately
InvokeCommand({ InvocationType: 'RequestResponse' })
```

**Key behaviour:** This route acts as a thin typed proxy. It accepts a structured JSON body from the admin UI and forwards it to the pipeline Lambda. The `RequestResponse` mode is used when the pipeline returns a value (e.g., a generated `applicationSlug`) that the UI needs before navigating.

---

### 5.4 `resumes.ts` — Resume Lifecycle

**Pattern:** Exclusive activation (deactivate old → activate new as atomic-ish DynamoDB ops)

```typescript
// Deactivate previous active resume
UpdateCommand({ Key: { pk: `RESUME#${currentActiveId}`, sk: 'METADATA' },
  UpdateExpression: 'SET #status = :inactive, gsi1pk = :inactiveGsi' })

// Activate new resume
UpdateCommand({ Key: { pk: `RESUME#${id}`, sk: 'METADATA' },
  UpdateExpression: 'SET #status = :active, gsi1pk = :activeGsi' })
```

**Key behaviour:**
- Generates S3 presigned URLs for resume PDF access.
- Uses `@aws-sdk/s3-request-presigner` with a 1-hour TTL.
- Activation is **two sequential `UpdateItem` calls** — not a DynamoDB transaction. This means there's a small window where either 0 or 2 resumes could appear active if the process crashes between operations.

> **Note:** Consider wrapping this in a `TransactWriteCommand` to make the activation atomic.

---

### 5.5 `drafts.ts` — New Article Draft Upload

**Pattern:** S3 PutObject → S3 event notification → Lambda (without direct Lambda call)

```typescript
// Upload to S3 at drafts/<slug>.md
PutObjectCommand({ Bucket: config.assetsBucketName, Key: `drafts/${slug}.md`, Body: content })
// The S3 bucket event notification automatically fires the trigger Lambda
```

**Key behaviour:** This route is deliberately separate from the article content update route. It handles **new** drafts only (no DynamoDB record exists yet). The S3 bucket is configured with an event notification in `pipeline-stack.ts` that automatically invokes the article pipeline trigger Lambda on any `PUT` to `drafts/*.md`.

> **Contrast with `pipelines.ts`:** The `pipelines.ts` route manually invokes the Lambda with a synthetic S3 event for cases where the S3 notification isn't configured (e.g., local dev). `drafts.ts` relies on the native S3→Lambda trigger.

---

### 5.6 `finops.ts` — Observability & Cost Metrics

**Pattern:** Read-only CloudWatch `GetMetricData` + Cost Explorer aggregation

```typescript
// CloudWatch: single query fetching multiple metrics in one API call
GetMetricDataCommand({ MetricDataQueries: [{ Id: 'inputTokens', ... }, ...] })

// Cost Explorer: always us-east-1, filtered by Project=bedrock tag
GetCostAndUsageCommand({ Filter: { Tags: { Key: 'Project', Values: ['bedrock'] } } })
```

**Four endpoints and their CloudWatch namespaces:**

| Endpoint         | Namespace                              | Key Metrics |
|-----------------|----------------------------------------|-------------|
| `/realtime`     | `BedrockMultiAgent`                    | InputTokens, OutputTokens, ThinkingTokens, ProcessingDurationMs |
| `/costs`        | AWS Cost Explorer (global)             | UnblendedCost grouped by inference profile |
| `/chatbot`      | `BedrockChatbot` (env=development)     | InvocationCount, BlockedInputs, RedactedOutputs |
| `/self-healing` | `self-healing-development/SelfHealing` | InputTokens, OutputTokens |

**Key behaviour:**
- The `collapseMetrics()` helper takes the first value from each time-series result — suitable for the "total over period" view but lossy for trend data.
- All endpoints accept `?days=N` (default 7, max 365), converting to a single CloudWatch period (`days × 86400` seconds). This means results are **aggregated into one data point**, not a time-series.
- Cost Explorer gracefully returns `{ costs: [] }` on failure rather than propagating errors.

---

### 5.7 `comments.ts` — Comment Moderation

**Pattern:** GSI pending queue, two-phase moderation (update status → adjust counter)

```typescript
// Pending queue (GSI-first, no scan)
QueryCommand({ IndexName: GSI1, KeyConditionExpression: 'gsi1pk = :pk',
  ExpressionAttributeValues: { ':pk': 'COMMENT#pending' } })

// Moderate: update status + GSI key atomically in one UpdateItem
UpdateCommand({ UpdateExpression: 'SET #status = :status, gsi1pk = :gsi1pk' })

// Counter management (separate UpdateItem with ADD)
UpdateCommand({ Key: { pk: `ARTICLE#${slug}`, sk: 'COUNTERS' },
  UpdateExpression: 'ADD commentCount :inc', ExpressionAttributeValues: { ':inc': 1 } })
```

**Key behaviour:**
- The composite ID format `slug__sk` (double underscore separator) is URL-decoded before parsing. The `parseCompositeId()` helper uses `slice(1).join('__')` to handle sort-key values that themselves contain `__`.
- Counter increment on approval and decrement on deletion are **separate `UpdateItem` calls**, not part of a transaction. Same atomicity risk as the resume activation pattern.

---

## 6. Cross-Cutting Concerns

### 6.1 Authentication Flow

```
Request → Hono middleware (auth.ts)
          │  Extract Bearer token
          ▼
      jose.jwtVerify()
          │  JWKS fetched from Cognito (cached in-memory)
          ▼
      Claims validated → ctx.set('user', payload)
          │
          ▼
      Route handler executes
```

- JWKS URL: `https://cognito-idp.<region>.amazonaws.com/<userPoolId>/.well-known/jwks.json`
- The JWKS is cached by `jose`'s `createRemoteJWKSet()` — avoids a network call per request.

### 6.2 Configuration Management (Fail-Fast Pattern)

```typescript
// loadConfig() is called at startup in index.ts
// If any env var is missing → throws → CrashLoopBackOff in K8s
const config = loadConfig();
```

All required variables sourced from Kubernetes:
- `admin-api-secrets` (K8s Secret): `COGNITO_USER_POOL_ID`, `COGNITO_CLIENT_ID`, `COGNITO_REGION`
- `admin-api-config` (K8s ConfigMap): `DYNAMODB_TABLE_NAME`, `DYNAMODB_GSI1_NAME`, `ARTICLE_TRIGGER_LAMBDA_ARN`, `STRATEGIST_TRIGGER_LAMBDA_ARN`, `ASSETS_BUCKET_NAME`, `AWS_REGION`

### 6.3 AWS SDK Client Pattern (Lazy Singletons)

Each route module maintains its own **module-level lazy singleton** for AWS clients:

```typescript
let _docClient: DynamoDBDocumentClient | null = null;

function getDocClient(region: string): DynamoDBDocumentClient {
  if (!_docClient) {
    _docClient = DynamoDBDocumentClient.from(new DynamoDBClient({ region }), {
      marshallOptions: { removeUndefinedValues: true },
    });
  }
  return _docClient;
}
```

> **Note:** `removeUndefinedValues: true` is set on all DynamoDB Document Clients — this silently drops `undefined` fields during marshalling rather than throwing. Useful for partial updates, but can mask missing required fields if types aren't strict.

### 6.4 Error Handling Conventions

| Route Module  | Error Strategy |
|--------------|----------------|
| `finops.ts`   | Graceful: returns empty arrays/zero values on AWS SDK failures |
| `drafts.ts`   | Propagates: returns `500` with error message on S3 failure |
| `comments.ts` | Mixed: GSI query failures return empty arrays; not-found returns `404` |
| `articles.ts` | Propagates: most errors bubble up as `500` |
| `applications.ts` | Propagates: unhandled errors return `500` |

---

## 7. Identified Design Issues & Recommendations

### 🔴 High Priority

#### 1. Non-Atomic Resume Activation (`resumes.ts`)
Two sequential `UpdateItem` calls for deactivate-then-activate create a window where 0 or 2 resumes are active if the process crashes between them.

**Fix:** Use `TransactWriteCommand`:
```typescript
await client.send(new TransactWriteCommand({
  TransactItems: [
    { Update: { /* deactivate old */ } },
    { Update: { /* activate new */ } },
  ],
}));
```

#### 2. Non-Atomic Comment Counter (`comments.ts`)
`commentCount` is updated in a separate `UpdateItem` after moderation/deletion. If the process crashes between them, the counter drifts from reality.

**Fix:** Use `TransactWriteCommand` to combine the status update and counter adjustment.

---

### 🟡 Medium Priority

#### 3. FinOps Single-Point-in-Time Aggregation
`collapseMetrics()` takes `res.Values[0]` — the first (newest) value in the CloudWatch response. When `periodInSeconds = days × 86400`, there should only be one aggregated data point returned, so this is correct *today*. However, if the period is ever shorter than the time range, multiple values will be silently discarded.

**Fix:** Sum or average all values explicitly:
```typescript
stats[res.Id] = res.Values.reduce((sum, v) => sum + v, 0);
```

#### 4. `drafts.ts` — Region Hardcoding Fallback
```typescript
const region = process.env['AWS_REGION'] ?? process.env['AWS_DEFAULT_REGION'] ?? 'eu-west-1';
```
This singleton S3 client is created outside the router factory and uses `process.env` directly rather than `config.awsRegion`. All other routes use `config.awsRegion` consistently. If the K8s config changes the region, the drafts S3 client won't pick it up.

**Fix:** Pass `config.awsRegion` to `createDraftsRouter` and use it for the S3 client, same pattern as `finops.ts`.

#### 5. Partial `comments.ts` DynamoDB Client — Not Using Shared `dynamo.ts`
The `comments.ts` and `finops.ts` modules create their own DynamoDB/CloudWatch clients rather than importing from the shared `lib/dynamo.ts` singleton. This results in multiple client instances in the process.

**Fix:** Extend `lib/dynamo.ts` to export the `DynamoDBDocumentClient` singleton and use it across all route modules.

---

### 🟢 Low Priority / Observations

#### 6. `pipelines.ts` — No Retry or Timeout on Lambda Invocations
Lambda invocations have no explicit timeout configured. If the downstream Lambda is slow or cold-starting, the HTTP request from the admin UI will hang.

**Fix:** Set `clientConfig.requestHandler` with a timeout, or add a configurable timeout via `AbortSignal`.

#### 7. Comment Composite ID — URL Encoding Requirement
The `/:id` pattern for comments requires the composite `slug__sk` to be URL-encoded by the client. This is documented but not validated — if the client sends a non-encoded `#` character in the sort key, the router will split it incorrectly.

**Fix:** Document clearly in OpenAPI/client types, or consider base64-encoding the composite ID.

---

## 8. Dependency Summary

```json
{
  "@aws-sdk/client-cloudwatch":    "CloudWatch metrics (finops)",
  "@aws-sdk/client-cost-explorer": "Cost data (finops)",
  "@aws-sdk/client-dynamodb":      "Low-level DynamoDB",
  "@aws-sdk/client-lambda":        "Pipeline invocations",
  "@aws-sdk/client-s3":            "Draft uploads",
  "@aws-sdk/lib-dynamodb":         "Document-layer marshalling",
  "@aws-sdk/s3-request-presigner": "Presigned URL generation (resumes)",
  "@hono/node-server":             "Node.js HTTP adapter for Hono",
  "hono":                          "Web framework",
  "jose":                          "JWT/JWKS validation (Cognito)"
}
```

---

## 9. Summary

The `admin-api` is a **well-structured, lean BFF** with clear separation of concerns. Key strengths:

- ✅ **Fail-fast config** prevents misconfigured deployments from serving traffic silently.
- ✅ **GSI-first access patterns** avoid expensive table scans across all entity types.
- ✅ **Zero secrets in code** — all credentials via IMDS/K8s injection.
- ✅ **Dual Lambda invocation modes** (async event vs. sync request-response) provide flexibility for different pipeline use cases.
- ✅ **Graceful FinOps degradation** — observability endpoints never crash the API on AWS SDK failures.

The three items most worth addressing are the **non-atomic dual-`UpdateItem` patterns** (resumes + comments) and the **`drafts.ts` region inconsistency**, as these represent correctness risks in production.
