# Code Review — New Analysis Form Submission Flow

**Scope:** `NewAnalysisPanel.tsx`, `applications.ts`, `pipelines.ts`, `use-applications-trigger.ts`, `auth-guard.ts`, `applications.types.ts`

---

## 1. Architecture Overview

The analysis form submission traverses **four distinct layers**:

```
Browser (React form)
  │  @tanstack/react-form — useForm + onSubmit
  ▼
TanStack Query Mutation
  │  useApplicationsTrigger → useMutation
  ▼
TanStack Start Server Function (runs server-side)
  │  triggerApplicationsAnalysisFn → createServerFn
  ▼
admin-api BFF (in-cluster HTTP)
  │  POST /api/admin/pipelines/strategist
  ▼
AWS Lambda (Strategist trigger handler)
  │  Step Functions StartExecution
  ▼
State Machine (Research → Applications agents)
```

The frontend pod carries **zero AWS SDK dependencies** — all infrastructure calls are delegated to `admin-api`.

---

## 2. UI Layer — `NewAnalysisPanel.tsx`

### 2.1 Form State

Built with `@tanstack/react-form`. Default values:

| Field | Type | Default |
|---|---|---|
| `jobDescription` | `string` | `''` (or draft) |
| `targetCompany` | `string` | `''` (or draft) |
| `targetRole` | `string` | `''` (or draft) |
| `interviewStage` | `InterviewStage` | `'applied'` (or draft) |
| `includeCoverLetter` | `boolean` | `true` (or draft) |
| `testMode` | `boolean` | `false` (never persisted) |

### 2.2 Draft Persistence

- **On every render/change**: `DraftSaver` component saves all form values to `localStorage` key `application-form-draft` via a `useEffect` subscribed to `form.Subscribe`.
- **On page load**: The `[initialDraft]` state is initialised once from `localStorage` (safe-parsed JSON, falls back to `null`).
- **On success / clear**: `localStorage.removeItem('application-form-draft')` is called explicitly.
- `testMode` is excluded from draft reads (always starts as `false`).

### 2.3 Client-Side Validation Gate

The submit button is only enabled when **all three conditions pass**:

```ts
jd.length >= MIN_JD_LENGTH   // MIN_JD_LENGTH = 50 chars
&& company.trim().length > 0
&& role.trim().length > 0
```

There is **no Zod validation on the client** — the gate is purely a UI check driven by `form.Subscribe`.

### 2.4 Test Mode Path

When `testMode === true`:
- Draft is cleared, form reset.
- `submittedSlug` is set to `mock-${Date.now()}` — immediately renders `ProgressBars` with a fake slug.
- **No network call is made.**

### 2.5 Happy Path — `onSubmit`

```ts
trigger.mutate(
  {
    jobDescription: value.jobDescription,
    targetCompany: company,         // trimmed
    targetRole: role,               // trimmed
    interviewStage: value.interviewStage,
    resumeId: preselectedResumeId,  // from parent prop
    includeCoverLetter: value.includeCoverLetter,
  },
  {
    onSuccess: (data) => {
      localStorage.removeItem('application-form-draft')
      form.reset()
      setSubmittedSlug(data.applicationSlug)
      addNotification({ ... })
      // onSuccess prop is NOT called — ProgressBars takes over navigation
    },
  }
)
```

> [!NOTE]
> `interviewStage` is included in the mutation body, but **it is intentionally dropped** at the server layer before reaching the Lambda (documented in `pipelines.ts` line 290). The Lambda hardcodes `'applied'` for analyse runs. The field is stored locally on the DynamoDB record by the admin-api or the Lambda side-effect, not via this trigger path.

### 2.6 Retry Event Listener

```ts
window.addEventListener('application-retry', handleRetry)
```

An external component (e.g. a failed application card) can dispatch a `CustomEvent` with `{ targetCompany, targetRole, interviewStage }` to pre-fill the form fields. This is a loose coupling via browser events.

### 2.7 Post-Submission State

When `submittedSlug` is set, the entire form is replaced by `<ProgressBars slug={submittedSlug} />`, which polls pipeline status until completion.

---

## 3. Mutation Hook — `use-applications-trigger.ts`

```ts
useMutation<TriggerResponse, Error, AnalyseTriggerBody>({
  mutationFn: (data) => triggerApplicationsAnalysisFn({ data }),
  onSuccess: () => {
    void queryClient.invalidateQueries({ queryKey: adminKeys.applications.all })
  },
})
```

- **Typed generics**: `TriggerResponse` (response), `Error` (error), `AnalyseTriggerBody` (variables).
- On success, the applications list query cache is **invalidated** — the dashboard list will re-fetch.
- The `onSuccess` callback in `mutate(data, { onSuccess })` at the call site runs **after** the hook-level `onSuccess`.

### Payload Type — `AnalyseTriggerBody`

```ts
interface AnalyseTriggerBody {
  readonly jobDescription: string
  readonly targetCompany: string
  readonly targetRole: string
  readonly interviewStage?: InterviewStage   // optional
  readonly resumeId?: string                 // optional
  readonly includeCoverLetter?: boolean      // optional
}
```

---

## 4. Server Function — `triggerApplicationsAnalysisFn` (in `pipelines.ts`)

### 4.1 Input Schema (Zod Validation)

```ts
const analyseTriggerSchema = z.object({
  jobDescription: z.string(),
  targetCompany: z.string(),
  targetRole: z.string(),
  interviewStage: z.enum([
    'applied', 'phone-screen', 'technical',
    'system-design', 'behavioural', 'bar-raiser', 'final'
  ]).optional(),
  resumeId: z.string().optional(),
  includeCoverLetter: z.boolean().optional(),
})
```

> [!IMPORTANT]
> **`jobDescription` and `targetCompany`/`targetRole` have no minimum length validation in the Zod schema.** The 50-char guard exists only on the client. Any direct call to this server function bypasses that constraint.

### 4.2 Authentication Gate

```ts
await requireAuth()
```

**First thing called in every handler.** Reads the `__session` HTTP-only cookie, verifies the JWT against Cognito JWKS. Throws `AuthenticationError` if:
- Cookie is absent
- JWT is expired
- JWT signature is invalid

If `requireAuth()` throws, the handler exits immediately — no BFF call is made.

### 4.3 Lambda Payload Construction

```ts
const lambdaPayload = {
  operation: 'analyse',          // discriminant field for the Lambda schema
  jobDescription: data.jobDescription,
  targetCompany: data.targetCompany,
  targetRole: data.targetRole,
  resumeId: data.resumeId ?? '',             // defaults to empty string
  includeCoverLetter: data.includeCoverLetter ?? true,
  // interviewStage is intentionally OMITTED
}
```

> [!WARNING]
> `interviewStage` collected from the form is **silently dropped here**. The Lambda's `AnalyseRequestSchema` uses `.strict()` — extra fields would cause a validation failure. The Lambda hardcodes the stage to `'applied'` for analyse operations. This is documented in the JSDoc but may confuse future maintainers.

### 4.4 BFF HTTP Call

```
POST http://admin-api.admin-api:3002/api/admin/pipelines/strategist
```

Headers sent:

| Header | Value |
|---|---|
| `Content-Type` | `application/json` |
| `Authorization` | `Bearer <JWT from __session cookie>` |

Body: `JSON.stringify(lambdaPayload)`

---

## 5. `apiFetch` Helper (`pipelines.ts`) — HTTP Error Handling

```ts
if (!res.ok) {
  let detail = ''
  try {
    const body = await res.json() as { error?: string }
    detail = body.error ? ` — ${body.error}` : ''
  } catch { /* ignore */ }
  throw new Error(
    `admin-api ${init?.method ?? 'GET'} ${path} failed [${res.status}]${detail}`
  )
}
```

This is the **more defensive** version (vs the one in `applications.ts` which uses `res.text()`). If admin-api returns a structured `{ error: string }` JSON body, the error message surfaces to the UI via `trigger.error.message`.

---

## 6. Server Functions in `applications.ts`

These are CRUD functions for **existing application records** — not used by the new analysis form submission.

| Function | Method | Route | Purpose |
|---|---|---|---|
| `getApplicationsFn` | GET | `/api/admin/applications?status=X` | List applications |
| `getApplicationDetailFn` | GET | `/api/admin/applications/:slug` | Get full detail |
| `deleteApplicationFn` | POST | `DELETE /api/admin/applications/:slug` | Delete record |
| `updateApplicationStatusFn` | POST | `POST /api/admin/applications/:slug/status` | Update status + stage |

All four call `requireAuth()` first. The `apiFetch` in `applications.ts` uses `res.text()` on error (less structured than the `pipelines.ts` variant).

### Status Update Payload

```ts
// updateApplicationStatusFn body
{
  status: string,           // e.g. 'interviewing'
  interviewStage?: string   // e.g. 'technical'
}
```

---

## 7. Auth Chain — End-to-End

```
Browser sends __session cookie (HTTP-only, set by Cognito callback)
  │
  ▼
TanStack Start server function executes
  │  requireAuth() → getCookie('__session') → verifyCognitoJwt(token)
  │  Throws AuthenticationError if invalid
  │
  ▼
getSessionToken() → reads same __session cookie
  │
  ▼
apiFetch → Authorization: Bearer <token>
  │
  ▼
admin-api re-verifies token against Cognito JWKS
```

**Double verification**: once in the frontend server function, once in admin-api. The `__session` cookie is read twice in the same request — harmless but worth noting.

---

## 8. Response — `TriggerResponse`

```ts
interface TriggerResponse {
  readonly pipelineId: string       // unique execution ID
  readonly applicationSlug: string  // kebab-case, e.g. "revolut-senior-devops-engineer"
  readonly status: 'analysing'      // always 'analysing' on trigger
  readonly executionArn: string     // Step Functions ARN
}
```

The `applicationSlug` is used immediately to:
1. Set `submittedSlug` (triggers ProgressBars render)
2. Build the notification link `/applications/:slug`
3. Call `addNotification()` in the pipeline notifications store

---

## 9. Design Observations & Gaps

### ✅ Strengths

- **Auth double-fence**: JWT verified at the SSR edge _and_ at admin-api. No unauthenticated BFF call is possible.
- **Draft persistence**: Robust — saves on every keystroke, removes on success or clear. Survives page refreshes.
- **Test Mode**: Clean separation — zero network calls, immediate feedback loop.
- **Type safety**: `AnalyseTriggerBody`, `TriggerResponse`, and all domain types are shared from a single `applications.types.ts` source of truth.
- **Cache invalidation**: Mutation hook invalidates the application list on success — consistent UI without manual refetching.

### ⚠️ Observations / Potential Issues

| # | Issue | Impact | Location |
|---|---|---|---|
| 1 | **`interviewStage` is silently dropped** — collected, validated, stored in draft, but never forwarded to the Lambda. The JSDoc explains this but the UI still shows it as a real input, which may confuse users. | Low–Medium | `pipelines.ts:319-326` |
| 2 | **Server-side has no minimum length on `jobDescription`** — Zod schema uses `z.string()` (no `.min()`). Direct calls bypass the 50-char gate. | Low | `pipelines.ts:109` |
| 3 | **`resumeId` falls back to `''` (empty string) instead of a sensible default** — `data.resumeId ?? ''`. An empty string may behave differently than `undefined` on the Lambda side. | Medium | `pipelines.ts:324` |
| 4 | **`getSessionToken()` is duplicated** — identical functions in both `applications.ts` and `pipelines.ts`. Should be a shared utility at `server/auth-guard.ts` or a `server/utils.ts`. | Low | Both files |
| 5 | **Two different `apiFetch` error strategies**: `applications.ts` uses `res.text()`, `pipelines.ts` uses `res.json()`. Inconsistent error message quality. | Low | Both files |
| 6 | **`ADMIN_API_URL` is duplicated** — defined identically in both `applications.ts` and `pipelines.ts`. | Low | Both files |
| 7 | **`onSuccess` prop is accepted but never called** (`_onSuccess` prefix confirms intentional suppression). The prop exists in the interface but its suppression is uncommented inline. | Low | `NewAnalysisPanel.tsx:29` |
| 8 | **`application-retry` event is loosely typed** — `e as CustomEvent` with no runtime shape check on `customEvent.detail`. Malformed events could set incorrect field values silently. | Low | `NewAnalysisPanel.tsx:96` |

---

## 10. Complete Data Flow Summary

```
User types in form
  → DraftSaver writes to localStorage on every keystroke

User clicks "Start Analysis"
  → e.preventDefault() + form.handleSubmit()
  → onSubmit({ value }) fires
  → testMode check (exit early if true)
  → trigger.mutate(AnalyseTriggerBody)

  TanStack Query sends to server function
  → triggerApplicationsAnalysisFn({ data: AnalyseTriggerBody })

  Server function (SSR context)
  → await requireAuth()               // verifies __session JWT via Cognito JWKS
  → builds lambdaPayload              // strips interviewStage, defaults resumeId/includeCoverLetter
  → apiFetch POST /api/admin/pipelines/strategist
      Headers: Content-Type: application/json, Authorization: Bearer <JWT>
      Body:    { operation, jobDescription, targetCompany, targetRole, resumeId, includeCoverLetter }

  admin-api (in-cluster)
  → re-verifies JWT
  → invokes Strategist trigger Lambda
  → Lambda starts Step Functions execution
  → returns { pipelineId, applicationSlug, status: 'analysing', executionArn }

  Back in UI
  → form.reset() + localStorage.removeItem()
  → setSubmittedSlug(data.applicationSlug)
  → addNotification(...)
  → ProgressBars renders and starts polling GET /pipeline-status/:slug
```
