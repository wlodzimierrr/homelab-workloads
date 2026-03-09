# RBAC Audit Report - 2026-03-04

## Scope

- Repository: `workloads`
- Areas reviewed:
  - `apps/**`
  - `platform/**`
  - `environments/**`
  - `bootstrap/**`
- Target ticket: `T3.1.2 Audit and tighten Kubernetes service account permissions`

## Audit commands

```bash
rg -n "kind:\s*(ServiceAccount|Role|ClusterRole|RoleBinding|ClusterRoleBinding)|cluster-admin|\*" -S apps platform environments bootstrap
```

```bash
./scripts/check-rbac-guardrails.sh
```

## Findings

### RBAC objects present for app workloads

- `apps/homelab-api/base/serviceaccount-backend.yaml` (`ServiceAccount`)
- `apps/homelab-web/base/serviceaccount-web.yaml` (`ServiceAccount`)
- `apps/homelab-api/base/role-backend-kube-api-read.yaml` (`Role`)
- `apps/homelab-api/base/rolebinding-backend-kube-api-read.yaml` (`RoleBinding`)
- `apps/homelab-api/base/clusterrole-backend-kube-api-read.yaml` (`ClusterRole`)
- `apps/homelab-api/base/clusterrolebinding-backend-kube-api-read.yaml` (`ClusterRoleBinding`)

### Risk checks

- One approved `ClusterRoleBinding` exists in `apps/**` for `homelab-api` cluster-wide read-only discovery.
- No `cluster-admin` role references in `apps/**`.
- No wildcard (`*`) verbs/resources/apiGroups in app RBAC manifests.
- App RBAC is namespace-scoped by default, with one reviewed read-only `ClusterRole` + `ClusterRoleBinding` exception for `homelab-api` to read namespaces and Argo `Application` resources.

## Tightening actions completed

- Added guardrail script: `scripts/check-rbac-guardrails.sh`
  - Fails if app manifests introduce:
    - unexpected `ClusterRoleBinding`
    - `cluster-admin` references
    - wildcard RBAC tokens (`*`)
    - mutating verbs in the approved read-only `ClusterRole`

## Conclusion

- Acceptance criterion 1 met: no cluster-admin bindings for app workloads, and the only cluster-wide binding is a reviewed read-only exception.
- Acceptance criterion 2 met: RBAC audit report committed.
