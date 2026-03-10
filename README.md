# Homelab GitOps Workloads Repository Skeleton

This directory is a starter layout for a dedicated manifests repository.

## Layout

- `bootstrap/`: Argo CD bootstrap objects (AppProject, root apps).
- `platform/`: shared platform components managed by GitOps.
- `apps/`: workload application manifests.
- `environments/`: environment-level Argo CD app sets (dev/prod).

## Argo CD target paths

Use these exact paths in Argo CD `spec.source.path`.

| Purpose | Path |
|---|---|
| Root app (dev) | `environments/dev` |
| Root app (prod) | `environments/prod` |
| Workloads child app (dev) | `environments/dev/workloads` |
| Workloads child app (prod) | `environments/prod/workloads` (intentionally empty in single-cluster mode) |
| Platform (dev) | `platform/envs/dev` |
| Platform (prod) | `platform/envs/prod` |
| Homelab API (dev) | `apps/homelab-api/envs/dev` |
| Homelab API (prod) | `apps/homelab-api/envs/prod` |
| Homelab Web (dev) | `apps/homelab-web/envs/dev` |
| Homelab Web (prod) | `apps/homelab-web/envs/prod` |
| Monitoring app (dev) | `environments/dev/workloads/monitoring-app.yaml` |
| Loki app (dev) | `environments/dev/workloads/loki-app.yaml` |
| Promtail app (dev) | `environments/dev/workloads/promtail-app.yaml` |

## Bootstrapping sequence

1. Apply `bootstrap/project-homelab.yaml`.
2. Apply one root app:
   - `bootstrap/root-app-dev.yaml`, or
   - `bootstrap/root-app-prod.yaml`.

## Argo CD project boundaries

`bootstrap/project-homelab.yaml` defines five scoped `AppProject` objects:

- `homelab-bootstrap`: may deploy only to `argocd` namespace.
- `homelab-platform`: may deploy only to `platform` namespace.
- `homelab-api`: may deploy only to `homelab-api` namespace.
- `homelab-web`: may deploy only to `homelab-web` namespace.
- `homelab-monitoring`: may deploy to `monitoring` and required scrape service objects in `kube-system`.

Source repos allowed by project:

- `https://github.com/wlodzimierrr/homelab-workloads.git`
- `https://prometheus-community.github.io/helm-charts` (monitoring only)
- `https://grafana.github.io/helm-charts` (Loki/Promtail only)

## RBAC audit guardrails

- RBAC audit report: `audit/rbac-audit-2026-03-04.md`
- Guardrail check script: `scripts/check-rbac-guardrails.sh`
- Secret guardrail check script: `scripts/check-secrets-guardrails.sh`
- Rotation SLO check script: `scripts/verify-rotation-slo.sh`

Run locally:

```bash
./scripts/check-rbac-guardrails.sh
./scripts/check-secrets-guardrails.sh
./scripts/check-environment-contract.sh
./scripts/smoke-test-scaffold-generator.sh
./scripts/verify-rotation-slo.sh homelab-api homelab-api 300
```

## Environment contract

| Environment | Root app | Platform path | Workloads path | Current state |
|---|---|---|---|---|
| `dev` | `bootstrap/root-app-dev.yaml` | `platform/envs/dev` | `environments/dev/workloads` | Active on the current cluster |
| `prod` | `bootstrap/root-app-prod.yaml` | `platform/envs/prod` | `environments/prod/workloads` | Overlay intent exists; workloads path stays empty with `allowEmpty: true` in single-cluster safety mode |

## Notes

- `repoURL` in bootstrap and environment Applications is pinned to this repo URL; update all manifests consistently if you fork or rename it.
- Environment folders use Kustomize overlays for clear, explicit promotion boundaries.
- Single-cluster safety mode: `environments/prod/workloads/kustomization.yaml` is intentionally empty to prevent accidental recreation of `*-prod` apps in the same cluster/namespaces.
- `homelab-api-prod`, `homelab-web-prod`, and `monitoring-prod` should remain deleted from Argo CD unless you introduce separate namespaces/clusters for prod isolation.

## Layering Strategy

- Decision: use Kustomize base + overlays for dev/prod layering.
- Scope: default for platform and app manifests in this repo.
- Exception: when third-party Helm charts are required, keep Argo CD paths environment-scoped and preserve the same folder conventions.

## Example App: base + overlay

`apps/homelab-api` demonstrates the pattern:

- Base:
  - `apps/homelab-api/base/deployment.yaml`
  - `apps/homelab-api/base/service.yaml`
- Dev overlay:
  - `apps/homelab-api/envs/dev/kustomization.yaml`
  - `apps/homelab-api/envs/dev/patch-deployment.yaml`
- Prod overlay:
  - `apps/homelab-api/envs/prod/kustomization.yaml`
  - `apps/homelab-api/envs/prod/patch-deployment.yaml`

## Promotion Contract (dev -> prod)

- Dev image bumps are created by `apps/portal/.github/workflows/portal-images.yml` and may change only dev overlay image patch files.
- Prod promotion and rollback requests are created by `apps/portal/.github/workflows/gated-promotion.yml`.
- Normal prod promotions for `homelab-api` and `homelab-web` may change only:
  - `apps/homelab-api/envs/prod/patch-deployment.yaml`
  - `apps/homelab-api/envs/prod/patch-migration-job.yaml`
  - `apps/homelab-api/envs/prod/patch-catalog-sync-cronjob.yaml`
  - `apps/homelab-web/envs/prod/patch-deployment.yaml`
- Validate structural changes with `./scripts/check-environment-contract.sh`.
- Roll back by re-running the gated workflow with `action_mode=rollback` or by reverting the merged prod PR.

## Service scaffolding

Use the scaffold generator to create a service repo skeleton plus matching GitOps manifests:

```bash
./scripts/scaffold-service.sh \
  --name my-app \
  --description "Internal app" \
  --image-repo ghcr.io/wlodzimierrr/my-app \
  --repo-url https://github.com/wlodzimierrr/my-app \
  --owner platform \
  --owner-email you@example.com \
  --runbook-url https://github.com/wlodzimierrr/homelab/blob/main/docs/runbooks/my-app.md \
  --template python-fastapi \
  --repo-output-dir /tmp/my-app-repo
```

Supported templates:

- `python-fastapi`
- `static-nginx`

Useful overrides:

- `--container-port` / `--service-port`
- `--health-path` / `--readiness-path`
- `--image-pull-secret ''` for public images
- `--owner` / `--owner-email`
- `--runbook-url` (defaults to `--repo-url`)

What it generates:

- Service source repo skeleton with Dockerfile, README, and CI workflow.
- `apps/<service>/base` plus `envs/dev` and `envs/prod` overlays.
- Dev and prod Argo `Application` manifests under `environments/*/workloads/`.
- A new service `AppProject` appended to `bootstrap/project-homelab.yaml`.
- A Git-backed service catalog entry appended to `services.yaml`.

Current safety-mode behavior:

- The dev app manifest is added to `environments/dev/workloads/kustomization.yaml`.
- The prod app manifest is generated but not enabled in `environments/prod/workloads/kustomization.yaml` while single-cluster safety mode is active.

Generator smoke test:

```bash
./scripts/smoke-test-scaffold-generator.sh
```

## Service catalog metadata

`services.yaml` is the Git-backed source for lightweight portal catalog metadata.

Each entry should define:

- `service_id`
- `owner`
- `repo_url`
- `runbook_url`

The portal joins this file with project and service registry data so the Services page can show ownership links without relying on a spreadsheet.

## Network policy baseline

`apps/homelab-api/base` and `apps/homelab-web/base` include a baseline policy set:

- `default-deny` for ingress and egress at namespace scope.
- explicit DNS egress to CoreDNS in `kube-system`.
- explicit app traffic allows:
  - Traefik (`kube-system`) ingress to app pods.
  - `homelab-web` egress to `homelab-api`.

## Homelab API data layer

`apps/homelab-api/base` now includes:

- `postgres-statefulset.yaml` with a PVC (`volumeClaimTemplates`) for durable Postgres storage.
- `postgres-service.yaml` for in-cluster DB connectivity.
- `migration-job.yaml` (Argo CD Sync hook) that waits for DB readiness, skips rollback replays when the database revision is newer than the current image knows about, and otherwise runs `alembic upgrade head` with retry.
- DB-specific network policies allowing only labeled DB clients to reach Postgres on `5432`.

### Postgres credentials (SOPS standard)

`homelab-api` expects a Secret named `homelab-api-postgres` in namespace `homelab-api`.

Repository standard:

1. Store secret manifests only as SOPS-encrypted files (`*.enc.yaml`).
2. Never commit plaintext `kind: Secret` manifests.
3. Validate with `./scripts/check-secrets-guardrails.sh`.

Implementation runbook:

- `docs/runbooks/sops-secrets.md`

Bootstrap helper:

```bash
./scripts/bootstrap-sops-postgres-secret.sh dev
./scripts/bootstrap-sops-postgres-secret.sh prod
./scripts/render-kustomize.sh apps/homelab-api/envs/dev >/dev/null
```

### Private GHCR image pulls

If `homelab-api` images are private in GHCR, create a pull secret in the `homelab-api` namespace and reference it as `ghcr-pull-secret`:

```bash
kubectl -n homelab-api create secret docker-registry ghcr-pull-secret \
  --docker-server=ghcr.io \
  --docker-username=wlodzimierrr \
  --docker-password="$CR_PAT"
```

`apps/homelab-api/base/serviceaccount-backend.yaml` is configured to use this secret via `imagePullSecrets`.

## Ingress hosts

Current host routing:

- `portal.dev.homelab.local` -> `homelab-web`
- `portal.homelab.local` -> `homelab-web`
- `api.dev.homelab.local` -> `homelab-api`
- `api.homelab.local` -> `homelab-api`
- `monitoring.homelab.local` -> `kube-prometheus-stack-grafana` (namespace `monitoring`)

Frontend proxies `/api/*` to `homelab-api.homelab-api.svc.cluster.local`.

## Portal ingress auth gate (T3.2.2)

Base manifests still include basic-auth middleware for fallback, while the dev overlay enables centralized SSO through oauth2-proxy + Traefik ForwardAuth.

Dev overlay resources:

- `apps/homelab-web/envs/dev/oauth2-proxy.yaml`
- `apps/homelab-web/envs/dev/middleware-oauth2.yaml`
- `apps/homelab-web/envs/dev/networkpolicy-allow-ingress-oauth2-proxy.yaml`
- `apps/homelab-web/envs/dev/networkpolicy-allow-egress-oauth2-proxy.yaml`
- ingress patches in `apps/homelab-web/envs/dev/patch-ingress.yaml` and `patch-ingress-api.yaml`

### oauth2-proxy bootstrap (SOPS + KSOPS)

Create/update the encrypted secret and render the dev overlay locally:

```bash
./scripts/bootstrap-sops-oauth2-proxy-secret.sh dev
./scripts/render-kustomize.sh apps/homelab-web/envs/dev >/dev/null
```

This config protects both UI and `/api/*` with:

- `oauth2-errors` middleware: converts auth `401/403` to oauth2 sign-in flow.
- `oauth2-forward-auth` middleware: validates session and forwards user/group claims.

Commit `apps/homelab-web/envs/dev/oauth2-proxy-secret.enc.yaml` and let Argo CD reconcile it through KSOPS.

### Emergency break-glass path

Use `docs/runbooks/sso-break-glass.md` for emergency bypass and restoration commands.

Because this repo is GitOps-managed, commit/revert any break-glass change so Argo CD state remains consistent.

## Quarterly secret rotation

Use `docs/runbooks/secret-rotation-quarterly.md` for the quarterly procedure covering:

1. SOPS-encrypted DB credential rotation
2. oauth2-proxy credential/cookie rotation
3. GHCR pull secret rotation
4. Rollout SLO verification (`<= 300s`) via `scripts/verify-rotation-slo.sh`

### Private GHCR image pulls for web namespace

`homelab-web` uses ServiceAccount `homelab-web` with pull secret `ghcr-pull-secret`.
Create it in `homelab-web` namespace too:

```bash
kubectl -n homelab-web create secret docker-registry ghcr-pull-secret \
  --docker-server=ghcr.io \
  --docker-username=wlodzimierrr \
  --docker-password="$CR_PAT"
```

## GHCR auth and retention policy (T2.3.1)

### Standard auth pattern for cluster pulls

- Registry: `ghcr.io`
- Secret name: `ghcr-pull-secret`
- Namespaces requiring the secret: `homelab-api`, `homelab-web`
- ServiceAccounts consuming it:
  - `apps/homelab-api/base/serviceaccount-backend.yaml`
  - `apps/homelab-web/base/serviceaccount-web.yaml`

Recommended token scope for pull-only credentials:

- Classic PAT: `read:packages` only
- Or fine-grained PAT with package read access limited to:
  - `ghcr.io/wlodzimierrr/homelab-api`
  - `ghcr.io/wlodzimierrr/homelab-web`

### Pull secret rotation procedure

Create a new read-only token in GitHub, then rotate secrets in both namespaces:

```bash
export GHCR_USER="wlodzimierrr"
export GHCR_TOKEN="<new-read-only-token>"

for ns in homelab-api homelab-web; do
  kubectl -n "$ns" create secret docker-registry ghcr-pull-secret \
    --docker-server=ghcr.io \
    --docker-username="$GHCR_USER" \
    --docker-password="$GHCR_TOKEN" \
    --dry-run=client -o yaml | kubectl apply -f -
done
```

Validation:

```bash
kubectl -n homelab-api get secret ghcr-pull-secret
kubectl -n homelab-web get secret ghcr-pull-secret
kubectl -n homelab-api rollout restart deployment/homelab-api
kubectl -n homelab-web rollout restart deployment/homelab-web
kubectl -n homelab-api rollout status deployment/homelab-api
kubectl -n homelab-web rollout status deployment/homelab-web
```

Rotation cadence: every 90 days, and immediately after any credential exposure suspicion.

## Monitoring stack (T4.1.1)

`kube-prometheus-stack` is deployed as Argo CD applications:

- `environments/dev/workloads/monitoring-app.yaml`

Homelab resource profile:

- Alertmanager enabled so the portal can query live active alerts and incidents.
- Prometheus retention: `24h` and `retentionSize: 3GiB` on `5Gi` PVC.
- Grafana persistence enabled with `2Gi` PVC.
- Scope: single shared cluster monitoring stack for now (no separate `monitoring-prod` app) to avoid Argo CD shared-resource conflicts.
- Future: split monitoring per environment using distinct release names and namespaces when multi-cluster or strict env isolation is introduced.

Operational runbook:

- `docs/runbooks/monitoring-kube-prometheus-stack.md`
- `docs/runbooks/platform-health-dashboard.md`

## Centralized logging stack (T4.2.1)

Loki + Promtail are deployed as Argo CD applications:

- `environments/dev/workloads/loki-app.yaml`
- `environments/dev/workloads/promtail-app.yaml`

Homelab resource profile:

- Loki runs single-binary mode with `10Gi` PVC.
- Retention is enabled with `retention_period: 168h` (7 days).
- Promtail runs as a DaemonSet and ships pod logs to Loki.
- Log labels support filtering by `namespace`, `container`, and `app` in Grafana Explore.
- Grafana is preconfigured with a Loki datasource (`uid: loki`) in `environments/dev/workloads/monitoring-app.yaml`.

Operational runbook:

- `docs/runbooks/logging-loki-promtail.md`
- `docs/runbooks/log-to-triage-workflow.md`

### Registry retention policy

Packages covered:

- `ghcr.io/wlodzimierrr/homelab-api`
- `ghcr.io/wlodzimierrr/homelab-web`

Retention rules:

- Keep all semver/release tags (for example `0.3.1`, `0.2.0`) for rollback safety.
- Keep digest/provenance artifacts associated with retained tags.
- Keep only the most recent 60 `sha-<commit>` tags per image package.
- Prune `sha-*` tags older than 60 entries on a monthly schedule.

Operational note: apply retention via GHCR package settings or an org/repo cleanup workflow; never delete the currently deployed prod tag or the prior known-good rollback tag.
