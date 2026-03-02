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

## Notes

- `repoURL` is intentionally a placeholder in example Applications. Replace it with your dedicated repo URL.
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
- `migration-job.yaml` (Argo CD Sync hook) that runs `alembic upgrade head`.
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
