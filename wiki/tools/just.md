---
title: Just (Task Runner)
type: tool
tags: [devops, just, task-runner, developer-experience, ci-cd]
sources: [raw/step-function-runtime-logging.md, raw/scripts_justfile_review.md]
created: 2026-04-13
updated: 2026-04-15
---

# Just (Task Runner)

[Just](https://github.com/casey/just) is the **stable CLI contract** for the [[k8s-bootstrap-pipeline]]. All workflows — local development, CDK deployments, diagnostics, and CI pipelines — are exposed as `just` recipes. When the underlying implementation changes, recipe names stay constant: GitHub Actions workflows never need updating.

## Why Just Over npm Scripts or Make

| Concern | npm scripts | Make | just |
|---|---|---|---|
| Multi-step recipes | `&&` chains | Native deps (file-based) | Native deps (command-based) |
| Comments | Not in JSON | Supported | Full comment support |
| Argument passing | `-- --flag` workaround | `$(VAR)` / shell conflicts | Clean variable interpolation |
| Cross-package | `--filter` / `--cwd` flags | Multiple Makefiles | Single `justfile` at monorepo root |
| Predictability | N/A | Re-runs based on file mtimes — wrong for infra | Always re-runs — predictable |
| Windows | Works | Requires WSL | Native cross-platform |

**Key insight**: In a CDK monorepo, `just` recipes run many times per day from multiple contexts (terminal, CI runner, VS Code task). Frictionless = `just diagnose`. Friction = `npx tsx scripts/local/control-plane-troubleshoot.ts --profile dev-account --region eu-west-1`.

## Recipe Groups

The `justfile` is organized into six groups matching the project's separation of concerns:

| Group | Maps to | Examples |
|---|---|---|
| `cdk` | `infra/` CDK code | `just synth`, `just deploy`, `just diff` |
| `ci` | GitHub Actions entry points | `just test-stacks`, `just ci-synth` |
| `test` | Unit + integration tests | `just test-integration`, `just verify-ssm` |
| `k8s` | `kubernetes-app/` ArgoCD/Helm | `just argocd-sync`, `just rollout-status` |
| `ops` | `scripts/local/` TypeScript diagnostics | `just diagnose`, `just fix-cert`, `just asg-audit` |
| `infra` | Raw AWS infrastructure inspection | `just ebs-audit`, `just cfn-troubleshoot` |

## CI/CD Integration Pattern

Every GitHub Actions workflow calls `just` recipes, never raw commands:

```yaml
# .github/workflows/_deploy-kubernetes.yml
- run: just deploy-kubernetes ${{ inputs.environment }}

# .github/workflows/ci.yml
- run: just test-stacks

# .github/workflows/_deploy-ssm-automation.yml
- run: just verify-ssm ${{ inputs.stack_name }}
```

**Why this matters**: If the underlying CDK command changes (e.g., `cdk deploy` → `cdk deploy --hotswap`), one line in the `justfile` changes. All 26 GitHub Actions workflows inherit the change automatically.

## Key Design Decisions

**AWS_PROFILE at recipe level** (not hardcoded in commands): recipes accept `profile='dev-account'` as a positional parameter with a default. Local developers with multiple AWS accounts avoid wrong-account deployments; CI passes `profile=ci` which maps to OIDC ambient credentials.

**`--require-approval never` on all deploy recipes**: CDK's interactive approval gate is incompatible with CI. The human approval gate is the GitHub PR review, not the CDK prompt. Post-deploy integration tests provide the automated safety net.

**Recipes as documentation**: every recipe has a comment explaining what, when, and what it requires. `just --list` becomes a self-describing operations manual — valuable after weeks of absence.

## Self-Other: Why just Matters for Solo Development

The project runs without an on-call team. `just --list` is the entire ops manual accessible from one command. When something breaks at 2 AM, the developer types `just diagnose`, not `npx tsx scripts/local/control-plane-troubleshoot.ts --profile ...`. The recipe abstraction is the difference between "I remember how to do this" and "I don't have to remember."

## Key Recipes

See [[k8s-bootstrap-commands]] for the full command reference.

### Deploy Script Workflows

| Recipe | Purpose |
|--------|---------|
| `just deploy-test <script>` | Run offline unit tests (< 5s) |
| `just deploy-sync <script>` | Upload deploy.py to S3 (file mode, ~10s) |
| `just deploy-sync <script> development full` | Upload entire chart directory |
| `just deploy-script <script>` | Trigger via SSM document + CloudWatch tail |
| `just ssm-shell` | Root interactive session on EC2 |

### Bootstrap Script Workflows

| Recipe | Purpose |
|--------|---------|
| `just boot-test-local` | Offline pytest for bootstrap scripts |
| `just bootstrap-pytest` | Full 75-test suite |
| `just bootstrap-sync` | Sync bootstrap scripts to S3 |
| `just bootstrap-pull $ID` | Pull updated scripts onto EC2 |
| `just bootstrap-dry-run $ID` | Dry-run on live instance |
| `just bootstrap-test $ID` | All-in-one: sync + pull + dry-run |
| `just bootstrap-run $ID` | Live run (ArgoCD-only Day-2) |

### Step Functions & Config

| Recipe | Purpose |
|--------|---------|
| `just config-run development` | Trigger SM-B (all 5 deploy scripts) |
| `just config-status` | Latest SM-B execution ARN + status |

### CDK

| Recipe | Purpose |
|--------|---------|
| `just deploy-stack <stack> kubernetes development` | Deploy single CDK stack |
| `just diff kubernetes development` | CDK diff before deploying |
| `just list kubernetes development` | List all stacks |

## Related Pages

- [[k8s-bootstrap-pipeline]] — project context
- [[operational-scripts]] — the TypeScript diagnostic scripts invoked by the `ops` and `infra` recipe groups
- [[ci-cd-pipeline-architecture]] — the CI/CD pipelines that call `just` recipes as their stable interface
- [[k8s-bootstrap-commands]] — full command reference
- [[shift-left-validation]] — the testing philosophy these recipes implement
