#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

echo "[rbac-guardrails] scanning workloads manifests..."

fail=0
rbac_files="$(rg -l --glob 'apps/**/*.yaml' 'kind:\s*(Role|ClusterRole|RoleBinding|ClusterRoleBinding)' apps || true)"
cluster_admin_hits_file="$(mktemp)"
rbac_wildcard_hits_file="$(mktemp)"
trap 'rm -f "$cluster_admin_hits_file" "$rbac_wildcard_hits_file"' EXIT

allowed_clusterrolebinding_file="apps/homelab-api/base/clusterrolebinding-backend-kube-api-read.yaml"
allowed_clusterrole_file="apps/homelab-api/base/clusterrole-backend-kube-api-read.yaml"
allowed_clusterrole_name="homelab-api-backend-kube-api-read"

# 1) App workloads must not define cluster-admin style bindings.
if rg -n --glob 'apps/**/*.yaml' 'cluster-admin' apps >"$cluster_admin_hits_file"; then
  echo "[rbac-guardrails] FAIL: disallowed cluster-admin reference in apps/"
  cat "$cluster_admin_hits_file"
  fail=1
else
  echo "[rbac-guardrails] OK: no cluster-admin references in apps/"
fi

# 2) App workloads may define only explicitly approved read-only ClusterRoleBindings.
mapfile -t clusterrolebinding_files < <(rg -l --glob 'apps/**/*.yaml' '^kind:\s*ClusterRoleBinding$' apps || true)

if [[ "${#clusterrolebinding_files[@]}" -eq 0 ]]; then
  echo "[rbac-guardrails] OK: no ClusterRoleBinding objects in apps/"
else
  unexpected_clusterrolebindings=0

  for file in "${clusterrolebinding_files[@]}"; do
    if [[ "$file" != "$allowed_clusterrolebinding_file" ]]; then
      echo "[rbac-guardrails] FAIL: unexpected ClusterRoleBinding in apps/: $file"
      unexpected_clusterrolebindings=1
      fail=1
      continue
    fi

    if [[ "$(sed -nE 's/^[[:space:]]*name:[[:space:]]*([^[:space:]]+).*$/\1/p' "$file" | head -n1)" != "$allowed_clusterrole_name" ]]; then
      echo "[rbac-guardrails] FAIL: approved ClusterRoleBinding name drifted in $file"
      fail=1
    fi
    if ! rg -q '^[[:space:]-]*kind:[[:space:]]*ServiceAccount$' "$file"; then
      echo "[rbac-guardrails] FAIL: approved ClusterRoleBinding must bind a ServiceAccount in $file"
      fail=1
    fi
    if ! rg -q '^[[:space:]]*name:[[:space:]]*homelab-api-backend$' "$file"; then
      echo "[rbac-guardrails] FAIL: approved ClusterRoleBinding subject must remain homelab-api-backend in $file"
      fail=1
    fi
    if ! rg -q '^[[:space:]]*namespace:[[:space:]]*homelab-api$' "$file"; then
      echo "[rbac-guardrails] FAIL: approved ClusterRoleBinding subject namespace must remain homelab-api in $file"
      fail=1
    fi
    if ! rg -q '^[[:space:]]*kind:[[:space:]]*ClusterRole$' "$file"; then
      echo "[rbac-guardrails] FAIL: approved ClusterRoleBinding must reference a ClusterRole in $file"
      fail=1
    fi
    if ! awk -v expected="$allowed_clusterrole_name" '
      $1 == "roleRef:" {in_role_ref=1; next}
      in_role_ref && /^[^[:space:]]/ {in_role_ref=0}
      in_role_ref && $1 == "name:" && $2 == expected {found=1}
      END {exit found ? 0 : 1}
    ' "$file"; then
      echo "[rbac-guardrails] FAIL: approved ClusterRoleBinding roleRef must remain ${allowed_clusterrole_name} in $file"
      fail=1
    fi

    echo "[rbac-guardrails] OK: approved read-only ClusterRoleBinding present: $file"
  done

  if [[ "$unexpected_clusterrolebindings" -eq 0 ]] && [[ -f "$allowed_clusterrole_file" ]]; then
    if rg -n '^[[:space:]]*-[[:space:]]*(create|update|patch|delete|deletecollection|bind|escalate|impersonate|approve)$' "$allowed_clusterrole_file"; then
      echo "[rbac-guardrails] FAIL: approved ClusterRole must remain read-only: $allowed_clusterrole_file"
      fail=1
    else
      echo "[rbac-guardrails] OK: approved ClusterRole verbs remain read-only"
    fi
  elif [[ "$unexpected_clusterrolebindings" -eq 0 ]]; then
    echo "[rbac-guardrails] FAIL: missing approved ClusterRole file: $allowed_clusterrole_file"
    fail=1
  fi
fi

# 3) Prevent wildcard RBAC rules in app roles.
if [[ -n "${rbac_files}" ]]; then
  if rg -n '^\s*-\s*"\*"\s*$|^\s*-\s*\*\s*$' ${rbac_files} >"$rbac_wildcard_hits_file"; then
    echo "[rbac-guardrails] FAIL: wildcard RBAC token found in apps RBAC manifests"
    cat "$rbac_wildcard_hits_file"
    fail=1
  else
    echo "[rbac-guardrails] OK: no wildcard RBAC tokens in apps RBAC manifests"
  fi
else
  echo "[rbac-guardrails] OK: no app RBAC manifests found to evaluate for wildcards"
fi

if [[ "$fail" -ne 0 ]]; then
  echo "[rbac-guardrails] result: FAILED"
  exit 1
fi

echo "[rbac-guardrails] result: PASSED"
