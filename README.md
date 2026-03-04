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
| Workloads child app (prod) | `environments/prod/workloads` |
| Platform (dev) | `platform/envs/dev` |
| Platform (prod) | `platform/envs/prod` |
| Homelab API (dev) | `apps/homelab-api/envs/dev` |
| Homelab API (prod) | `apps/homelab-api/envs/prod` |
| Homelab Web (dev) | `apps/homelab-web/envs/dev` |
| Homelab Web (prod) | `apps/homelab-web/envs/prod` |

## Bootstrapping sequence

1. Apply `bootstrap/project-homelab.yaml`.
2. Apply one root app:
   - `bootstrap/root-app-dev.yaml`, or
   - `bootstrap/root-app-prod.yaml`.

## Argo CD project boundaries

`bootstrap/project-homelab.yaml` defines four scoped `AppProject` objects:

- `homelab-bootstrap`: may deploy only to `argocd` namespace.
- `homelab-platform`: may deploy only to `platform` namespace.
- `homelab-api`: may deploy only to `homelab-api` namespace.
- `homelab-web`: may deploy only to `homelab-web` namespace.

All projects allow only this repo URL as a source:

- `https://github.com/wlodzimierrr/homelab-workloads.git`

## RBAC audit guardrails

- RBAC audit report: `audit/rbac-audit-2026-03-04.md`
- Guardrail check script: `scripts/check-rbac-guardrails.sh`

Run locally:

```bash
./scripts/check-rbac-guardrails.sh
```

## Notes

- `repoURL` in bootstrap and environment Applications is pinned to this repo URL; update all manifests consistently if you fork or rename it.
- Environment folders use Kustomize overlays for clear, explicit promotion boundaries.

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

## Promotion Path (dev -> prod)

1. Validate changes in `apps/homelab-api/envs/dev`.
2. Promote by PR: update prod overlay (typically image tag in `apps/homelab-api/envs/prod/patch-deployment.yaml`).
3. Merge after checks; Argo CD reconciles `apps/homelab-api/envs/prod`.
4. Roll back by reverting the promotion commit.

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
- `migration-job.yaml` (Argo CD Sync hook) that waits for DB readiness and runs `alembic upgrade head` with retry.
- DB-specific network policies allowing only labeled DB clients to reach Postgres on `5432`.

### Postgres credentials bootstrap (no plaintext secrets in Git)

`homelab-api` expects a Secret named `homelab-api-postgres` in namespace `homelab-api`.
This repo intentionally does not store the Secret manifest with credentials.

Bootstrap/create secret:

```bash
cp apps/homelab-api/base/postgres-secret.env.example /tmp/homelab-api-postgres.env
# Edit /tmp/homelab-api-postgres.env and set a strong POSTGRES_PASSWORD.
kubectl -n homelab-api create secret generic homelab-api-postgres \
  --from-env-file=/tmp/homelab-api-postgres.env \
  --dry-run=client -o yaml | kubectl apply -f -
```

Rotate password:

```bash
kubectl -n homelab-api create secret generic homelab-api-postgres \
  --from-env-file=/tmp/homelab-api-postgres.env \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl -n homelab-api rollout restart deployment/homelab-api
kubectl -n argocd annotate app homelab-api-dev argocd.argoproj.io/refresh=hard --overwrite
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

Frontend proxies `/api/*` to `homelab-api.homelab-api.svc.cluster.local`.

## Portal ingress auth gate (T3.2.2)

Base manifests still include basic-auth middleware for fallback, while the dev overlay enables centralized SSO through oauth2-proxy + Traefik ForwardAuth.

Dev overlay resources:

- `apps/homelab-web/envs/dev/oauth2-proxy.yaml`
- `apps/homelab-web/envs/dev/middleware-oauth2.yaml`
- `apps/homelab-web/envs/dev/networkpolicy-allow-ingress-oauth2-proxy.yaml`
- `apps/homelab-web/envs/dev/networkpolicy-allow-egress-oauth2-proxy.yaml`
- ingress patches in `apps/homelab-web/envs/dev/patch-ingress.yaml` and `patch-ingress-api.yaml`

### oauth2-proxy bootstrap (secret in Git is placeholder only)

Edit placeholders in `apps/homelab-web/envs/dev/oauth2-proxy.yaml` and apply:

```bash
kubectl apply -k apps/homelab-web/envs/dev
```

This config protects both UI and `/api/*` with:

- `oauth2-errors` middleware: converts auth `401/403` to oauth2 sign-in flow.
- `oauth2-forward-auth` middleware: validates session and forwards user/group claims.

### Emergency break-glass path

Use `docs/runbooks/sso-break-glass.md` for emergency bypass and restoration commands.

Because this repo is GitOps-managed, commit/revert any break-glass change so Argo CD state remains consistent.

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
