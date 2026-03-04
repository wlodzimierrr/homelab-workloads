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

if command -v kustomize >/dev/null 2>&1; then
  kustomize build apps/homelab-web/envs/dev >/dev/null
elif command -v kubectl >/dev/null 2>&1; then
  kubectl kustomize apps/homelab-web/envs/dev >/dev/null
else
  echo "warning: neither kustomize nor kubectl found; skipped render validation" >&2
fi

echo "sso manifest validation passed"
