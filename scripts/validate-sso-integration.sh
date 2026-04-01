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

if ! rg -n 'router\.middlewares:\s+homelab-web-oauth2-errors@kubernetescrd,homelab-web-oauth2-forward-auth@kubernetescrd' "apps/homelab-web/envs/dev/patch-ingress.yaml" >/dev/null; then
  echo "UI ingress must keep oauth2 error rewriting before forward auth" >&2
  exit 1
fi

if ! rg -n 'router\.middlewares:\s+homelab-web-oauth2-forward-auth@kubernetescrd' "apps/homelab-web/envs/dev/patch-ingress-api.yaml" >/dev/null; then
  echo "API ingress must use forward auth without oauth2 error rewriting" >&2
  exit 1
fi

if rg -n 'oauth2-errors@kubernetescrd' "apps/homelab-web/envs/dev/patch-ingress-api.yaml" >/dev/null; then
  echo "API ingress must not use oauth2 error rewriting" >&2
  exit 1
fi

echo "sso manifest validation passed"
