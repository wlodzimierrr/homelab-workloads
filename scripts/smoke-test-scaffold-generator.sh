#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp_root="$(mktemp -d)"
trap 'rm -rf "$tmp_root"' EXIT

gitops_root="$tmp_root/workloads"
repo_output_dir="$tmp_root/scaffold-smoke-repo"

cp -R "$repo_root" "$gitops_root"
rm -rf "$gitops_root/.git"

python3 "$repo_root/scripts/scaffold-service.py" \
  --name scaffold-smoke \
  --description "Smoke-test scaffolded FastAPI service" \
  --image-repo ghcr.io/example/scaffold-smoke \
  --repo-url https://github.com/example/scaffold-smoke \
  --owner-email ops@example.com \
  --template python-fastapi \
  --gitops-root "$gitops_root" \
  --repo-output-dir "$repo_output_dir" \
  --image-pull-secret ""

required_paths=(
  "$repo_output_dir/.github/workflows/build-scaffold-smoke.yml"
  "$repo_output_dir/app/main.py"
  "$gitops_root/apps/scaffold-smoke/base/kustomization.yaml"
  "$gitops_root/apps/scaffold-smoke/envs/dev/kustomization.yaml"
  "$gitops_root/apps/scaffold-smoke/envs/prod/kustomization.yaml"
  "$gitops_root/environments/dev/workloads/scaffold-smoke-app.yaml"
  "$gitops_root/environments/prod/workloads/scaffold-smoke-app.yaml"
  "$gitops_root/services.yaml"
)

for path in "${required_paths[@]}"; do
  if [[ ! -f "$path" ]]; then
    echo "missing generated file: $path" >&2
    exit 1
  fi
done

grep -q "service_id: scaffold-smoke" "$gitops_root/services.yaml"
grep -q "repo_url: 'https://github.com/example/scaffold-smoke'" "$gitops_root/services.yaml"

if command -v kustomize >/dev/null 2>&1; then
  kustomize build "$gitops_root/apps/scaffold-smoke/envs/dev" >/dev/null
  kustomize build "$gitops_root/apps/scaffold-smoke/envs/prod" >/dev/null
  kustomize build "$gitops_root/environments/dev" >/dev/null
  kustomize build "$gitops_root/environments/prod" >/dev/null
elif command -v kubectl >/dev/null 2>&1; then
  kubectl kustomize "$gitops_root/apps/scaffold-smoke/envs/dev" >/dev/null
  kubectl kustomize "$gitops_root/apps/scaffold-smoke/envs/prod" >/dev/null
  kubectl kustomize "$gitops_root/environments/dev" >/dev/null
  kubectl kustomize "$gitops_root/environments/prod" >/dev/null
else
  echo "warning: neither kustomize nor kubectl found; skipped render validation" >&2
fi

"$gitops_root/scripts/check-environment-contract.sh" >/dev/null
"$gitops_root/scripts/check-rbac-guardrails.sh" >/dev/null
"$gitops_root/scripts/check-secrets-guardrails.sh" >/dev/null

echo "scaffold generator smoke test passed"
