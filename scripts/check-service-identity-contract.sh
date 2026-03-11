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
  echo "[identity-contract] OK: $1"
}

fail() {
  echo "[identity-contract] FAIL: $1" >&2
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
      if rg -q -- "$pattern" "$file"; then
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

echo "[identity-contract] checking canonical service identity across GitOps and workload manifests..."

extract_service_block() {
  local service_id="$1"

  awk -v sid="$service_id" '
    /^[[:space:]]*- service_id:[[:space:]]*/ {
      if (capture) {
        exit
      }
      if ($0 ~ "^[[:space:]]*- service_id:[[:space:]]*" sid "$") {
        capture=1
      }
    }
    capture { print }
  ' services.yaml
}

while IFS= read -r app_dir; do
  service_id="$(basename "$app_dir")"
  service_block="$(extract_service_block "$service_id")"

  require_regex "services.yaml" "^[[:space:]]*- service_id:[[:space:]]*${service_id}$" "service catalog entry exists for ${service_id}"
  require_regex "services.yaml" "argo_app:[[:space:]]*${service_id}-dev$" "service catalog dev Argo app matches ${service_id}"
  require_regex "services.yaml" "argo_app:[[:space:]]*${service_id}-prod$" "service catalog prod Argo app matches ${service_id}"
  require_regex "services.yaml" "namespace:[[:space:]]*${service_id}$" "service catalog namespace matches ${service_id}"

  if [[ -z "$service_block" ]]; then
    fail "service catalog block can be extracted for ${service_id}"
  elif printf '%s\n' "$service_block" | grep -Eq '^[[:space:]]*observability:[[:space:]]*$'; then
    pass "service catalog observability block exists for ${service_id}"
  else
    fail "service catalog observability block exists for ${service_id}"
  fi

  if [[ -n "$service_block" ]] && printf '%s\n' "$service_block" | grep -Eq '^[[:space:]]*mode:[[:space:]]*(app-native|ingress-derived|no-http)$'; then
    pass "service catalog observability mode is valid for ${service_id}"
  else
    fail "service catalog observability mode is valid for ${service_id}"
  fi

  dev_app_file="environments/dev/workloads/${service_id}-app.yaml"
  require_file "$dev_app_file" "dev workload application exists for ${service_id}"
  require_regex "$dev_app_file" "^  name: ${service_id}-dev$" "dev Argo application name matches ${service_id}"
  require_regex "$dev_app_file" "^    path: apps/${service_id}/envs/dev$" "dev Argo application path matches ${service_id}"
  require_regex "$dev_app_file" "^    namespace: ${service_id}$" "dev Argo destination namespace matches ${service_id}"

  base_deployment="${app_dir}/base/deployment.yaml"
  require_file "$base_deployment" "base deployment exists for ${service_id}"
  require_regex "$base_deployment" "app.kubernetes.io/name:[[:space:]]*${service_id}$" "deployment labels use canonical app label for ${service_id}"
  require_regex "$base_deployment" "^  namespace: ${service_id}$" "deployment namespace matches ${service_id}"

  base_service="${app_dir}/base/service.yaml"
  if [[ -f "$base_service" ]]; then
    require_regex "$base_service" "app.kubernetes.io/name:[[:space:]]*${service_id}$" "service selector uses canonical app label for ${service_id}"
    require_regex "$base_service" "^  namespace: ${service_id}$" "service namespace matches ${service_id}"
  fi

  service_monitor="${app_dir}/base/servicemonitor.yaml"
  if [[ -f "$service_monitor" ]]; then
    require_regex "$service_monitor" "app.kubernetes.io/name:[[:space:]]*${service_id}$" "ServiceMonitor selector uses canonical app label for ${service_id}"
    require_regex "$service_monitor" "matchNames:" "ServiceMonitor uses namespace selector for ${service_id}"
    require_regex "$service_monitor" "-[[:space:]]*${service_id}$" "ServiceMonitor scopes to ${service_id} namespace"
  fi
done < <(find apps -mindepth 1 -maxdepth 1 -type d | sort)

if [[ "$status" -ne 0 ]]; then
  echo "[identity-contract] result: FAILED" >&2
  exit 1
fi

echo "[identity-contract] result: PASSED"
