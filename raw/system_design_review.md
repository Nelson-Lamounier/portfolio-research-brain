# System Design Review — `apps/site` & `apps/start-admin`

> **Scope:** `apps/site` (public portfolio) and `apps/start-admin` (admin dashboard)  
> **Monorepo root:** `frontend-portfolio` (Yarn 4 workspaces)  
> **Reviewed:** 2026-04-15

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Monorepo Architecture](#2-monorepo-architecture)
3. [apps/site — Public Portfolio (Next.js 15)](#3-appssite--public-portfolio-nextjs-15)
   - 3.1 Framework Choice & Rationale
   - 3.2 What the Application Does
   - 3.3 Application Tiers & Multi-Tier Architecture
   - 3.4 Web Server Design
   - 3.5 API Layer
   - 3.6 Data Store (DynamoDB)
   - 3.7 Caching Strategy
   - 3.8 CDN (CloudFront)
   - 3.9 HTTP Communication
   - 3.10 Styling (Tailwind CSS v4)
   - 3.11 TypeScript Usage
   - 3.12 Testing Suite
   - 3.13 Observability — Metrics, Traces & RUM
   - 3.14 Security Posture
   - 3.15 Containerisation & ECR Push
   - 3.16 How Users Access It
4. [apps/start-admin — Admin Dashboard (TanStack Start)](#4-appsstart-admin--admin-dashboard-tanstack-start)
   - 4.1 Framework Choice & Rationale
   - 4.2 What the Application Does
   - 4.3 Application Tiers
   - 4.4 Web Server Design
   - 4.5 API Layer (BFF Pattern)
   - 4.6 Authentication (Cognito OAuth PKCE)
   - 4.7 Styling
   - 4.8 TypeScript Usage
   - 4.9 Testing Suite
   - 4.10 Observability
   - 4.11 Security Posture
   - 4.12 Containerisation
5. [Comparative Analysis: site vs start-admin](#5-comparative-analysis-site-vs-start-admin)
6. [Supporting Infrastructure](#6-supporting-infrastructure)
7. [Best Practices Assessment](#7-best-practices-assessment)
8. [Gaps & Recommendations](#8-gaps--recommendations)

---

## 1. Executive Summary

This is a **3-tier, multi-application monorepo** deployed on Kubernetes (K3s/kubeadm on AWS EC2)
with a CloudFront CDN edge. The system comprises two distinct frontend applications with fundamentally
different responsibilities:

| Application | Framework | Purpose | Auth |
|---|---|---|---|
| `apps/site` | Next.js 15 (App Router) | Public-facing portfolio, blog, AI chat | None (public) |
| `apps/start-admin` | TanStack Start (Vinxi/Vite SSR) | Private admin dashboard | AWS Cognito PKCE |

Both apps are fully written in **TypeScript** with `strict: true`, styled with **Tailwind CSS v4**,
containerised with multi-stage Docker builds on **Amazon Linux 2023**, and deployed via ArgoCD GitOps.
The backend data tier is **AWS DynamoDB** (single-table design) with assets in **S3**. A separate
`admin-api` Express service acts as the authenticated BFF between the admin UI and AWS services.

---

## 2. Monorepo Architecture

```
frontend-portfolio/           ← Yarn 4 workspace root
├── apps/
│   ├── site/                 ← Next.js 15 public portfolio (port 3000)
│   └── start-admin/          ← TanStack Start admin dashboard (port 5001)
├── packages/
│   ├── shared/               ← Shared lib, types, UI components
│   └── ui/                   ← (secondary UI package)
├── Dockerfile                ← Multi-stage build (supports both apps via ARG APP_NAME)
└── apps/start-admin/Dockerfile  ← Start-admin-specific multi-stage build
```

The shared `packages/shared` workspace exposes three key path aliases used by both apps:
- `@/lib/*` → shared utilities (auth, observability, API clients)
- `@/types/*` → shared TypeScript interfaces
- `@/components/ui/*` → shared React UI primitives

---

## 3. apps/site — Public Portfolio (Next.js 15)

### 3.1 Framework Choice & Rationale

**Next.js 15** (App Router) was chosen for several concrete reasons:

1. **Server-Side Rendering (SSR) + Static Generation (SSG):** The public portfolio benefits from
   pre-rendered HTML for SEO, fast first-paint for visitors, and on-demand ISR for articles pulled
   from DynamoDB.
2. **Built-in API Routes:** Next.js collocates backend API handlers (`/app/api/*/route.ts`) with
   the React frontend, removing the need for a separate Express server for the public site.
3. **Next/Image optimisation:** Automatic WebP conversion, responsive sizing, lazy loading.
4. **MDX support:** Blog articles can be authored as MDX files via `@next/mdx`, with `remark-gfm`
   and `rehype-prism-plus` for syntax highlighting.
5. **Standalone output mode:** `output: 'standalone'` produces a minimal Node.js bundle ideal for
   containerised Kubernetes deployments — no full `node_modules` needed at runtime.
6. **Instrumentation hook:** Next.js 15.5's built-in instrumentation hook (`src/instrumentation.ts`)
   enables OpenTelemetry SDK initialisation without third-party wrappers.
7. **Ecosystem maturity:** `@tanstack/react-query`, `framer-motion`, `zustand`, `next-themes` all
   integrate cleanly with App Router patterns.

### 3.2 What the Application Does

`apps/site` is the **public-facing portfolio website** at `nelsonlamounier.com`. It:

- Renders a personal homepage, about page, projects showcase, and music section.
- Hosts a technical **blog** (`/articles`) backed by DynamoDB + S3 content.
- Exposes an **AI chat assistant** (`/api/chat`) that proxies to a Bedrock Agent via API Gateway.
- Generates an **RSS feed** (`/feed.xml`) for article syndication.
- Provides a **resume** page with PDF export (`jsPDF` + `html2canvas-pro`).
- Exposes `/api/metrics` for **Prometheus scraping**.
- Exposes `/api/health` for **Kubernetes health checks**.

It has **no authentication** — it is entirely public.

### 3.3 Application Tiers & Multi-Tier Architecture

This is a **3-tier application**:

| Tier | Component | Technology |
|---|---|---|
| **Presentation** | React 19 components (App Router) | Next.js 15, Tailwind CSS v4, Framer Motion |
| **Application/API** | Next.js API Routes + Server Components | Node.js runtime, AWS SDK v3 |
| **Data** | DynamoDB (articles, resume) + S3 (MDX content) | AWS DynamoDB, S3 |

The **edge layer** (CloudFront + WAF) is an additional tier ahead of the presentation layer,
making this effectively a **4-tier** system in production:

```
Browser → CloudFront (CDN/WAF) → K8s Ingress (Traefik) → Next.js Pod → DynamoDB / S3 / Bedrock
```

### 3.4 Web Server Design

Next.js runs its own **Node.js HTTP server** (the standalone `server.js` bundle). In Kubernetes:

- Deployed as a **K8s Deployment** behind a **ClusterIP Service**.
- Exposed externally via **Traefik IngressRoute** → **NLB** → **CloudFront**.
- Port: `3000`
- Graceful signal handling: `SIGTERM` / `SIGINT` trigger the OTel SDK shutdown.
- Docker `HEALTHCHECK` hits `GET /api/health` every 30s.

The `next.config.mjs` also configures **rewrites** (a proxy layer within Next.js):
- `/log-proxy` → Faro collector at `ops.nelsonlamounier.com`
- `/admin/*` → `start-admin` pod at `localhost:3001` (dev-time co-location)

### 3.5 API Layer

Seven API route groups under `src/app/api/`:

| Route | Method | Purpose |
|---|---|---|
| `/api/articles/[slug]` | `GET` | Fetches individual article from DynamoDB |
| `/api/chat` | `POST` | Server-side proxy → Bedrock Agent API Gateway |
| `/api/health` | `GET` | Kubernetes liveness/readiness probe |
| `/api/metrics` | `GET` | Prometheus metrics exposition (Bearer auth via SSM) |
| `/api/resume` | `GET` | Resume data from DynamoDB |
| `/api/revalidate` | `POST` | On-demand ISR cache revalidation |
| `/api/track-error` | `POST` | Client-side error reporting endpoint |

All routes are typed TypeScript, use `NextResponse.json()` and follow RESTful conventions.
The `/api/metrics` route is notable — it implements **SSM-backed Bearer token auth** with
a 5-minute in-memory cache and 60-second backoff on SSM failures to prevent Prometheus
scrapes from hammering a broken SSM path.

### 3.6 Data Store (DynamoDB)

The primary data store is **AWS DynamoDB** (single-table design accessed via `@aws-sdk/lib-dynamodb`):

- **Articles table:** Stores article metadata (title, excerpt, status, tags, dates).
  Content (MDX body) lives in **S3** and is referenced via a `contentRef` field.
- **Resume table:** Stores structured resume data for the `/resume` page.
- **Single-table design:** GSI (`gsi1pk`) for tag-based queries.

The app also has migration scripts (`scripts/dynamodb/`) for seeding and schema evolution,
demonstrating operational maturity. There is **no relational database** (no RDS/Postgres).

No **Redis** or in-process cache layer exists for DynamoDB reads. Next.js's own fetch cache
(`revalidate`) handles ISR, but there is no explicit cache invalidation layer independent
of the revalidate API.

### 3.7 Caching Strategy

| Level | Mechanism | TTL |
|---|---|---|
| **CDN** | CloudFront (`Cache-Control: public, max-age=...`) | Per-page/asset |
| **Next.js ISR** | On-demand revalidation via `/api/revalidate` | On-demand |
| **Metrics bearer token** | In-memory (`cachedToken`) | 5 min |
| **Static assets** | `_next/static` (content-hashed, 1-year TTL at CloudFront) | 1 year |

There is no Redis/Elasticache layer. For a portfolio-scale workload this is appropriate —
DynamoDB reads are fast and ISR provides sufficient HTML caching.

### 3.8 CDN (CloudFront)

CloudFront sits in front of the Kubernetes NLB:

- **Origin:** NLB → Traefik → Next.js pod.
- **SSL termination:** CloudFront handles HTTPS; backend traffic is HTTP within the VPC.
- **WAF:** AWS WAF rate-limiting rules applied at the CloudFront distribution.
- **Static assets:** `_next/static/**` served with long cache TTLs (content-hashed filenames).
- **No message queue** is present in this path.

### 3.9 HTTP Communication

- **Browser → CloudFront:** HTTPS (TLS 1.2/1.3).
- **CloudFront → NLB → Traefik → Pod:** HTTP within VPC.
- **Next.js → DynamoDB:** AWS SDK v3 (HTTPS to AWS endpoint).
- **Next.js → S3:** AWS SDK v3 (HTTPS).
- **Next.js → Bedrock Agent API Gateway:** `fetch()` over HTTPS with API key auth.
- **Next.js → OTel Collector (Alloy sidecar):** gRPC (OTLP protocol) on `localhost:4317`.
- **Prometheus → `/api/metrics`:** HTTP with Bearer token.

**No WebSocket or message queue** (SQS/SNS) is used by `apps/site` itself. The Bedrock
publish pipeline (triggered from the admin side) uses Lambda asynchronously, but that
is backstage to the site.

### 3.10 Styling (Tailwind CSS v4)

`apps/site` uses **Tailwind CSS v4** (`tailwindcss: ^4.1.15`) with the PostCSS plugin:

- Entry point: `src/styles/tailwind.css` — uses the new `@import 'tailwindcss'` v4 syntax.
- `@source` directive points at `packages/shared/src` to scan shared components.
- `@plugin '@tailwindcss/typography'` for prose styling.
- Custom dark variant: `@custom-variant dark (&:where(.dark, .dark *))`.
- Custom type scale via `@theme` CSS variables.
- **No vanilla CSS files** for layout — everything is utility-first Tailwind.
- `prism.css` is the only raw CSS file, imported for code block syntax themes.
- `framer-motion` provides animation.
- `next-themes` + `ThemeProvider` for dark/light mode switching.

### 3.11 TypeScript Usage

- `tsconfig.json`: `strict: true`, `isolatedModules: true`, `noEmit: true`.
- **No `any` types** in the reviewed server modules.
- All API routes, server functions, and component props are fully typed.
- Zod v4 for runtime validation (`zod: ^4.3.6`).
- `@types/node`, `@types/react`, `@types/react-dom` are all present.
- `next-env.d.ts` provides Next.js ambient types.

### 3.12 Testing Suite

`apps/site` has **Jest** as its test framework (`jest: ^30.2.0`) with `jest-environment-jsdom`:

| Test Type | Files | Coverage |
|---|---|---|
| **Unit — API routes** | `__tests__/api/health.test.ts`, `metrics.test.ts` | Health check, Prometheus metrics, auth |
| **Unit — Library** | `__tests__/lib/article-service.test.ts`, `rate-limiter.test.ts` | Article service, rate limiting |
| **Integration — UI flows** | `__tests__/integration/*.test.tsx` | Articles flow, navigation, project filters |
| **Unit — Pages** | `__tests__/app/page.test.tsx` (+ sub-pages) | Homepage, articles, music, projects |

Test tooling: `@testing-library/react`, `@testing-library/user-event`, `@testing-library/jest-dom`.  
Scripts: `yarn test`, `yarn test:watch`.

> [!NOTE]
> Integration tests exercise React component trees with mocked fetch — they test rendering
> and user interaction flows, not live HTTP endpoints against a running server.

### 3.13 Observability — Metrics, Traces & RUM

This is one of the most sophisticated aspects of the system:

#### Distributed Traces (OpenTelemetry)

`src/instrumentation.ts` initialises the OTel Node.js SDK on server start:

- **Exporter:** OTLP/gRPC → Alloy sidecar sidecar (co-located in the K8s pod) → **Grafana Tempo**.
- **Propagation:** W3C TraceContext (`traceparent`/`tracestate` headers).
- **Auto-instrumentation:**
  - `@opentelemetry/instrumentation-aws-sdk` — traces all DynamoDB/S3/Lambda calls automatically.
  - `@opentelemetry/instrumentation-http` — traces incoming HTTP requests.
  - FS/DNS/Net instrumentation disabled (too noisy).
- **Resource detection:** `awsEcsDetector` attaches ECS task ARN, cluster, and container metadata
  (note: the pod actually runs on K8s — the ECS detector may not resolve fully, but this is
  harmless — it falls back gracefully).
- **AWS X-Ray ID generator:** `@opentelemetry/id-generator-aws-xray` for compatibility.

#### Prometheus Metrics

`src/app/api/metrics/route.ts` exposes a Prometheus scrape endpoint:

Collected metrics (via `prom-client`):
- **Request duration** (`http_request_duration_seconds`) — histogram, tracked per path/method/status.
- **Request size** (`http_request_size_bytes`) — histogram.
- **API call counter** (`http_api_calls_total`) — counter for `/api/*` paths.
- Default Node.js runtime metrics (heap, GC, event loop lag) from `prom-client` default collection.

The endpoint is scraped by the in-cluster **Prometheus** instance every 15–30 seconds.
Auth is via a Bearer token fetched from **SSM Parameter Store** (5-minute cache, 60s backoff).

#### Real User Monitoring (RUM)

`providers.tsx` calls `initialiseFaro()` on mount (client-side only):

- **Grafana Faro Web SDK** (`@grafana/faro-web-sdk`, `@grafana/faro-web-tracing`).
- Collects: page views, unhandled errors, performance data, session info.
- Telemetry sent to `https://ops.nelsonlamounier.com/faro/collect` via the `/log-proxy` Next.js
  rewrite (avoids CORS issues by keeping the browser request on the same origin).

**Summary of observability signals collected:**

| Signal | Tool | Sink |
|---|---|---|
| Distributed traces | OpenTelemetry (OTLP/gRPC) | Alloy → Tempo |
| Infrastructure metrics | Prometheus (`prom-client`) | Prometheus → Grafana |
| Real-user monitoring | Grafana Faro | Faro collector |
| AWS SDK spans | OTel auto-instrumentation | Tempo |

### 3.14 Security Posture

`src/middleware.ts` applies security headers to **every response**:

| Header | Value | Purpose |
|---|---|---|
| `X-Content-Type-Options` | `nosniff` | Prevent MIME sniffing |
| `X-Frame-Options` | `DENY` | Clickjacking protection |
| `X-XSS-Protection` | `0` | Disable legacy XSS filter (modern CSP preferred) |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | Referrer leakage control |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=()` | Feature policy |
| `Strict-Transport-Security` | `max-age=63072000; includeSubDomains; preload` | Force HTTPS for 2 years |

Additional protections:
- **CloudFront WAF** rate limiting.
- **API key** hidden server-side for Bedrock Agent (never exposed to browser).
- `/api/metrics` protected by SSM-backed Bearer auth.
- Non-root Docker user (`nextjs:nodejs`, UID 1001).

> [!WARNING]
> No **Content Security Policy** header is set by the middleware. This is a gap —
> a CSP would significantly reduce XSS impact. The admin app (`start-admin`) does
> implement a CSP via TanStack middleware.

### 3.15 Containerisation & ECR Push

The monorepo root `Dockerfile` is a **4-stage multi-stage build**:

1. **base** — Amazon Linux 2023 + Node.js 22 LTS + Corepack (Yarn 4).
2. **deps** — Installs all workspace dependencies (`yarn install --immutable`).
3. **builder** — Runs `yarn workspace site build --no-lint` (Next.js standalone output).
4. **runner** — Minimal AL2023 + Node.js 22 runtime, copies only the `.next/standalone` output.

The build accepts `ARG APP_NAME=site` so the same Dockerfile builds either app.

**ECR push via GitHub Actions CI/CD:**
1. `docker build` with build args (`NEXT_PUBLIC_API_URL`, `APP_NAME`).
2. `docker push` to the ECR repository (`<account>.dkr.ecr.<region>.amazonaws.com/site`).
3. ArgoCD watches the ECR image tag and syncs the K8s Deployment.

OTel is **disabled by default** in the container (`OTEL_SDK_DISABLED=true`) and enabled
via a K8s pod annotation/env var override in the cluster.

### 3.16 How Users Access It

```
User Browser
    │
    ▼ HTTPS (443)
CloudFront Distribution (nelsonlamounier.com)
    │  ← WAF rules, cache headers
    ▼ HTTP
AWS NLB (network load balancer)
    │
    ▼
Traefik IngressRoute (K8s)
    │
    ▼
nextjs-site Pod (port 3000)
    │  ← DynamoDB, S3, Bedrock Agent (via Next.js API routes)
    ▼
Response → Traefik → NLB → CloudFront → Browser
```

---

## 4. apps/start-admin — Admin Dashboard (TanStack Start)

### 4.1 Framework Choice & Rationale

**TanStack Start** (built on Vinxi + Vite) was chosen instead of Next.js for the admin app because:

1. **Full-stack type-safety without a separate API layer:** TanStack Start's `createServerFn`
   compiles server functions that are called from the client but execute server-side — the
   RPC contract is completely type-safe.
2. **TanStack Router integration:** File-based routing with nested layouts, type-safe navigation,
   and first-class SSR query integration (`@tanstack/react-router-ssr-query`).
3. **Vite build pipeline:** Faster HMR, lighter config, and seamless Tailwind v4 integration
   via the `@tailwindcss/vite` plugin.
4. **BFF pattern clarity:** The admin app explicitly acts as a thin UI layer — all AWS operations
   are delegated to `admin-api`. `createServerFn` makes this BFF pattern first-class.
5. **No overkill:** The admin is a protected internal tool, not a public-facing page, so
   Next.js's ISR/SSG features bring no benefit.

### 4.2 What the Application Does

`apps/start-admin` is the **private CMS/admin dashboard** at `/admin/` (proxied through the
site). It provides:

- **Article management:** Create, edit (MDX editor), publish, unpublish, delete articles.
- **Draft publishing pipeline:** Triggers Bedrock AI enrichment Lambda via `admin-api`.
- **Resume management:** Edit resume data.
- **Applications tracker:** Job application tracking board.
- **Comments moderation:** Review user comments.
- **FinOps dashboard:** Cost reporting and AWS spend overview.
- **CI/CD pipeline viewer:** GitHub Actions pipeline status.
- **AI Agent integration:** Bedrock-backed AI assistance for article workflows.
- **Calendar:** Internal scheduling/event calendar.
- **Reports:** Analytics and traffic reports.

### 4.3 Application Tiers

| Tier | Component |
|---|---|
| **Presentation** | React 19 + TanStack Router (SSR) |
| **Application** | TanStack Start server functions (`createServerFn`) |
| **BFF** | `admin-api` Express service (separate K8s pod) |
| **Data** | DynamoDB + S3 (via `admin-api`), AWS Cognito |

This is a **4-tier architecture** client → SSR server → BFF → data stores.

### 4.4 Web Server Design

TanStack Start uses **Vinxi** as its build/server orchestrator:

- **Dev:** `vite dev --port 5001` with HMR.
- **Production build:** `vite build` (client + SSR bundles) + `esbuild` to bundle `server.js`.
- The custom `server.js` wrapper starts the H3 (or Nitro) HTTP server.
- The app is mounted at `base: '/admin/'` — all client assets are under `/admin/_next/` equivalent.
- A **dev-time proxy** (`/admin/api` → `http://localhost:3000`) forwards auth API calls to the site.

### 4.5 API Layer (BFF Pattern)

The server layer in `src/server/` contains 12 modules, each a collection of `createServerFn` calls:

| Module | Operations |
|---|---|
| `articles.ts` | CRUD articles, publish/unpublish, content save |
| `auth.ts` | Session read, login URL, logout, OAuth callback |
| `auth-guard.ts` | `requireAuth()` — fast-path JWT guard |
| `applications.ts` | Job application CRUD |
| `comments.ts` | Comment listing and moderation |
| `draft-publish.ts` | Trigger Bedrock pipeline |
| `finops.ts` | AWS cost data |
| `pipelines.ts` | GitHub Actions CI/CD status |
| `resumes.ts` | Resume CRUD |
| `upload.ts` | S3 file uploads |
| `patches.ts` | Server patching utilities |
| `security-headers.ts` | Security headers middleware |

All data operations **delegate to `admin-api`** via authenticated `fetch()` requests:

```
createServerFn → requireAuth() → apiFetch('/api/admin/...') → admin-api pod → DynamoDB/S3
```

The raw Cognito JWT from the `__session` cookie is forwarded as `Authorization: Bearer <token>`
so `admin-api` can re-verify it independently.

### 4.6 Authentication (Cognito OAuth PKCE)

The admin is fully protected via **AWS Cognito + OAuth 2.0 PKCE**:

1. `getLoginUrlFn()` generates a PKCE code verifier + challenge, stores them in `httpOnly` cookies,
   and returns the Cognito `/oauth2/authorize` URL.
2. Cognito redirects to `/admin/auth/callback` with an auth code.
3. `handleAuthCallbackFn()` validates CSRF state, exchanges the code via PKCE, and stores the
   `id_token` as a `__session` `httpOnly` secure cookie (24h TTL).
4. `requireAuth()` (in `auth-guard.ts`) runs at the top of every server function — it verifies
   the JWT against the Cognito JWKS endpoint and throws if invalid.

Security properties:
- No client-side token exposure (JWT in `httpOnly` cookie).
- CSRF protection via `oauth_state` cookie comparison.
- Short-lived PKCE cookies (15 min).

### 4.7 Styling

Same Tailwind CSS v4 stack as `apps/site`:
- `@tailwindcss/vite` Vite plugin (not PostCSS).
- Source: `src/styles.css` importing from `packages/shared`.
- Disabled during SSR build to prevent hash mismatch (explicitly handled in `vite.config.ts`
  with `!isSsrBuild && tailwindcss()`).
- Uses `@heroicons/react` and `lucide-react` for icons.

### 4.8 TypeScript Usage

- `tsconfig.json`: `strict: true`, `moduleResolution: bundler`, ESM-first.
- Zod v3 for validation (`zod: ^3.23.8`).
- TanStack Form with Zod adapter for type-safe forms.
- `@tanstack/react-form` for form state management.

### 4.9 Testing Suite

`apps/start-admin` uses **Vitest** (`vitest: ^3.0.5`) — appropriate given the Vite build pipeline:

| Test File | Coverage |
|---|---|
| `__tests__/server/auth.test.ts` | JWT verification, login URL generation, PKCE flow, logout |
| `__tests__/server/articles.test.ts` | Article CRUD server functions, auth guard, error handling |
| `__tests__/server/applications.test.ts` | Application CRUD server functions |

All tests mock `@tanstack/react-start/server` (cookie functions) and `fetch` to avoid network calls.

### 4.10 Observability

- **Grafana Faro RUM** — same `@grafana/faro-web-sdk` stack as `apps/site`.
- **No Prometheus metrics endpoint** — the admin is internal; its resource usage is covered by
  the K8s node-level metrics from the monitoring stack.
- No OTel distributed tracing configured (server functions do not currently emit spans).

> [!NOTE]
> Adding OTel traces to server functions would improve visibility into admin-api call latency
> and error rates from the admin UI layer.

### 4.11 Security Posture

- Full **CSP** implemented via `securityHeadersMiddleware` on the `getUserSessionFn` (runs on
  every route load):
  - `default-src 'self'`, `script-src 'self' 'unsafe-inline' 'unsafe-eval'` (Vite requirement).
  - `connect-src` scoped to `*.nelsonlamounier.com`, `*.amazonaws.com`, `*.amazoncognito.com`.
  - `frame-ancestors 'none'`.
- Standard security headers: HSTS, X-Frame-Options DENY, X-Content-Type-Options, Referrer-Policy.
- All routes enforce `requireAuth()` — no accidental public exposure.
- Non-root Docker user (`startadmin:nodejs`, UID 1001).
- JWT stored in `httpOnly` cookie — not `localStorage`.

### 4.12 Containerisation

`apps/start-admin/Dockerfile` — also 4-stage:

1. **base** — AL2023 + Node.js 22.
2. **deps** — Full yarn workspace install.
3. **builder** — `yarn workspace start-admin build` (Vite + esbuild SSR bundle).
4. **runner** — Copies `dist/` + `node_modules/` + `server.js`, runs as non-root.

Port: `5001`, health check hits `GET /admin/` (status < 500).

---

## 5. Comparative Analysis: site vs start-admin

| Dimension | apps/site | apps/start-admin |
|---|---|---|
| **Framework** | Next.js 15 (App Router) | TanStack Start (Vinxi/Vite) |
| **Router** | Next.js file-based (App Router) | TanStack Router (type-safe, file-based) |
| **Build tool** | Webpack (via Next.js) + SWC | Vite + Vinxi |
| **Test runner** | Jest | Vitest |
| **API style** | Next.js Route Handlers (`route.ts`) | TanStack `createServerFn` (RPC-style) |
| **Auth** | None (public) | AWS Cognito PKCE + `httpOnly` cookies |
| **Data access** | Direct AWS SDK v3 (DynamoDB, S3) | Via `admin-api` BFF (HTTP) |
| **OTel traces** | ✅ Full OTel SDK (OTLP/gRPC → Tempo) | ❌ Not configured |
| **Prometheus metrics** | ✅ `/api/metrics` endpoint | ❌ Not configured |
| **RUM (Faro)** | ✅ Client-side telemetry | ✅ Client-side telemetry |
| **CSP header** | ❌ Missing | ✅ Full CSP via middleware |
| **MDX support** | ✅ `@next/mdx` + `next-mdx-remote` | ✅ `@mdx-js/mdx` (editor) |
| **Tailwind** | v4 (PostCSS plugin) | v4 (Vite plugin) |
| **Port** | 3000 | 5001 |
| **Docker base** | Amazon Linux 2023 | Amazon Linux 2023 |
| **Output mode** | `standalone` (Next.js) | Vite SSR (`dist/`) |
| **Health check** | `GET /api/health` | `GET /admin/` |
| **SSR** | ✅ (React Server Components + SSR) | ✅ (Vinxi SSR) |
| **State management** | `zustand` + `@tanstack/react-query` | `@tanstack/react-query` |
| **Forms** | Uncontrolled / custom | `@tanstack/react-form` + Zod |

---

## 6. Supporting Infrastructure

While not part of the frontend apps themselves, these components complete the system picture:

| Component | Technology | Role |
|---|---|---|
| **admin-api** | Express (separate pod) | Authenticated BFF — CRUD to DynamoDB/S3 |
| **Bedrock Agent** | AWS Bedrock + API Gateway + Lambda | AI chat (site) + publish pipeline (admin) |
| **DynamoDB** | AWS DynamoDB (single-table) | Article metadata, resume data |
| **S3** | AWS S3 | MDX article content, uploaded assets |
| **CloudFront** | AWS CloudFront + WAF | CDN, edge caching, WAF rate limiting |
| **NLB** | AWS NLB | K8s cluster ingress |
| **Traefik** | K8s IngressController | Internal routing |
| **ArgoCD** | GitOps | Continuous deployment |
| **Prometheus** | K8s monitoring | Metric collection |
| **Grafana** | K8s monitoring | Dashboards, alerting |
| **Loki** | K8s monitoring | Log aggregation |
| **Tempo** | K8s monitoring | Distributed trace storage |
| **Faro** | Grafana cloud RUM | Browser-side monitoring |
| **Alloy** | Grafana Alloy (sidecar) | OTLP → Tempo forwarding |
| **AWS Cognito** | Managed IdP | Admin auth (PKCE) |
| **SSM Parameter Store** | AWS SSM | Secrets (Bearer tokens, Bedrock keys) |

---

## 7. Best Practices Assessment

### ✅ Positive Findings

| Practice | Status |
|---|---|
| TypeScript strict mode | ✅ Both apps |
| No `any` types in reviewed code | ✅ |
| JSDoc on all public server functions | ✅ |
| Multi-stage Docker builds | ✅ |
| Non-root container user | ✅ |
| Security headers on every response | ✅ |
| Health checks defined | ✅ |
| Zod for runtime validation | ✅ Both apps |
| SSM for secrets (no hardcoded keys) | ✅ |
| Bearer token caching with backoff | ✅ Metrics endpoint |
| PKCE OAuth (no implicit flow) | ✅ |
| `httpOnly` cookies (no localStorage JWT) | ✅ |
| Graceful shutdown (SIGTERM) | ✅ Next.js OTel |
| Yarn 4 lockfile (`--immutable` in Docker) | ✅ |
| Shared packages (`@repo/shared`) | ✅ |
| AL2023 base image (K8s OS parity) | ✅ |
| ArgoCD GitOps | ✅ |
| Prometheus + Grafana + Tempo + Loki | ✅ Full observability stack |

### ⚠️ Concerns / Gaps

| Concern | Severity | Details |
|---|---|---|
| No CSP on `apps/site` | Medium | Unlike admin, site responses lack a `Content-Security-Policy` header |
| No OTel on `apps/start-admin` | Low | Server function spans would help debug LCP and API latency |
| Prometheus metrics on `apps/site` use in-process token cache | Low | On pod restart, the cache is cold — first scrape may fail auth if SSM is slow |
| Rate limiter coverage | Low | Only `articles` API has a rate limiter; `chat` endpoint has no built-in rate limiting beyond API Gateway |
| No Redis/Elasticache | Low | Not needed at portfolio scale, but worth noting if traffic grows |
| `unsafe-inline` / `unsafe-eval` in admin CSP | Low | Required by Vite HMR in production is unusual; review if needed post-build |
| ECS resource detector in K8s | Low | `awsEcsDetector` runs but detects nothing meaningful on K8s — use `@opentelemetry/resource-detector-container` instead |

---

## 8. Gaps & Recommendations

1. **Add CSP to `apps/site` middleware** — A nonce-based or hash-based `Content-Security-Policy`
   header would close the most significant security gap.

2. **Replace `awsEcsDetector` with container detector** — The site runs on K8s, not ECS.
   Use `@opentelemetry/resource-detector-container` for accurate container metadata.

3. **Add OTel spans to start-admin server functions** — Wrap `apiFetch` calls in
   `tracer.startActiveSpan()` to generate admin-api latency traces in Tempo.

4. **Rate-limit the `/api/chat` endpoint** — The Bedrock Agent API Gateway has rate limits,
   but the Next.js proxy route has no local rate limiter. Add the existing `rate-limiter` utility.

5. **Consider a dedicated `revalidate` webhook secret** — The `/api/revalidate` endpoint
   should validate a token before purging ISR cache, else it's an unauthenticated DoS vector.
