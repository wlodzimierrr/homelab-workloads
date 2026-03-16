#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

status=0
regex_tool=""

if command -v rg >/dev/null 2>&1; then
  regex_tool="rg"
else
  regex_tool="grep"
fi

pass() {
  echo "[env-contract] OK: $1"
}

fail() {
  echo "[env-contract] FAIL: $1" >&2
  status=1
}

require_file() {
  local file="$1"
  local description="$2"

  if [[ -f "$file" ]]; then
    pass "$description"
  else
    fail "$description (missing $file)"
  fi
}

require_regex() {
  local file="$1"
  local pattern="$2"
  local description="$3"

  case "$regex_tool" in
    rg)
      if rg -q "$pattern" "$file"; then
        pass "$description"
      else
        fail "$description (pattern '$pattern' not found in $file)"
      fi
      ;;
    grep)
      if grep -Eq -- "$pattern" "$file"; then
        pass "$description"
      else
        fail "$description (pattern '$pattern' not found in $file)"
      fi
      ;;
    *)
      fail "$description (no supported regex tool available)"
      ;;
  esac
}

render_overlay() {
  local overlay="$1"
  if "$repo_root/scripts/render-kustomize.sh" "$overlay" >/dev/null; then
    pass "rendered $overlay with plugin-aware kustomize"
  else
    fail "plugin-aware kustomize build failed for $overlay"
  fi
}

echo "[env-contract] checking bootstrap entrypoints..."
require_regex "bootstrap/root-app-dev.yaml" '^  name: homelab-root-dev$' "dev root application name is fixed"
require_regex "bootstrap/root-app-dev.yaml" '^    path: environments/dev$' "dev root application points to environments/dev"
require_regex "bootstrap/root-app-prod.yaml" '^  name: homelab-root-prod$' "prod root application name is fixed"
require_regex "bootstrap/root-app-prod.yaml" '^    path: environments/prod$' "prod root application points to environments/prod"

echo "[env-contract] checking environment app-of-apps structure..."
require_regex "environments/dev/kustomization.yaml" '^[[:space:]]*-[[:space:]]*platform-app.yaml$' "dev environment includes platform app"
require_regex "environments/dev/kustomization.yaml" '^[[:space:]]*-[[:space:]]*workloads-app.yaml$' "dev environment includes workloads app"
require_regex "environments/prod/kustomization.yaml" '^[[:space:]]*-[[:space:]]*platform-app.yaml$' "prod environment includes platform app"
require_regex "environments/prod/kustomization.yaml" '^[[:space:]]*-[[:space:]]*workloads-app.yaml$' "prod environment includes workloads app"
require_regex "environments/dev/workloads/homelab-api-app.yaml" '^    path: apps/homelab-api/envs/dev$' "dev API app points to dev overlay"
require_regex "environments/dev/workloads/homelab-web-app.yaml" '^    path: apps/homelab-web/envs/dev$' "dev web app points to dev overlay"
require_regex "environments/prod/workloads-app.yaml" 'allowEmpty:[[:space:]]*true' "prod workloads app stays allowEmpty in single-cluster safety mode"

# Prod workloads kustomization may only contain StatefulSet-based (database) services.
# HTTP services must go through the gated-promotion workflow instead.
mapfile -t prod_resources < <(grep -E '^\s*-\s+\S' environments/prod/workloads/kustomization.yaml | sed 's/^\s*-\s*//' || true)
if [[ "${#prod_resources[@]}" -eq 0 ]]; then
  pass "prod workloads kustomization is empty (single-cluster safety mode active)"
else
  for resource in "${prod_resources[@]}"; do
    service_name="${resource%-app.yaml}"
    if [[ -f "apps/${service_name}/base/statefulset.yaml" ]]; then
      pass "prod workloads kustomization entry ${resource} is a database service"
    else
      fail "prod workloads kustomization contains non-database service ${service_name} — HTTP services must use gated-promotion"
    fi
  done
fi

echo "[env-contract] checking overlay identity labels..."
for env_name in dev prod; do
  require_regex "apps/homelab-api/envs/${env_name}/kustomization.yaml" "homelab.env:[[:space:]]*${env_name}" "API overlay labels ${env_name} resources"
  require_regex "apps/homelab-web/envs/${env_name}/kustomization.yaml" "homelab.env:[[:space:]]*${env_name}" "web overlay labels ${env_name} resources"
  require_regex "platform/envs/${env_name}/kustomization.yaml" "homelab.env:[[:space:]]*${env_name}" "platform overlay labels ${env_name} resources"
done

echo "[env-contract] checking declarative host and image promotion files..."
require_regex "apps/homelab-api/base/ingress.yaml" 'host:[[:space:]]*api\.dev\.homelab\.local' "API base ingress is the dev host"
require_regex "apps/homelab-api/envs/prod/patch-ingress.yaml" 'host:[[:space:]]*api\.homelab\.local' "API prod ingress host is patched declaratively"
require_regex "apps/homelab-web/base/ingress.yaml" 'host:[[:space:]]*portal\.dev\.homelab\.local' "web base ingress is the dev host"
require_regex "apps/homelab-web/envs/prod/patch-ingress.yaml" 'host:[[:space:]]*portal\.homelab\.local' "web prod ingress host is patched declaratively"

promotion_files=(
  "apps/homelab-api/envs/dev/patch-deployment.yaml"
  "apps/homelab-api/envs/dev/patch-migration-job.yaml"
  "apps/homelab-api/envs/dev/patch-catalog-sync-cronjob.yaml"
  "apps/homelab-api/envs/prod/patch-deployment.yaml"
  "apps/homelab-api/envs/prod/patch-migration-job.yaml"
  "apps/homelab-api/envs/prod/patch-catalog-sync-cronjob.yaml"
  "apps/homelab-web/envs/dev/patch-deployment.yaml"
  "apps/homelab-web/envs/prod/patch-deployment.yaml"
)

for file in "${promotion_files[@]}"; do
  require_file "$file" "promotion patch file exists: $file"
done

echo "[env-contract] rendering overlays..."
for overlay in \
  "platform/envs/dev" \
  "platform/envs/prod" \
  "apps/homelab-api/envs/dev" \
  "apps/homelab-api/envs/prod" \
  "apps/homelab-web/envs/dev" \
  "apps/homelab-web/envs/prod" \
  "environments/dev" \
  "environments/prod"; do
  render_overlay "$overlay"
done

if [[ "$status" -ne 0 ]]; then
  echo "[env-contract] result: FAILED" >&2
  exit 1
fi

echo "[env-contract] result: PASSED"
