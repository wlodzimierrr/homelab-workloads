#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

required_files=(
  "bootstrap/argocd-oidc.yaml"
  "apps/homelab-web/envs/dev/oauth2-proxy.yaml"
  "apps/homelab-web/envs/dev/middleware-oauth2.yaml"
  "apps/homelab-web/envs/dev/networkpolicy-allow-ingress-oauth2-proxy.yaml"
  "apps/homelab-web/envs/dev/networkpolicy-allow-egress-oauth2-proxy.yaml"
)

for file in "${required_files[@]}"; do
  if [[ ! -f "$file" ]]; then
    echo "missing required file: $file" >&2
    exit 1
  fi
done

"$repo_root/scripts/render-kustomize.sh" apps/homelab-web/envs/dev >/dev/null

if ! rg -n '^[[:space:]]*-[[:space:]]*"401"[[:space:]]*$' "apps/homelab-web/envs/dev/middleware-oauth2.yaml" >/dev/null; then
  echo "oauth2 errors middleware must rewrite 401 responses" >&2
  exit 1
fi

if rg -n '401-403|403-403|^[[:space:]]*-[[:space:]]*"403"[[:space:]]*$' "apps/homelab-web/envs/dev/middleware-oauth2.yaml" >/dev/null; then
  echo "oauth2 errors middleware must not rewrite 403 responses" >&2
  exit 1
fi

echo "sso manifest validation passed"
