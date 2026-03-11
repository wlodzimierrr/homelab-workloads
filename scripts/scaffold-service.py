#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
import re
import textwrap


SERVICE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,62}$")


@dataclass(frozen=True)
class TemplateSpec:
    key: str
    display_name: str
    container_port: int
    service_port: int
    health_path: str
    readiness_path: str
    container_name: str
    default_observability_mode: str
    repo_files: dict[str, str]


def dedent(value: str) -> str:
    return textwrap.dedent(value).strip() + "\n"


def render_template(template: str, **values: str) -> str:
    return dedent(template.format(**values))


def indent_block(value: str, spaces: int) -> str:
    prefix = " " * spaces
    return "\n".join(f"{prefix}{line}" if line else line for line in value.splitlines())


def yaml_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def build_python_fastapi_repo_files(name: str, description: str, image_repo: str) -> dict[str, str]:
    return {
        ".gitignore": dedent(
            """
            __pycache__/
            *.pyc
            .pytest_cache/
            .venv/
            dist/
            build/
            """
        ),
        ".dockerignore": dedent(
            """
            .git
            .github
            .pytest_cache
            .venv
            __pycache__
            tests
            """
        ),
        "README.md": render_template(
            """
            # {name}

            {description}

            ## Local Development

            ```bash
            python3 -m venv .venv
            . .venv/bin/activate
            pip install -e .[dev]
            uvicorn app.main:app --reload --port 8000
            ```

            ## Tests

            ```bash
            pytest
            ```

            ## Image

            CI publishes `sha-<commit>` tags to `{image_repo}` on pushes to `main`.
            """,
            name=name,
            description=description,
            image_repo=image_repo,
        ),
        "pyproject.toml": render_template(
            """
            [build-system]
            requires = ["setuptools>=68", "wheel"]
            build-backend = "setuptools.build_meta"

            [project]
            name = "{name}"
            version = "0.1.0"
            description = "{description}"
            requires-python = ">=3.11"
            dependencies = [
              "fastapi>=0.116,<1.0",
              "uvicorn[standard]>=0.35,<1.0",
            ]

            [project.optional-dependencies]
            dev = [
              "httpx>=0.28,<1.0",
              "pytest>=8.4,<9.0",
            ]

            [tool.setuptools.packages.find]
            include = ["app*"]
            """,
            name=name,
            description=description,
        ),
        "app/__init__.py": "",
        "app/main.py": dedent(
            """
            from fastapi import FastAPI


            app = FastAPI(title="scaffolded-service")


            @app.get("/health")
            async def health() -> dict[str, str]:
                return {"status": "ok"}


            @app.get("/")
            async def root() -> dict[str, str]:
                return {"service": "ready"}
            """
        ),
        "tests/test_health.py": dedent(
            """
            from fastapi.testclient import TestClient

            from app.main import app


            client = TestClient(app)


            def test_health() -> None:
                response = client.get("/health")
                assert response.status_code == 200
                assert response.json() == {"status": "ok"}
            """
        ),
        "Dockerfile": dedent(
            """
            FROM python:3.11-slim

            WORKDIR /app

            COPY pyproject.toml ./
            COPY app ./app

            RUN pip install --no-cache-dir --upgrade pip \
              && pip install --no-cache-dir .

            EXPOSE 8000

            CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
            """
        ),
    }


def build_static_nginx_repo_files(name: str, description: str, image_repo: str) -> dict[str, str]:
    return {
        ".gitignore": dedent(
            """
            dist/
            .DS_Store
            """
        ),
        ".dockerignore": dedent(
            """
            .git
            .github
            """
        ),
        "README.md": render_template(
            """
            # {name}

            {description}

            ## Local Preview

            ```bash
            docker build -t {name}:local .
            docker run --rm -p 8080:80 {name}:local
            ```

            ## Image

            CI publishes `sha-<commit>` tags to `{image_repo}` on pushes to `main`.
            """,
            name=name,
            description=description,
            image_repo=image_repo,
        ),
        "site/index.html": render_template(
            """
            <!doctype html>
            <html lang="en">
              <head>
                <meta charset="utf-8" />
                <meta name="viewport" content="width=device-width, initial-scale=1" />
                <title>{name}</title>
                <style>
                  body {{
                    font-family: "IBM Plex Sans", sans-serif;
                    margin: 0;
                    min-height: 100vh;
                    display: grid;
                    place-items: center;
                    background: linear-gradient(160deg, #f8f2e8 0%, #dce7f3 100%);
                    color: #1f2933;
                  }}
                  main {{
                    width: min(90vw, 44rem);
                    padding: 3rem;
                    border-radius: 1.5rem;
                    background: rgba(255, 255, 255, 0.8);
                    box-shadow: 0 24px 80px rgba(15, 23, 42, 0.12);
                  }}
                  h1 {{
                    margin-top: 0;
                    font-size: clamp(2rem, 5vw, 3.5rem);
                  }}
                </style>
              </head>
              <body>
                <main>
                  <h1>{name}</h1>
                  <p>{description}</p>
                  <p>Replace this page with the real service UI.</p>
                </main>
              </body>
            </html>
            """,
            name=name,
            description=description,
        ),
        "nginx.conf": dedent(
            """
            server {
              listen 80;
              server_name _;
              root /usr/share/nginx/html;
              index index.html;

              location /health {
                add_header Content-Type text/plain;
                return 200 "ok";
              }

              location / {
                try_files $uri $uri/ /index.html;
              }
            }
            """
        ),
        "Dockerfile": dedent(
            """
            FROM nginx:1.27-alpine

            COPY nginx.conf /etc/nginx/conf.d/default.conf
            COPY site /usr/share/nginx/html
            """
        ),
    }


TEMPLATES: dict[str, TemplateSpec] = {
    "python-fastapi": TemplateSpec(
        key="python-fastapi",
        display_name="Python + FastAPI",
        container_port=8000,
        service_port=80,
        health_path="/health",
        readiness_path="/health",
        container_name="app",
        default_observability_mode="app-native",
        repo_files={},
    ),
    "static-nginx": TemplateSpec(
        key="static-nginx",
        display_name="Static site + Nginx",
        container_port=80,
        service_port=80,
        health_path="/health",
        readiness_path="/health",
        container_name="web",
        default_observability_mode="ingress-derived",
        repo_files={},
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scaffold a service repo plus matching GitOps manifests.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--name", required=True, help="Kubernetes-safe service name, for example my-app")
    parser.add_argument("--description", required=True, help="Short service description")
    parser.add_argument("--image-repo", "--image", dest="image_repo", required=True, help="Image repository without a tag")
    parser.add_argument("--repo-url", required=True, help="Source repository URL for the generated service")
    parser.add_argument("--owner", default="", help="Owning team or person label; defaults to owner email")
    parser.add_argument("--owner-email", required=True, help="Owning contact email")
    parser.add_argument("--runbook-url", default="", help="Runbook URL; defaults to the repo URL until replaced")
    parser.add_argument(
        "--template",
        choices=sorted(TEMPLATES),
        default="python-fastapi",
        help="Repository/template type to generate",
    )
    parser.add_argument(
        "--gitops-root",
        default=str(Path(__file__).resolve().parents[1]),
        help="Root of the workloads GitOps repository to modify",
    )
    parser.add_argument(
        "--repo-output-dir",
        default="",
        help="Directory to generate the new service source repo into; defaults to /tmp/<name>-repo",
    )
    parser.add_argument("--namespace", default="", help="Kubernetes namespace; defaults to the service name")
    parser.add_argument("--dev-host", default="", help="Dev ingress host; defaults to <name>.dev.homelab.local")
    parser.add_argument("--prod-host", default="", help="Prod ingress host; defaults to <name>.homelab.local")
    parser.add_argument("--dev-tag", default="0.1.0", help="Initial dev image tag")
    parser.add_argument("--prod-tag", default="0.1.0", help="Initial prod image tag")
    parser.add_argument("--image-pull-secret", default="ghcr-pull-secret", help="Image pull secret; use '' for public images")
    parser.add_argument("--dev-replicas", type=int, default=1, help="Initial dev replica count")
    parser.add_argument("--prod-replicas", type=int, default=2, help="Initial prod replica count")
    parser.add_argument("--container-port", type=int, default=0, help="Override the template container port")
    parser.add_argument("--service-port", type=int, default=0, help="Override the service port")
    parser.add_argument("--health-path", default="", help="Override the liveness probe path")
    parser.add_argument("--readiness-path", default="", help="Override the readiness probe path")
    parser.add_argument(
        "--observability-mode",
        choices=("app-native", "ingress-derived", "no-http"),
        default="",
        help="Declared service observability mode written into services.yaml",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite an existing empty output repo directory")
    return parser.parse_args()


def validate_service_name(name: str) -> None:
    if not SERVICE_NAME_PATTERN.match(name):
        raise SystemExit("service name must match ^[a-z][a-z0-9-]{1,62}$")


def ensure_gitops_root(gitops_root: Path) -> None:
    required = [
        gitops_root / "bootstrap" / "project-homelab.yaml",
        gitops_root / "environments" / "dev" / "workloads" / "kustomization.yaml",
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise SystemExit(f"gitops root is missing required files: {', '.join(missing)}")


def ensure_absent(path: Path, description: str) -> None:
    if path.exists():
        raise SystemExit(f"{description} already exists: {path}")


def ensure_repo_output_dir(path: Path, force: bool) -> None:
    if path.exists():
        if any(path.iterdir()):
            raise SystemExit(f"repo output dir is not empty: {path}")
        if not force:
            raise SystemExit(f"repo output dir already exists; pass --force if you want to use it: {path}")
    path.mkdir(parents=True, exist_ok=True)


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def append_unique_resource(kustomization_path: Path, resource_name: str) -> None:
    lines = kustomization_path.read_text(encoding="utf-8").splitlines()
    if any(line.strip() == f"- {resource_name}" for line in lines):
        return

    output: list[str] = []
    inserted = False
    for line in lines:
        output.append(line)
        if line.strip() == "resources:":
            inserted = True
            continue
    if not inserted:
        raise SystemExit(f"expected resources: block in {kustomization_path}")

    resource_lines = [line.strip() for line in lines if line.strip().startswith("- ")]
    resource_lines.append(f"- {resource_name}")
    resource_lines = sorted(dict.fromkeys(resource_lines))

    rebuilt: list[str] = []
    in_resources = False
    for line in lines:
        stripped = line.strip()
        if stripped == "resources:":
            rebuilt.append(line)
            for resource_line in resource_lines:
                rebuilt.append(f"  {resource_line}")
            in_resources = True
            continue
        if in_resources and stripped.startswith("- "):
            continue
        rebuilt.append(line)

    kustomization_path.write_text("\n".join(rebuilt) + "\n", encoding="utf-8")


def append_appproject(projects_path: Path, content: str, project_name: str) -> None:
    existing = projects_path.read_text(encoding="utf-8")
    if f"name: {project_name}" in existing:
        raise SystemExit(f"AppProject {project_name} already exists in {projects_path}")
    suffix = "" if existing.endswith("\n") else "\n"
    projects_path.write_text(existing + suffix + "---\n" + content, encoding="utf-8")


def append_service_catalog_entry(
    catalog_path: Path,
    *,
    service_id: str,
    display_name: str,
    owner: str,
    owner_email: str,
    repo_url: str,
    runbook_url: str,
    description: str,
    namespace: str,
    observability_mode: str,
) -> None:
    if catalog_path.exists():
        existing = catalog_path.read_text(encoding="utf-8")
    else:
        existing = "services:\n"

    if f"service_id: {service_id}\n" in existing:
        raise SystemExit(f"service catalog entry already exists in {catalog_path}: {service_id}")
    if "services:" not in existing:
        raise SystemExit(f"expected top-level services: list in {catalog_path}")

    entry = (
        f"  - service_id: {service_id}\n"
        f"    name: {yaml_string(display_name)}\n"
        f"    owner: {yaml_string(owner)}\n"
        f"    owner_email: {yaml_string(owner_email)}\n"
        f"    repo_url: {yaml_string(repo_url)}\n"
        f"    runbook_url: {yaml_string(runbook_url)}\n"
        f"    description: {yaml_string(description)}\n"
        "    observability:\n"
        f"      mode: {observability_mode}\n"
        "    envs:\n"
        "      - name: dev\n"
        f"        namespace: {namespace}\n"
        f"        argo_app: {service_id}-dev\n"
        "      - name: prod\n"
        f"        namespace: {namespace}\n"
        f"        argo_app: {service_id}-prod\n"
    )
    suffix = "" if existing.endswith("\n") else "\n"
    catalog_path.write_text(existing + suffix + entry, encoding="utf-8")


def gitops_base_files(
    *,
    name: str,
    namespace: str,
    image_repo: str,
    template: TemplateSpec,
    base_tag: str,
    description: str,
    image_pull_secret: str,
    dev_host: str,
) -> dict[str, str]:
    serviceaccount = render_template(
        """
        apiVersion: v1
        kind: ServiceAccount
        metadata:
          name: {name}
          namespace: {namespace}
          labels:
            app.kubernetes.io/name: {name}
        """,
        name=name,
        namespace=namespace,
    )
    if image_pull_secret:
        serviceaccount += render_template(
            """
            imagePullSecrets:
              - name: {image_pull_secret}
            """,
            image_pull_secret=image_pull_secret,
        )

    probes = render_template(
        """
        readinessProbe:
          httpGet:
            path: {readiness_path}
            port: http
          initialDelaySeconds: 5
          periodSeconds: 10
        livenessProbe:
          httpGet:
            path: {health_path}
            port: http
          initialDelaySeconds: 10
          periodSeconds: 20
        """,
        readiness_path=template.readiness_path,
        health_path=template.health_path,
    )

    deployment_lines = [
        "apiVersion: apps/v1",
        "kind: Deployment",
        "metadata:",
        f"  name: {name}",
        f"  namespace: {namespace}",
        "  labels:",
        f"    app.kubernetes.io/name: {name}",
        "spec:",
        "  replicas: 1",
        "  selector:",
        "    matchLabels:",
        f"      app.kubernetes.io/name: {name}",
        "  template:",
        "    metadata:",
        "      labels:",
        f"        app.kubernetes.io/name: {name}",
        "    spec:",
        f"      serviceAccountName: {name}",
        "      containers:",
        f"        - name: {template.container_name}",
        f"          image: {image_repo}:{base_tag}",
        "          imagePullPolicy: IfNotPresent",
        "          ports:",
        "            - name: http",
        f"              containerPort: {template.container_port}",
        "          env:",
        "            - name: APP_ENV",
        "              value: base",
    ]
    deployment_lines.extend(indent_block(probes.rstrip(), 10).splitlines())
    deployment_lines.extend(
        [
            "          resources:",
            "            requests:",
            "              cpu: 50m",
            "              memory: 64Mi",
            "            limits:",
            "              cpu: 300m",
            "              memory: 256Mi",
        ]
    )

    return {
        "kustomization.yaml": render_template(
            """
            apiVersion: kustomize.config.k8s.io/v1beta1
            kind: Kustomization
            resources:
              - namespace.yaml
              - serviceaccount.yaml
              - deployment.yaml
              - service.yaml
              - ingress.yaml
              - networkpolicy-default-deny.yaml
              - networkpolicy-allow-dns-egress.yaml
              - networkpolicy-allow-ingress.yaml
            """,
        ),
        "namespace.yaml": render_template(
            """
            apiVersion: v1
            kind: Namespace
            metadata:
              name: {namespace}
              labels:
                app.kubernetes.io/name: {name}
            """,
            namespace=namespace,
            name=name,
        ),
        "serviceaccount.yaml": serviceaccount,
        "deployment.yaml": "\n".join(deployment_lines) + "\n",
        "service.yaml": render_template(
            """
            apiVersion: v1
            kind: Service
            metadata:
              name: {name}
              namespace: {namespace}
              labels:
                app.kubernetes.io/name: {name}
            spec:
              type: ClusterIP
              selector:
                app.kubernetes.io/name: {name}
              ports:
                - name: http
                  port: {service_port}
                  targetPort: http
            """,
            name=name,
            namespace=namespace,
            service_port=str(template.service_port),
        ),
        "ingress.yaml": render_template(
            """
            apiVersion: networking.k8s.io/v1
            kind: Ingress
            metadata:
              name: {name}
              namespace: {namespace}
              labels:
                app.kubernetes.io/name: {name}
              annotations:
                traefik.ingress.kubernetes.io/router.entrypoints: web
            spec:
              ingressClassName: traefik
              rules:
                - host: {dev_host}
                  http:
                    paths:
                      - path: /
                        pathType: Prefix
                        backend:
                          service:
                            name: {name}
                            port:
                              number: {service_port}
            """,
            name=name,
            namespace=namespace,
            dev_host=dev_host,
            service_port=str(template.service_port),
        ),
        "networkpolicy-default-deny.yaml": render_template(
            """
            apiVersion: networking.k8s.io/v1
            kind: NetworkPolicy
            metadata:
              name: default-deny
              namespace: {namespace}
            spec:
              podSelector: {{}}
              policyTypes:
                - Ingress
                - Egress
            """,
            namespace=namespace,
        ),
        "networkpolicy-allow-dns-egress.yaml": render_template(
            """
            apiVersion: networking.k8s.io/v1
            kind: NetworkPolicy
            metadata:
              name: allow-dns-egress
              namespace: {namespace}
            spec:
              podSelector: {{}}
              policyTypes:
                - Egress
              egress:
                - to:
                    - namespaceSelector:
                        matchLabels:
                          kubernetes.io/metadata.name: kube-system
                  ports:
                    - protocol: UDP
                      port: 53
                    - protocol: TCP
                      port: 53
            """,
            namespace=namespace,
        ),
        "networkpolicy-allow-ingress.yaml": render_template(
            """
            apiVersion: networking.k8s.io/v1
            kind: NetworkPolicy
            metadata:
              name: allow-ingress-from-traefik
              namespace: {namespace}
            spec:
              podSelector:
                matchLabels:
                  app.kubernetes.io/name: {name}
              policyTypes:
                - Ingress
              ingress:
                - from:
                    - namespaceSelector:
                        matchLabels:
                          kubernetes.io/metadata.name: kube-system
                  ports:
                    - protocol: TCP
                      port: {container_port}
            """,
            namespace=namespace,
            name=name,
            container_port=str(template.container_port),
        ),
    }


def gitops_overlay_files(
    *,
    name: str,
    namespace: str,
    image_repo: str,
    env_name: str,
    container_name: str,
    image_tag: str,
    replicas: int,
    cpu_request: str,
    memory_request: str,
    cpu_limit: str,
    memory_limit: str,
    prod_host: str,
) -> dict[str, str]:
    files = {
        "kustomization.yaml": render_template(
            """
            apiVersion: kustomize.config.k8s.io/v1beta1
            kind: Kustomization
            resources:
              - ../../base
            commonLabels:
              homelab.env: {env_name}
            patches:
              - path: patch-deployment.yaml
            """,
            env_name=env_name,
        ),
        "patch-deployment.yaml": render_template(
            """
            apiVersion: apps/v1
            kind: Deployment
            metadata:
              name: {name}
              namespace: {namespace}
            spec:
              replicas: {replicas}
              template:
                spec:
                  containers:
                    - name: {container_name}
                      image: {image_repo}:{image_tag}
                      env:
                        - name: APP_ENV
                          value: {env_name}
                      resources:
                        requests:
                          cpu: {cpu_request}
                          memory: {memory_request}
                        limits:
                          cpu: {cpu_limit}
                          memory: {memory_limit}
            """,
            name=name,
            namespace=namespace,
            replicas=str(replicas),
            container_name=container_name,
            image_repo=image_repo,
            image_tag=image_tag,
            env_name=env_name,
            cpu_request=cpu_request,
            memory_request=memory_request,
            cpu_limit=cpu_limit,
            memory_limit=memory_limit,
        ),
    }

    if env_name == "prod":
        files["kustomization.yaml"] = render_template(
            """
            apiVersion: kustomize.config.k8s.io/v1beta1
            kind: Kustomization
            resources:
              - ../../base
            commonLabels:
              homelab.env: prod
            patches:
              - path: patch-deployment.yaml
              - path: patch-ingress.yaml
            """
        )
        files["patch-ingress.yaml"] = render_template(
            """
            apiVersion: networking.k8s.io/v1
            kind: Ingress
            metadata:
              name: {name}
              namespace: {namespace}
            spec:
              rules:
                - host: {prod_host}
            """,
            name=name,
            namespace=namespace,
            prod_host=prod_host,
        )

    return files


def gitops_application_manifest(
    *,
    app_name: str,
    project_name: str,
    path: str,
    namespace: str,
    repo_url: str,
    active_comment: str = "",
) -> str:
    prefix = ""
    if active_comment:
        prefix = active_comment.rstrip() + "\n"
    return prefix + render_template(
        """
        apiVersion: argoproj.io/v1alpha1
        kind: Application
        metadata:
          name: {app_name}
          namespace: argocd
        spec:
          project: {project_name}
          source:
            repoURL: {repo_url}
            targetRevision: main
            path: {path}
          destination:
            server: https://kubernetes.default.svc
            namespace: {namespace}
          syncPolicy:
            automated:
              prune: true
              selfHeal: true
            syncOptions:
              - CreateNamespace=true
        """,
        app_name=app_name,
        project_name=project_name,
        path=path,
        namespace=namespace,
        repo_url=repo_url,
    )


def gitops_appproject_manifest(name: str, namespace: str, description: str, repo_url: str) -> str:
    return render_template(
        """
        apiVersion: argoproj.io/v1alpha1
        kind: AppProject
        metadata:
          name: {name}
          namespace: argocd
        spec:
          description: {description}
          sourceRepos:
            - {repo_url}
          destinations:
            - namespace: {namespace}
              server: https://kubernetes.default.svc
          clusterResourceWhitelist:
            - group: ""
              kind: Namespace
        """,
        name=name,
        description=description,
        repo_url=repo_url,
        namespace=namespace,
    )


def repo_workflow(name: str, image_repo: str, template: str) -> str:
    if template == "python-fastapi":
        return render_template(
            """
            name: Build and Publish {name}

            on:
              pull_request:
              push:
                branches:
                  - main

            permissions:
              contents: read

            jobs:
              test:
                runs-on: ubuntu-latest
                steps:
                  - name: Checkout
                    uses: actions/checkout@v4

                  - name: Setup Python
                    uses: actions/setup-python@v5
                    with:
                      python-version: "3.11"

                  - name: Install dependencies
                    run: |
                      python -m pip install --upgrade pip
                      python -m pip install -e .[dev]

                  - name: Run tests
                    run: pytest

              build:
                runs-on: ubuntu-latest
                needs: test
                permissions:
                  contents: read
                  packages: write
                steps:
                  - name: Checkout
                    uses: actions/checkout@v4

                  - name: Set up Docker Buildx
                    uses: docker/setup-buildx-action@v3

                  - name: Build image
                    uses: docker/build-push-action@v6
                    with:
                      context: .
                      push: false
                      tags: local/{name}:ci-${{{{ github.sha }}}}

                  - name: Login to GHCR
                    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
                    uses: docker/login-action@v3
                    with:
                      registry: ghcr.io
                      username: ${{{{ github.actor }}}}
                      password: ${{{{ secrets.GITHUB_TOKEN }}}}

                  - name: Publish image
                    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
                    uses: docker/build-push-action@v6
                    with:
                      context: .
                      push: true
                      tags: {image_repo}:sha-${{{{ github.sha }}}}
            """,
            name=name,
            image_repo=image_repo,
        )

    return render_template(
        """
        name: Build and Publish {name}

        on:
          pull_request:
          push:
            branches:
              - main

        permissions:
          contents: read

        jobs:
          test:
            runs-on: ubuntu-latest
            steps:
              - name: Checkout
                uses: actions/checkout@v4

              - name: Validate static assets
                run: |
                  test -f site/index.html
                  test -f nginx.conf

          build:
            runs-on: ubuntu-latest
            needs: test
            permissions:
              contents: read
              packages: write
            steps:
              - name: Checkout
                uses: actions/checkout@v4

              - name: Set up Docker Buildx
                uses: docker/setup-buildx-action@v3

              - name: Build image
                uses: docker/build-push-action@v6
                with:
                  context: .
                  push: false
                  tags: local/{name}:ci-${{{{ github.sha }}}}

              - name: Login to GHCR
                if: github.event_name == 'push' && github.ref == 'refs/heads/main'
                uses: docker/login-action@v3
                with:
                  registry: ghcr.io
                  username: ${{{{ github.actor }}}}
                  password: ${{{{ secrets.GITHUB_TOKEN }}}}

              - name: Publish image
                if: github.event_name == 'push' && github.ref == 'refs/heads/main'
                uses: docker/build-push-action@v6
                with:
                  context: .
                  push: true
                  tags: {image_repo}:sha-${{{{ github.sha }}}}
        """,
        name=name,
        image_repo=image_repo,
    )


def scaffold_repo(args: argparse.Namespace, template: TemplateSpec, repo_output_dir: Path) -> None:
    files = build_python_fastapi_repo_files(args.name, args.description, args.image_repo)
    if template.key == "static-nginx":
        files = build_static_nginx_repo_files(args.name, args.description, args.image_repo)

    files[f".github/workflows/build-{args.name}.yml"] = repo_workflow(args.name, args.image_repo, template.key)

    for relative_path, content in files.items():
        write_file(repo_output_dir / relative_path, content)


def scaffold_gitops(args: argparse.Namespace, template: TemplateSpec, gitops_root: Path, namespace: str, dev_host: str, prod_host: str) -> None:
    app_root = gitops_root / "apps" / args.name
    ensure_absent(app_root, "service manifest directory")

    base_files = gitops_base_files(
        name=args.name,
        namespace=namespace,
        image_repo=args.image_repo,
        template=template,
        base_tag=args.dev_tag,
        description=args.description,
        image_pull_secret=args.image_pull_secret,
        dev_host=dev_host,
    )
    for relative_path, content in base_files.items():
        write_file(app_root / "base" / relative_path, content)

    container_name = template.container_name
    dev_overlay = gitops_overlay_files(
        name=args.name,
        namespace=namespace,
        image_repo=args.image_repo,
        env_name="dev",
        container_name=container_name,
        image_tag=args.dev_tag,
        replicas=args.dev_replicas,
        cpu_request="50m",
        memory_request="64Mi",
        cpu_limit="300m",
        memory_limit="256Mi",
        prod_host=prod_host,
    )
    for relative_path, content in dev_overlay.items():
        write_file(app_root / "envs" / "dev" / relative_path, content)

    prod_overlay = gitops_overlay_files(
        name=args.name,
        namespace=namespace,
        image_repo=args.image_repo,
        env_name="prod",
        container_name=container_name,
        image_tag=args.prod_tag,
        replicas=args.prod_replicas,
        cpu_request="100m",
        memory_request="128Mi",
        cpu_limit="500m",
        memory_limit="512Mi",
        prod_host=prod_host,
    )
    for relative_path, content in prod_overlay.items():
        write_file(app_root / "envs" / "prod" / relative_path, content)

    repo_url = "https://github.com/wlodzimierrr/homelab-workloads.git"
    write_file(
        gitops_root / "environments" / "dev" / "workloads" / f"{args.name}-app.yaml",
        gitops_application_manifest(
            app_name=f"{args.name}-dev",
            project_name=args.name,
            path=f"apps/{args.name}/envs/dev",
            namespace=namespace,
            repo_url=repo_url,
        ),
    )
    write_file(
        gitops_root / "environments" / "prod" / "workloads" / f"{args.name}-app.yaml",
        gitops_application_manifest(
            app_name=f"{args.name}-prod",
            project_name=args.name,
            path=f"apps/{args.name}/envs/prod",
            namespace=namespace,
            repo_url=repo_url,
            active_comment=(
                "# Generated for future prod activation.\n"
                "# Keep environments/prod/workloads/kustomization.yaml empty while single-cluster safety mode is active."
            ),
        ),
    )
    append_unique_resource(
        gitops_root / "environments" / "dev" / "workloads" / "kustomization.yaml",
        f"{args.name}-app.yaml",
    )
    append_appproject(
        gitops_root / "bootstrap" / "project-homelab.yaml",
        gitops_appproject_manifest(
            name=args.name,
            namespace=namespace,
            description=f"{args.description} resources in {namespace} namespace only",
            repo_url=repo_url,
        ),
        project_name=args.name,
    )
    append_service_catalog_entry(
        gitops_root / "services.yaml",
        service_id=args.name,
        display_name=args.name,
        owner=args.owner or args.owner_email,
        owner_email=args.owner_email,
        repo_url=args.repo_url,
        runbook_url=args.runbook_url or args.repo_url,
        description=args.description,
        namespace=namespace,
        observability_mode=args.observability_mode or template.default_observability_mode,
    )


def main() -> None:
    args = parse_args()
    validate_service_name(args.name)

    base_template = TEMPLATES[args.template]
    template = TemplateSpec(
        key=base_template.key,
        display_name=base_template.display_name,
        container_port=args.container_port or base_template.container_port,
        service_port=args.service_port or base_template.service_port,
        health_path=args.health_path or base_template.health_path,
        readiness_path=args.readiness_path or base_template.readiness_path,
        container_name=base_template.container_name,
        default_observability_mode=base_template.default_observability_mode,
        repo_files=base_template.repo_files,
    )
    namespace = args.namespace or args.name
    dev_host = args.dev_host or f"{args.name}.dev.homelab.local"
    prod_host = args.prod_host or f"{args.name}.homelab.local"
    gitops_root = Path(args.gitops_root).resolve()
    repo_output_dir = Path(args.repo_output_dir).resolve() if args.repo_output_dir else Path(f"/tmp/{args.name}-repo")

    ensure_gitops_root(gitops_root)
    ensure_repo_output_dir(repo_output_dir, args.force)

    scaffold_repo(args, template, repo_output_dir)
    scaffold_gitops(args, template, gitops_root, namespace, dev_host, prod_host)

    print(f"Generated service repo: {repo_output_dir}")
    print(f"Generated GitOps manifests under: {gitops_root / 'apps' / args.name}")
    print(f"Dev app manifest: {gitops_root / 'environments' / 'dev' / 'workloads' / f'{args.name}-app.yaml'}")
    print(f"Prod app manifest (not auto-enabled in single-cluster mode): {gitops_root / 'environments' / 'prod' / 'workloads' / f'{args.name}-app.yaml'}")
    print(f"Catalog metadata entry: {gitops_root / 'services.yaml'}")
    print("Next steps:")
    print(f"  1. Review the generated repo files in {repo_output_dir}")
    print(f"  2. Run ./scripts/render-kustomize.sh {gitops_root / 'apps' / args.name / 'envs' / 'dev'}")
    print(
        f"  3. Open a PR in the workloads repo with apps/{args.name}, bootstrap/project-homelab.yaml, services.yaml, and environments/dev/workloads/{args.name}-app.yaml"
    )
    print("  4. Replace the default runbook URL in services.yaml if this service needs a dedicated runbook.")
    print("  5. Keep environments/prod/workloads/kustomization.yaml unchanged until a dedicated prod target exists.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
