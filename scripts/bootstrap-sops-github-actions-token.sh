#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"

if ! command -v sops >/dev/null 2>&1; then
  echo "sops is required but not installed."
  exit 1
fi

if [[ ! -f .sops.yaml ]]; then
  echo "missing workloads/.sops.yaml"
  exit 1
fi

if grep -q 'age1REPLACE_WITH_YOUR_PUBLIC_KEY' .sops.yaml; then
  echo "replace placeholder age recipient in workloads/.sops.yaml first"
  exit 1
fi

mode="${1:---prompt}"
env_name="${2:-dev}"
if [[ "$mode" != "--prompt" && "$mode" != "--from-cluster" ]]; then
  echo "usage: $0 [--prompt|--from-cluster] [dev]"
  exit 1
fi

if [[ "$env_name" != "dev" ]]; then
  echo "usage: $0 [--prompt|--from-cluster] [dev]"
  exit 1
fi

secret_path="apps/homelab-api/envs/${env_name}/github-actions-secret.enc.yaml"
generator_path="apps/homelab-api/envs/${env_name}/github-actions-secret-generator.yaml"
kustomization_path="apps/homelab-api/envs/${env_name}/kustomization.yaml"

token=""
if [[ "$mode" == "--from-cluster" ]]; then
  if ! command -v kubectl >/dev/null 2>&1; then
    echo "kubectl is required for --from-cluster mode"
    exit 1
  fi
  if ! command -v base64 >/dev/null 2>&1; then
    echo "base64 is required for --from-cluster mode"
    exit 1
  fi

  token_b64="$(kubectl -n homelab-api get secret homelab-api-github-actions -o jsonpath='{.data.PORTAL_GITHUB_ACTIONS_TOKEN}')"
  if [[ -z "$token_b64" ]]; then
    echo "cluster secret homelab-api-github-actions is missing PORTAL_GITHUB_ACTIONS_TOKEN"
    exit 1
  fi
  token="$(printf '%s' "$token_b64" | base64 -d)"
else
  read -rsp "PORTAL_GITHUB_ACTIONS_TOKEN: " token
  echo
fi

if [[ -z "$token" ]]; then
  echo "PORTAL_GITHUB_ACTIONS_TOKEN cannot be empty"
  exit 1
fi

tmp_plain="$(mktemp)"
cat > "$tmp_plain" <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: homelab-api-github-actions
  namespace: homelab-api
type: Opaque
stringData:
  PORTAL_GITHUB_ACTIONS_TOKEN: ${token}
EOF

cp "$tmp_plain" "$secret_path"
sops --encrypt --in-place "$secret_path"
rm -f "$tmp_plain"

cat > "$generator_path" <<'EOF'
apiVersion: viaduct.ai/v1
kind: ksops
metadata:
  name: github-actions-secret-generator
  annotations:
    config.kubernetes.io/function: |
      exec:
        path: ksops
files:
  - github-actions-secret.enc.yaml
EOF

if ! grep -qE '^[[:space:]]*-[[:space:]]*github-actions-secret-generator\.yaml[[:space:]]*$' "$kustomization_path"; then
  awk '
    /^generators:/ && inserted == 0 { print; print "  - github-actions-secret-generator.yaml"; inserted = 1; next }
    /^commonLabels:/ && inserted == 0 { print "generators:"; print "  - github-actions-secret-generator.yaml"; inserted = 1 }
    { print }
  ' "$kustomization_path" > "${kustomization_path}.tmp"
  mv "${kustomization_path}.tmp" "$kustomization_path"
fi

echo "created: $secret_path"
echo "created: $generator_path"
echo "updated: $kustomization_path"
echo "next: ./scripts/check-secrets-guardrails.sh && ./scripts/render-kustomize.sh apps/homelab-api/envs/${env_name} >/dev/null"
