#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root"

env_name="${1:-dev}"
if [[ "$env_name" != "dev" ]]; then
  echo "usage: $0 [dev]"
  exit 1
fi

if ! command -v kubectl >/dev/null 2>&1; then
  echo "kubectl is required"
  exit 1
fi

age_key_file="${SOPS_AGE_KEY_FILE:-$HOME/.config/sops/age/keys.txt}"
if [[ ! -f "$age_key_file" ]]; then
  echo "missing age key file: $age_key_file"
  exit 1
fi

kubectl -n homelab-api create secret generic homelab-api-sops-age \
  --from-file=keys.txt="$age_key_file" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "applied: secret/homelab-api-sops-age in namespace homelab-api"
echo "next: kubectl -n homelab-api rollout restart deploy/homelab-api"
