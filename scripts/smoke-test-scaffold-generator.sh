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
grep -q "mode: ingress-derived" "$gitops_root/services.yaml"
grep -q "public_host: 'scaffold-gen-test.example.com'" "$gitops_root/services.yaml"
if [[ -f "$gitops_root/apps/scaffold-gen-test/base/servicemonitor.yaml" ]]; then
  echo "python-fastapi template should not generate a ServiceMonitor" >&2
  exit 1
fi
grep -q "image: ghcr.io/example/scaffold-gen-test:latest" "$gitops_root/apps/scaffold-gen-test/base/deployment.yaml"
grep -q "imagePullPolicy: Always" "$gitops_root/apps/scaffold-gen-test/base/deployment.yaml"
grep -q "image: ghcr.io/example/scaffold-gen-test:latest" "$gitops_root/apps/scaffold-gen-test/envs/dev/patch-deployment.yaml"
grep -q "imagePullPolicy: Always" "$gitops_root/apps/scaffold-gen-test/envs/dev/patch-deployment.yaml"
grep -q "ghcr.io/example/scaffold-gen-test:latest" "$repo_output_dir/.github/workflows/build-scaffold-gen-test.yml"
grep -q "ghcr.io/example/scaffold-gen-test:sha-\${{ github.sha }}" "$repo_output_dir/.github/workflows/build-scaffold-gen-test.yml"
grep -q "peter-evans/create-pull-request@v7" "$repo_output_dir/.github/workflows/build-scaffold-gen-test.yml"
grep -q "Deploy scaffold-gen-test: \${{ env.TARGET_TAG }} to dev" "$repo_output_dir/.github/workflows/build-scaffold-gen-test.yml"
grep -q "PORTAL_DEPLOYMENT_API_URL" "$repo_output_dir/.github/workflows/build-scaffold-gen-test.yml"
grep -q "requestKey\": \"gitops-pr:\${PR_NUMBER}:\${SERVICE_ID}:dev:deploy\"" "$repo_output_dir/.github/workflows/build-scaffold-gen-test.yml"

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

# Test node-express template
echo "Testing node-express template..."
repo_output_dir_node="$tmp_root/scaffold-smoke-node-repo"
gitops_root_node="$tmp_root/workloads-node"
cp -R "$repo_root" "$gitops_root_node"
rm -rf "$gitops_root_node/.git"

python3 "$repo_root/scripts/scaffold-service.py" \
  --name scaffold-smoke-node \
  --description "Smoke-test scaffolded Express.js service" \
  --image-repo ghcr.io/example/scaffold-smoke-node \
  --repo-url https://github.com/example/scaffold-smoke-node \
  --owner-email ops@example.com \
  --template node-express \
  --prod-host scaffold-smoke-node.example.com \
  --gitops-root "$gitops_root_node" \
  --repo-output-dir "$repo_output_dir_node" \
  --image-pull-secret ""

node_required_paths=(
  "$repo_output_dir_node/.github/workflows/build-scaffold-smoke-node.yml"
  "$repo_output_dir_node/src/index.js"
  "$repo_output_dir_node/Dockerfile"
  "$repo_output_dir_node/package.json"
  "$gitops_root_node/apps/scaffold-smoke-node/base/kustomization.yaml"
  "$gitops_root_node/apps/scaffold-smoke-node/base/servicemonitor.yaml"
  "$gitops_root_node/apps/scaffold-smoke-node/envs/dev/kustomization.yaml"
  "$gitops_root_node/apps/scaffold-smoke-node/envs/prod/kustomization.yaml"
  "$gitops_root_node/environments/dev/workloads/scaffold-smoke-node-app.yaml"
  "$gitops_root_node/environments/prod/workloads/scaffold-smoke-node-app.yaml"
)

for path in "${node_required_paths[@]}"; do
  if [[ ! -f "$path" ]]; then
    echo "missing node-express generated file: $path" >&2
    exit 1
  fi
done

grep -q "service_id: scaffold-smoke-node" "$gitops_root_node/services.yaml"
grep -q "mode: app-native" "$gitops_root_node/services.yaml"
grep -q "path: /metrics" "$gitops_root_node/apps/scaffold-smoke-node/base/servicemonitor.yaml"
grep -q "setup-node" "$repo_output_dir_node/.github/workflows/build-scaffold-smoke-node.yml"
grep -q "peter-evans/create-pull-request@v7" "$repo_output_dir_node/.github/workflows/build-scaffold-smoke-node.yml"

CI=true HOME="$smoke_home" "$gitops_root_node/scripts/render-kustomize.sh" "$gitops_root_node/apps/scaffold-smoke-node/envs/dev" >/dev/null
CI=true HOME="$smoke_home" "$gitops_root_node/scripts/render-kustomize.sh" "$gitops_root_node/apps/scaffold-smoke-node/envs/prod" >/dev/null

# Test vue template
echo "Testing vue template..."
repo_output_dir_vue="$tmp_root/scaffold-smoke-vue-repo"
gitops_root_vue="$tmp_root/workloads-vue"
cp -R "$repo_root" "$gitops_root_vue"
rm -rf "$gitops_root_vue/.git"

python3 "$repo_root/scripts/scaffold-service.py"   --name scaffold-smoke-vue   --description "Smoke-test scaffolded Vue service"   --image-repo ghcr.io/example/scaffold-smoke-vue   --repo-url https://github.com/example/scaffold-smoke-vue   --owner-email ops@example.com   --template vue   --prod-host scaffold-smoke-vue.example.com   --gitops-root "$gitops_root_vue"   --repo-output-dir "$repo_output_dir_vue"   --image-pull-secret ""

vue_required_paths=(
  "$repo_output_dir_vue/.github/workflows/build-scaffold-smoke-vue.yml"
  "$repo_output_dir_vue/src/App.vue"
  "$repo_output_dir_vue/src/main.js"
  "$repo_output_dir_vue/Dockerfile"
  "$repo_output_dir_vue/package.json"
  "$gitops_root_vue/apps/scaffold-smoke-vue/base/kustomization.yaml"
  "$gitops_root_vue/apps/scaffold-smoke-vue/envs/dev/kustomization.yaml"
  "$gitops_root_vue/apps/scaffold-smoke-vue/envs/prod/kustomization.yaml"
  "$gitops_root_vue/environments/dev/workloads/scaffold-smoke-vue-app.yaml"
  "$gitops_root_vue/environments/prod/workloads/scaffold-smoke-vue-app.yaml"
)

for path in "${vue_required_paths[@]}"; do
  if [[ ! -f "$path" ]]; then
    echo "missing vue generated file: $path" >&2
    exit 1
  fi
done

grep -q "service_id: scaffold-smoke-vue" "$gitops_root_vue/services.yaml"
grep -q "mode: ingress-derived" "$gitops_root_vue/services.yaml"
grep -q "path: /" "$gitops_root_vue/apps/scaffold-smoke-vue/base/deployment.yaml"
if [[ -f "$gitops_root_vue/apps/scaffold-smoke-vue/base/servicemonitor.yaml" ]]; then
  echo "vue template should not generate a ServiceMonitor" >&2
  exit 1
fi
grep -q "FROM node:20-alpine AS build" "$repo_output_dir_vue/Dockerfile"
grep -q "FROM nginx:1.27-alpine" "$repo_output_dir_vue/Dockerfile"
grep -q "setup-node" "$repo_output_dir_vue/.github/workflows/build-scaffold-smoke-vue.yml"
grep -q "npm run build" "$repo_output_dir_vue/.github/workflows/build-scaffold-smoke-vue.yml"
grep -q "peter-evans/create-pull-request@v7" "$repo_output_dir_vue/.github/workflows/build-scaffold-smoke-vue.yml"

CI=true HOME="$smoke_home" "$gitops_root_vue/scripts/render-kustomize.sh" "$gitops_root_vue/apps/scaffold-smoke-vue/envs/dev" >/dev/null
CI=true HOME="$smoke_home" "$gitops_root_vue/scripts/render-kustomize.sh" "$gitops_root_vue/apps/scaffold-smoke-vue/envs/prod" >/dev/null

# Test nextjs template
echo "Testing nextjs template..."
repo_output_dir_nextjs="$tmp_root/scaffold-smoke-nextjs-repo"
gitops_root_nextjs="$tmp_root/workloads-nextjs"
cp -R "$repo_root" "$gitops_root_nextjs"
rm -rf "$gitops_root_nextjs/.git"

python3 "$repo_root/scripts/scaffold-service.py" \
  --name scaffold-smoke-nextjs \
  --description "Smoke-test scaffolded Next.js service" \
  --image-repo ghcr.io/example/scaffold-smoke-nextjs \
  --repo-url https://github.com/example/scaffold-smoke-nextjs \
  --owner-email ops@example.com \
  --template nextjs \
  --prod-host scaffold-smoke-nextjs.example.com \
  --gitops-root "$gitops_root_nextjs" \
  --repo-output-dir "$repo_output_dir_nextjs" \
  --image-pull-secret ""

nextjs_required_paths=(
  "$repo_output_dir_nextjs/.github/workflows/build-scaffold-smoke-nextjs.yml"
  "$repo_output_dir_nextjs/src/app/page.tsx"
  "$repo_output_dir_nextjs/src/app/layout.tsx"
  "$repo_output_dir_nextjs/next.config.js"
  "$repo_output_dir_nextjs/package.json"
  "$gitops_root_nextjs/apps/scaffold-smoke-nextjs/base/kustomization.yaml"
  "$gitops_root_nextjs/apps/scaffold-smoke-nextjs/envs/dev/kustomization.yaml"
  "$gitops_root_nextjs/apps/scaffold-smoke-nextjs/envs/prod/kustomization.yaml"
  "$gitops_root_nextjs/environments/dev/workloads/scaffold-smoke-nextjs-app.yaml"
  "$gitops_root_nextjs/environments/prod/workloads/scaffold-smoke-nextjs-app.yaml"
)

for path in "${nextjs_required_paths[@]}"; do
  if [[ ! -f "$path" ]]; then
    echo "missing nextjs generated file: $path" >&2
    exit 1
  fi
done

grep -q "service_id: scaffold-smoke-nextjs" "$gitops_root_nextjs/services.yaml"
grep -q "mode: ingress-derived" "$gitops_root_nextjs/services.yaml"
if [[ -f "$gitops_root_nextjs/apps/scaffold-smoke-nextjs/base/servicemonitor.yaml" ]]; then
  echo "nextjs template should not generate a ServiceMonitor" >&2
  exit 1
fi
grep -q "setup-node" "$repo_output_dir_nextjs/.github/workflows/build-scaffold-smoke-nextjs.yml"
grep -q "npm run build" "$repo_output_dir_nextjs/.github/workflows/build-scaffold-smoke-nextjs.yml"
grep -q "peter-evans/create-pull-request@v7" "$repo_output_dir_nextjs/.github/workflows/build-scaffold-smoke-nextjs.yml"

CI=true HOME="$smoke_home" "$gitops_root_nextjs/scripts/render-kustomize.sh" "$gitops_root_nextjs/apps/scaffold-smoke-nextjs/envs/dev" >/dev/null
CI=true HOME="$smoke_home" "$gitops_root_nextjs/scripts/render-kustomize.sh" "$gitops_root_nextjs/apps/scaffold-smoke-nextjs/envs/prod" >/dev/null

# Test wordpress template
echo "Testing wordpress template..."
repo_output_dir_wordpress="$tmp_root/scaffold-smoke-wordpress-repo"
gitops_root_wordpress="$tmp_root/workloads-wordpress"
cp -R "$repo_root" "$gitops_root_wordpress"
rm -rf "$gitops_root_wordpress/.git"

python3 "$repo_root/scripts/scaffold-service.py"   --name scaffold-smoke-wordpress   --description "Smoke-test scaffolded WordPress service"   --image-repo wordpress:latest   --repo-url https://github.com/example/scaffold-smoke-wordpress   --owner-email ops@example.com   --template wordpress   --prod-host scaffold-smoke-wordpress.example.com   --gitops-root "$gitops_root_wordpress"   --repo-output-dir "$repo_output_dir_wordpress"   --image-pull-secret ""

wordpress_required_paths=(
  "$gitops_root_wordpress/apps/scaffold-smoke-wordpress/base/kustomization.yaml"
  "$gitops_root_wordpress/apps/scaffold-smoke-wordpress/base/persistentvolumeclaim.yaml"
  "$gitops_root_wordpress/apps/scaffold-smoke-wordpress/base/mysql-service.yaml"
  "$gitops_root_wordpress/apps/scaffold-smoke-wordpress/base/mysql-statefulset.yaml"
  "$gitops_root_wordpress/apps/scaffold-smoke-wordpress/base/networkpolicy-allow-mysql-egress.yaml"
  "$gitops_root_wordpress/apps/scaffold-smoke-wordpress/base/networkpolicy-allow-mysql-ingress.yaml"
  "$gitops_root_wordpress/apps/scaffold-smoke-wordpress/envs/dev/kustomization.yaml"
  "$gitops_root_wordpress/apps/scaffold-smoke-wordpress/envs/dev/wordpress-db-secret-generator.yaml"
  "$gitops_root_wordpress/apps/scaffold-smoke-wordpress/envs/dev/wordpress-db-secret.enc.yaml"
  "$gitops_root_wordpress/apps/scaffold-smoke-wordpress/envs/prod/kustomization.yaml"
  "$gitops_root_wordpress/apps/scaffold-smoke-wordpress/envs/prod/wordpress-db-secret-generator.yaml"
  "$gitops_root_wordpress/apps/scaffold-smoke-wordpress/envs/prod/wordpress-db-secret.enc.yaml"
  "$gitops_root_wordpress/environments/dev/workloads/scaffold-smoke-wordpress-app.yaml"
  "$gitops_root_wordpress/environments/prod/workloads/scaffold-smoke-wordpress-app.yaml"
)

for path in "${wordpress_required_paths[@]}"; do
  if [[ ! -f "$path" ]]; then
    echo "missing wordpress generated file: $path" >&2
    exit 1
  fi
done

wordpress_gitops_file_count="$(find "$gitops_root_wordpress/apps/scaffold-smoke-wordpress" -type f | wc -l | tr -d ' ')"
if [[ "$wordpress_gitops_file_count" != "23" ]]; then
  echo "unexpected wordpress manifest file count: $wordpress_gitops_file_count" >&2
  exit 1
fi

if [[ -d "$repo_output_dir_wordpress" ]] && find "$repo_output_dir_wordpress" -type f | grep -q .; then
  echo "wordpress template should not generate an application repo scaffold" >&2
  exit 1
fi

if [[ -f "$gitops_root_wordpress/apps/scaffold-smoke-wordpress/base/servicemonitor.yaml" ]]; then
  echo "wordpress template should not generate a ServiceMonitor" >&2
  exit 1
fi

grep -q "service_id: scaffold-smoke-wordpress" "$gitops_root_wordpress/services.yaml"
grep -q "mode: ingress-derived" "$gitops_root_wordpress/services.yaml"
grep -q "path: /wp-login.php" "$gitops_root_wordpress/apps/scaffold-smoke-wordpress/base/deployment.yaml"
grep -q "WORDPRESS_DB_PASSWORD" "$gitops_root_wordpress/apps/scaffold-smoke-wordpress/envs/dev/wordpress-db-secret.enc.yaml"
grep -q "MYSQL_ROOT_PASSWORD" "$gitops_root_wordpress/apps/scaffold-smoke-wordpress/envs/dev/wordpress-db-secret.enc.yaml"
grep -q "sops:" "$gitops_root_wordpress/apps/scaffold-smoke-wordpress/envs/dev/wordpress-db-secret.enc.yaml"
if grep -q "age1xxx" "$gitops_root_wordpress/apps/scaffold-smoke-wordpress/envs/dev/wordpress-db-secret.enc.yaml"; then
  echo "wordpress scaffold should emit a real encrypted secret, not the placeholder recipient" >&2
  exit 1
fi

CI=true HOME="$smoke_home" "$gitops_root_wordpress/scripts/render-kustomize.sh" "$gitops_root_wordpress/apps/scaffold-smoke-wordpress/envs/dev" >/dev/null
CI=true HOME="$smoke_home" "$gitops_root_wordpress/scripts/render-kustomize.sh" "$gitops_root_wordpress/apps/scaffold-smoke-wordpress/envs/prod" >/dev/null
CI=true HOME="$smoke_home" "$gitops_root_wordpress/scripts/render-kustomize.sh" "$gitops_root_wordpress/environments/dev" >/dev/null
CI=true HOME="$smoke_home" "$gitops_root_wordpress/scripts/render-kustomize.sh" "$gitops_root_wordpress/environments/prod" >/dev/null
"$gitops_root_wordpress/scripts/check-secrets-guardrails.sh" >/dev/null

echo "scaffold generator smoke test passed"
