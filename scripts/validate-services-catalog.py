#!/usr/bin/env python3
"""Validate workloads/services.yaml against the catalog schema.

Exit 0 on success, 1 on any validation failure.

Usage:
    python3 scripts/validate-services-catalog.py [--catalog services.yaml]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print(
        "validate-services-catalog: pyyaml is required. Install with: pip install pyyaml",
        file=sys.stderr,
    )
    sys.exit(2)


SERVICE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]+$")
VALID_OBSERVABILITY_MODES = frozenset({"app-native", "ingress-derived", "no-http"})
VALID_ENV_NAMES = frozenset({"dev", "prod"})

REQUIRED_SERVICE_FIELDS = ("service_id", "description", "repo_url", "runbook_url", "observability", "envs")
REQUIRED_ENV_FIELDS = ("name", "namespace", "argo_app")

_status = 0
_pass_count = 0
_fail_count = 0


def _pass(msg: str) -> None:
    global _pass_count
    _pass_count += 1
    print(f"[catalog] OK: {msg}")


def _fail(msg: str) -> None:
    global _status, _fail_count
    _status = 1
    _fail_count += 1
    print(f"[catalog] FAIL: {msg}", file=sys.stderr)


def validate_catalog(catalog_path: Path) -> None:
    if not catalog_path.exists():
        _fail(f"catalog file not found: {catalog_path}")
        return

    try:
        raw = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        _fail(f"YAML parse error in {catalog_path}: {exc}")
        return

    if not isinstance(raw, dict):
        _fail(f"{catalog_path} must be a YAML mapping at the top level, got {type(raw).__name__}")
        return

    services = raw.get("services")
    if not isinstance(services, list):
        _fail(f"top-level 'services' must be a list, got {type(services).__name__}")
        return
    if len(services) == 0:
        _fail("services list is empty")
        return

    _pass(f"catalog parses as valid YAML with {len(services)} service entries")

    seen_service_ids: set[str] = set()

    for idx, entry in enumerate(services):
        label = f"entry[{idx}]"

        if not isinstance(entry, dict):
            _fail(f"{label} is not a YAML mapping")
            continue

        service_id = entry.get("service_id")
        if not isinstance(service_id, str) or not service_id.strip():
            _fail(f"{label} missing or empty 'service_id'")
            continue

        label = f"service '{service_id}'"

        if not SERVICE_ID_PATTERN.match(service_id):
            _fail(f"{label} service_id must match ^[a-z][a-z0-9-]+$, got '{service_id}'")
        else:
            _pass(f"{label} service_id is valid kebab-case")

        if service_id in seen_service_ids:
            _fail(f"{label} duplicate service_id '{service_id}'")
        else:
            seen_service_ids.add(service_id)
            _pass(f"{label} service_id is unique")

        # Required fields
        missing = [f for f in REQUIRED_SERVICE_FIELDS if f not in entry]
        if missing:
            _fail(f"{label} missing required fields: {', '.join(missing)}")
        else:
            _pass(f"{label} has all required fields")

        # description non-empty
        desc = entry.get("description")
        if isinstance(desc, str) and desc.strip():
            _pass(f"{label} description is non-empty")
        else:
            _fail(f"{label} 'description' must be a non-empty string")

        # repo_url non-empty
        repo_url = entry.get("repo_url")
        if isinstance(repo_url, str) and repo_url.strip():
            _pass(f"{label} repo_url is present")
        else:
            _fail(f"{label} 'repo_url' must be a non-empty string")

        # runbook_url non-empty
        runbook_url = entry.get("runbook_url")
        if isinstance(runbook_url, str) and runbook_url.strip():
            _pass(f"{label} runbook_url is present")
        else:
            _fail(f"{label} 'runbook_url' must be a non-empty string")

        # observability.mode
        obs = entry.get("observability")
        if isinstance(obs, dict):
            mode = obs.get("mode")
            if mode in VALID_OBSERVABILITY_MODES:
                _pass(f"{label} observability.mode is valid ({mode})")
            else:
                _fail(
                    f"{label} observability.mode must be one of "
                    f"{sorted(VALID_OBSERVABILITY_MODES)}, got {mode!r}"
                )
        else:
            _fail(f"{label} 'observability' must be a mapping with a 'mode' key")

        # tags (optional) — must be a list of strings if present
        tags = entry.get("tags")
        if tags is not None:
            if isinstance(tags, list) and all(isinstance(t, str) for t in tags):
                _pass(f"{label} tags is a valid list of strings")
            else:
                _fail(f"{label} 'tags' must be a list of strings if present")

        # owner_email (optional) — must be a string if present
        owner_email = entry.get("owner_email")
        if owner_email is not None:
            if isinstance(owner_email, str) and owner_email.strip():
                _pass(f"{label} owner_email is present and non-empty")
            else:
                _fail(f"{label} 'owner_email' must be a non-empty string if present")

        # envs
        envs = entry.get("envs")
        if not isinstance(envs, list) or len(envs) == 0:
            _fail(f"{label} 'envs' must be a non-empty list")
            continue

        _pass(f"{label} has {len(envs)} env entries")

        seen_env_names: set[str] = set()
        for env_entry in envs:
            if not isinstance(env_entry, dict):
                _fail(f"{label} env entry is not a mapping")
                continue

            env_name = env_entry.get("name")
            env_label = f"{label} env '{env_name}'"

            if env_name not in VALID_ENV_NAMES:
                _fail(f"{label} env name must be one of {sorted(VALID_ENV_NAMES)}, got {env_name!r}")
            else:
                _pass(f"{env_label} env name is valid")

            if env_name in seen_env_names:
                _fail(f"{label} duplicate env name '{env_name}'")
            else:
                seen_env_names.add(str(env_name))

            missing_env = [f for f in REQUIRED_ENV_FIELDS if f not in env_entry]
            if missing_env:
                _fail(f"{env_label} missing required fields: {', '.join(missing_env)}")
            else:
                _pass(f"{env_label} has all required fields")

            argo_app = env_entry.get("argo_app")
            namespace = env_entry.get("namespace")

            if isinstance(namespace, str) and namespace.strip():
                _pass(f"{env_label} namespace is present")
            else:
                _fail(f"{env_label} 'namespace' must be a non-empty string")

            if isinstance(argo_app, str) and argo_app.strip():
                _pass(f"{env_label} argo_app '{argo_app}' is present")
            else:
                _fail(f"{env_label} 'argo_app' must be a non-empty string")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate workloads/services.yaml against the catalog schema.",
    )
    parser.add_argument(
        "--catalog",
        default="services.yaml",
        help="Path to the services catalog YAML file (default: services.yaml)",
    )
    args = parser.parse_args()

    catalog_path = Path(args.catalog)
    print(f"[catalog] validating {catalog_path} ...")
    validate_catalog(catalog_path)

    print(f"[catalog] checks: {_pass_count} passed, {_fail_count} failed")
    if _status != 0:
        print("[catalog] result: FAILED", file=sys.stderr)
        sys.exit(1)
    print("[catalog] result: PASSED")


if __name__ == "__main__":
    main()
