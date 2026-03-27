#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp_root="$(mktemp -d)"
trap 'rm -rf "$tmp_root"' EXIT
smoke_home="$tmp_root/home"
mkdir -p "$smoke_home"

gitops_root="$tmp_root/workloads"
repo_output_dir="$tmp_root/scaffold-gen-test-repo"

cp -R "$repo_root" "$gitops_root"
rm -rf "$gitops_root/.git"

python3 "$repo_root/scripts/scaffold-service.py" \
  --name scaffold-gen-test \
  --description "Smoke-test scaffolded FastAPI service" \
  --image-repo ghcr.io/example/scaffold-gen-test \
  --repo-url https://github.com/example/scaffold-gen-test \
  --owner-email ops@example.com \
  --template python-fastapi \
  --prod-host scaffold-gen-test.example.com \
  --gitops-root "$gitops_root" \
  --repo-output-dir "$repo_output_dir" \
  --image-pull-secret ""

required_paths=(
  "$repo_output_dir/.github/workflows/build-scaffold-gen-test.yml"
  "$repo_output_dir/app/main.py"
  "$gitops_root/apps/scaffold-gen-test/base/kustomization.yaml"
  "$gitops_root/apps/scaffold-gen-test/base/servicemonitor.yaml"
  "$gitops_root/apps/scaffold-gen-test/envs/dev/kustomization.yaml"
  "$gitops_root/apps/scaffold-gen-test/envs/prod/kustomization.yaml"
  "$gitops_root/environments/dev/workloads/scaffold-gen-test-app.yaml"
  "$gitops_root/environments/prod/workloads/scaffold-gen-test-app.yaml"
  "$gitops_root/services.yaml"
)

for path in "${required_paths[@]}"; do
  if [[ ! -f "$path" ]]; then
    echo "missing generated file: $path" >&2
    exit 1
  fi
done

grep -q "service_id: scaffold-gen-test" "$gitops_root/services.yaml"
grep -q "repo_url: 'https://github.com/example/scaffold-gen-test'" "$gitops_root/services.yaml"
grep -q "mode: app-native" "$gitops_root/services.yaml"
grep -q "public_host: 'scaffold-gen-test.example.com'" "$gitops_root/services.yaml"
grep -q "path: /metrics" "$gitops_root/apps/scaffold-gen-test/base/servicemonitor.yaml"
grep -q "image: ghcr.io/example/scaffold-gen-test:latest" "$gitops_root/apps/scaffold-gen-test/base/deployment.yaml"
grep -q "imagePullPolicy: Always" "$gitops_root/apps/scaffold-gen-test/base/deployment.yaml"
grep -q "image: ghcr.io/example/scaffold-gen-test:latest" "$gitops_root/apps/scaffold-gen-test/envs/dev/patch-deployment.yaml"
grep -q "imagePullPolicy: Always" "$gitops_root/apps/scaffold-gen-test/envs/dev/patch-deployment.yaml"
grep -q "ghcr.io/example/scaffold-gen-test:latest" "$repo_output_dir/.github/workflows/build-scaffold-gen-test.yml"
grep -q "ghcr.io/example/scaffold-gen-test:sha-\${{ github.sha }}" "$repo_output_dir/.github/workflows/build-scaffold-gen-test.yml"

CI=true HOME="$smoke_home" "$gitops_root/scripts/render-kustomize.sh" "$gitops_root/apps/scaffold-gen-test/envs/dev" >/dev/null
CI=true HOME="$smoke_home" "$gitops_root/scripts/render-kustomize.sh" "$gitops_root/apps/scaffold-gen-test/envs/prod" >/dev/null
CI=true HOME="$smoke_home" "$gitops_root/scripts/render-kustomize.sh" "$gitops_root/environments/dev" >/dev/null
CI=true HOME="$smoke_home" "$gitops_root/scripts/render-kustomize.sh" "$gitops_root/environments/prod" >/dev/null

CI=true HOME="$smoke_home" "$gitops_root/scripts/check-environment-contract.sh" >/dev/null
"$gitops_root/scripts/check-service-identity-contract.sh" >/dev/null
"$gitops_root/scripts/check-rbac-guardrails.sh" >/dev/null
"$gitops_root/scripts/check-secrets-guardrails.sh" >/dev/null
python3 "$gitops_root/scripts/validate-services-catalog.py" --catalog "$gitops_root/services.yaml" >/dev/null

# Test database addon feature with PostgreSQL
echo "Testing database addon (PostgreSQL)..."
repo_output_dir_pg="$tmp_root/scaffold-smoke-pg"
gitops_root_pg="$tmp_root/workloads-pg"
cp -R "$repo_root" "$gitops_root_pg"
rm -rf "$gitops_root_pg/.git"

python3 "$repo_root/scripts/scaffold-service.py" \
  --name scaffold-smoke-pg \
  --description "Smoke-test scaffolded FastAPI service with PostgreSQL" \
  --image-repo ghcr.io/example/scaffold-smoke-pg \
  --repo-url https://github.com/example/scaffold-smoke-pg \
  --owner-email ops@example.com \
  --template python-fastapi \
  --add-on database \
  --db-engine postgres \
  --gitops-root "$gitops_root_pg" \
  --repo-output-dir "$repo_output_dir_pg" \
  --image-pull-secret ""

pg_required_paths=(
  "$repo_output_dir_pg/.github/workflows/build-scaffold-smoke-pg.yml"
  "$gitops_root_pg/apps/scaffold-smoke-pg/base/kustomization.yaml"
  "$gitops_root_pg/apps/scaffold-smoke-pg/base/scaffold-smoke-pg-postgres-statefulset.yaml"
  "$gitops_root_pg/apps/scaffold-smoke-pg/base/scaffold-smoke-pg-postgres-service.yaml"
  "$gitops_root_pg/apps/scaffold-smoke-pg/base/networkpolicy-allow-postgres-egress.yaml"
  "$gitops_root_pg/apps/scaffold-smoke-pg/base/networkpolicy-allow-postgres-ingress.yaml"
  "$gitops_root_pg/apps/scaffold-smoke-pg/base/scaffold-smoke-pg-migrate-job.yaml"
)

for path in "${pg_required_paths[@]}"; do
  if [[ ! -f "$path" ]]; then
    echo "missing database addon file: $path" >&2
    exit 1
  fi
done

# Verify kustomization.yaml includes database resources
grep -q "scaffold-smoke-pg-postgres-statefulset.yaml" "$gitops_root_pg/apps/scaffold-smoke-pg/base/kustomization.yaml" || {
  echo "kustomization.yaml missing postgres-statefulset reference" >&2
  exit 1
}

# Verify kustomize can render the PostgreSQL variant
CI=true HOME="$smoke_home" "$gitops_root_pg/scripts/render-kustomize.sh" "$gitops_root_pg/apps/scaffold-smoke-pg/base" >/dev/null

# Test database addon feature with MySQL
echo "Testing database addon (MySQL)..."
repo_output_dir_mysql="$tmp_root/scaffold-smoke-mysql"
gitops_root_mysql="$tmp_root/workloads-mysql"
cp -R "$repo_root" "$gitops_root_mysql"
rm -rf "$gitops_root_mysql/.git"

python3 "$repo_root/scripts/scaffold-service.py" \
  --name scaffold-smoke-mysql \
  --description "Smoke-test scaffolded FastAPI service with MySQL" \
  --image-repo ghcr.io/example/scaffold-smoke-mysql \
  --repo-url https://github.com/example/scaffold-smoke-mysql \
  --owner-email ops@example.com \
  --template python-fastapi \
  --add-on database \
  --db-engine mysql \
  --gitops-root "$gitops_root_mysql" \
  --repo-output-dir "$repo_output_dir_mysql" \
  --image-pull-secret ""

mysql_required_paths=(
  "$gitops_root_mysql/apps/scaffold-smoke-mysql/base/kustomization.yaml"
  "$gitops_root_mysql/apps/scaffold-smoke-mysql/base/scaffold-smoke-mysql-mysql-statefulset.yaml"
  "$gitops_root_mysql/apps/scaffold-smoke-mysql/base/scaffold-smoke-mysql-mysql-service.yaml"
  "$gitops_root_mysql/apps/scaffold-smoke-mysql/base/networkpolicy-allow-mysql-egress.yaml"
  "$gitops_root_mysql/apps/scaffold-smoke-mysql/base/networkpolicy-allow-mysql-ingress.yaml"
)

for path in "${mysql_required_paths[@]}"; do
  if [[ ! -f "$path" ]]; then
    echo "missing database addon file: $path" >&2
    exit 1
  fi
done

# Verify kustomize can render the MySQL variant
CI=true HOME="$smoke_home" "$gitops_root_mysql/scripts/render-kustomize.sh" "$gitops_root_mysql/apps/scaffold-smoke-mysql/base" >/dev/null

echo "scaffold generator smoke test passed"
