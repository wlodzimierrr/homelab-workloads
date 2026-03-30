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

            CI publishes `sha-<commit>` and `latest` tags to `{image_repo}` on pushes to `main`.
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


def build_python_django_repo_files(name: str, description: str, image_repo: str) -> dict[str, str]:
    module_name = name.replace("-", "_")
    return {
        ".gitignore": dedent(
            """
            __pycache__/
            *.pyc
            .pytest_cache/
            .venv/
            dist/
            build/
            db.sqlite3
            staticfiles/
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
            python manage.py runserver 0.0.0.0:8000
            ```

            ## Tests

            ```bash
            pytest
            ```

            ## Image

            CI publishes `sha-<commit>` and `latest` tags to `{image_repo}` on pushes to `main`.
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
              "django>=5.1,<6.0",
              "gunicorn>=23.0,<24.0",
            ]

            [project.optional-dependencies]
            dev = [
              "pytest>=8.4,<9.0",
              "pytest-django>=4.9,<5.0",
            ]

            [tool.setuptools.packages.find]
            include = ["{module_name}*"]

            [tool.pytest.ini_options]
            DJANGO_SETTINGS_MODULE = "{module_name}.settings"
            """,
            name=name,
            description=description,
            module_name=module_name,
        ),
        "manage.py": render_template(
            """
            #!/usr/bin/env python
            import os
            import sys

            def main():
                os.environ.setdefault("DJANGO_SETTINGS_MODULE", "{module_name}.settings")
                from django.core.management import execute_from_command_line
                execute_from_command_line(sys.argv)

            if __name__ == "__main__":
                main()
            """,
            module_name=module_name,
        ),
        f"{module_name}/__init__.py": "",
        f"{module_name}/settings.py": render_template(
            """
            import os
            from pathlib import Path

            BASE_DIR = Path(__file__).resolve().parent.parent
            SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "change-me-in-production")
            DEBUG = os.getenv("DJANGO_DEBUG", "false").lower() in ("1", "true")
            ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "*").split(",")
            ROOT_URLCONF = "{module_name}.urls"
            INSTALLED_APPS = [
                "django.contrib.contenttypes",
                "django.contrib.auth",
            ]
            MIDDLEWARE = [
                "django.middleware.security.SecurityMiddleware",
                "django.middleware.common.CommonMiddleware",
            ]
            DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
            """,
            module_name=module_name,
        ),
        f"{module_name}/urls.py": render_template(
            """
            from django.urls import path
            from {module_name} import views

            urlpatterns = [
                path("health/", views.health),
                path("", views.root),
            ]
            """,
            module_name=module_name,
        ),
        f"{module_name}/views.py": dedent(
            """
            from django.http import JsonResponse


            def health(request):
                return JsonResponse({"status": "ok"})


            def root(request):
                return JsonResponse({"service": "ready"})
            """
        ),
        f"{module_name}/wsgi.py": render_template(
            """
            import os
            from django.core.wsgi import get_wsgi_application

            os.environ.setdefault("DJANGO_SETTINGS_MODULE", "{module_name}.settings")
            application = get_wsgi_application()
            """,
            module_name=module_name,
        ),
        "tests/test_health.py": render_template(
            """
            import pytest
            from django.test import Client

            @pytest.mark.django_db(transaction=False)
            def test_health():
                client = Client()
                response = client.get("/health/")
                assert response.status_code == 200
                assert response.json() == {{"status": "ok"}}
            """,
        ),
        "Dockerfile": render_template(
            """
            FROM python:3.11-slim

            WORKDIR /app

            COPY pyproject.toml ./
            COPY {module_name} ./{module_name}
            COPY manage.py ./

            RUN pip install --no-cache-dir --upgrade pip \\
              && pip install --no-cache-dir .

            EXPOSE 8000

            CMD ["gunicorn", "{module_name}.wsgi:application", "--bind", "0.0.0.0:8000"]
            """,
            module_name=module_name,
        ),
    }


def build_python_flask_repo_files(name: str, description: str, image_repo: str) -> dict[str, str]:
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
            flask --app app.main run --host 0.0.0.0 --port 5000
            ```

            ## Tests

            ```bash
            pytest
            ```

            ## Image

            CI publishes `sha-<commit>` and `latest` tags to `{image_repo}` on pushes to `main`.
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
              "flask>=3.1,<4.0",
              "gunicorn>=23.0,<24.0",
            ]

            [project.optional-dependencies]
            dev = [
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
            from flask import Flask, jsonify


            def create_app():
                app = Flask(__name__)

                @app.get("/health")
                def health():
                    return jsonify(status="ok")

                @app.get("/")
                def root():
                    return jsonify(service="ready")

                return app


            app = create_app()
            """
        ),
        "tests/test_health.py": dedent(
            """
            from app.main import create_app


            def test_health():
                app = create_app()
                client = app.test_client()
                response = client.get("/health")
                assert response.status_code == 200
                assert response.get_json() == {"status": "ok"}
            """
        ),
        "Dockerfile": render_template(
            """
            FROM python:3.11-slim

            WORKDIR /app

            COPY pyproject.toml ./
            COPY app ./app

            RUN pip install --no-cache-dir --upgrade pip \\
              && pip install --no-cache-dir .

            EXPOSE 5000

            CMD ["gunicorn", "app.main:app", "--bind", "0.0.0.0:5000"]
            """,
        ),
    }


def build_node_express_repo_files(name: str, description: str, image_repo: str) -> dict[str, str]:
    return {
        ".gitignore": dedent(
            """
            node_modules/
            npm-debug.log*
            .env
            dist/
            """
        ),
        ".dockerignore": dedent(
            """
            .git
            .github
            node_modules
            npm-debug.log*
            """
        ),
        "README.md": render_template(
            """
            # {name}

            {description}

            ## Local Development

            ```bash
            npm install
            node src/index.js
            ```

            ## Tests

            ```bash
            npm test
            ```

            ## Image

            CI publishes `sha-<commit>` and `latest` tags to `{image_repo}` on pushes to `main`.
            """,
            name=name,
            description=description,
            image_repo=image_repo,
        ),
        "package.json": render_template(
            """
            {{
              "name": "{name}",
              "version": "0.1.0",
              "description": "{description}",
              "main": "src/index.js",
              "scripts": {{
                "start": "node src/index.js",
                "test": "node --test"
              }},
              "dependencies": {{
                "express": "^4.21.0",
                "prom-client": "^15.1.0"
              }}
            }}
            """,
            name=name,
            description=description,
        ),
        "src/index.js": dedent(
            """
            'use strict'

            const express = require('express')
            const { register, collectDefaultMetrics } = require('prom-client')

            collectDefaultMetrics()

            const app = express()
            const PORT = process.env.PORT || 3000

            app.get('/health', (_req, res) => {
              res.json({ status: 'ok' })
            })

            app.get('/metrics', async (_req, res) => {
              res.set('Content-Type', register.contentType)
              res.end(await register.metrics())
            })

            app.get('/', (_req, res) => {
              res.json({ service: 'ready' })
            })

            app.listen(PORT, '0.0.0.0', () => {
              console.log(`Server listening on port ${PORT}`)
            })
            """
        ),
        "src/index.test.js": dedent(
            """
            'use strict'

            const { describe, it, before, after } = require('node:test')
            const assert = require('node:assert/strict')
            const http = require('node:http')

            let server

            before(async () => {
              process.env.PORT = '0'
              const mod = require('./index')
              server = mod
            })

            after(() => {
              if (server && typeof server.close === 'function') server.close()
            })

            async function get(path) {
              return new Promise((resolve, reject) => {
                const port = server?.address?.()?.port || 3000
                http.get(`http://127.0.0.1:${port}${path}`, (res) => {
                  let body = ''
                  res.on('data', (chunk) => { body += chunk })
                  res.on('end', () => resolve({ status: res.statusCode, body }))
                }).on('error', reject)
              })
            }

            describe('health endpoint', () => {
              it('returns 200 ok', async () => {
                const { status, body } = await get('/health')
                assert.equal(status, 200)
                assert.deepEqual(JSON.parse(body), { status: 'ok' })
              })
            })
            """
        ),
        "Dockerfile": dedent(
            """
            FROM node:20-alpine AS deps
            WORKDIR /app
            COPY package*.json ./
            RUN npm ci --omit=dev

            FROM node:20-alpine
            WORKDIR /app
            COPY --from=deps /app/node_modules ./node_modules
            COPY src ./src
            COPY package.json ./
            EXPOSE 3000
            CMD ["node", "src/index.js"]
            """
        ),
    }


def build_node_nestjs_repo_files(name: str, description: str, image_repo: str) -> dict[str, str]:
    return {
        ".gitignore": dedent(
            """
            node_modules/
            npm-debug.log*
            .env
            dist/
            """
        ),
        ".dockerignore": dedent(
            """
            .git
            .github
            node_modules
            npm-debug.log*
            dist
            """
        ),
        "README.md": render_template(
            """
            # {name}

            {description}

            ## Local Development

            ```bash
            npm install
            npm run start:dev
            ```

            ## Tests

            ```bash
            npm test
            ```

            ## Image

            CI publishes `sha-<commit>` and `latest` tags to `{image_repo}` on pushes to `main`.
            """,
            name=name,
            description=description,
            image_repo=image_repo,
        ),
        "package.json": render_template(
            """
            {{
              "name": "{name}",
              "version": "0.1.0",
              "description": "{description}",
              "scripts": {{
                "build": "tsc",
                "start": "node dist/main.js",
                "start:dev": "ts-node src/main.ts",
                "test": "node --test dist/**/*.test.js"
              }},
              "dependencies": {{
                "@nestjs/common": "^10.4.0",
                "@nestjs/core": "^10.4.0",
                "@nestjs/platform-express": "^10.4.0",
                "reflect-metadata": "^0.2.2",
                "rxjs": "^7.8.1"
              }},
              "devDependencies": {{
                "typescript": "^5.5.0",
                "ts-node": "^10.9.0",
                "@types/node": "^20.14.0",
                "@types/express": "^4.17.0"
              }}
            }}
            """,
            name=name,
            description=description,
        ),
        "tsconfig.json": dedent(
            """
            {
              "compilerOptions": {
                "module": "commonjs",
                "target": "ES2021",
                "outDir": "./dist",
                "rootDir": "./src",
                "strict": true,
                "esModuleInterop": true,
                "emitDecoratorMetadata": true,
                "experimentalDecorators": true,
                "skipLibCheck": true,
                "declaration": true
              },
              "include": ["src/**/*"]
            }
            """
        ),
        "src/main.ts": dedent(
            """
            import { NestFactory } from '@nestjs/core'
            import { AppModule } from './app.module'

            async function bootstrap() {
              const app = await NestFactory.create(AppModule)
              await app.listen(process.env.PORT || 3000, '0.0.0.0')
            }
            bootstrap()
            """
        ),
        "src/app.module.ts": dedent(
            """
            import { Module } from '@nestjs/common'
            import { HealthController } from './health.controller'

            @Module({
              controllers: [HealthController],
            })
            export class AppModule {}
            """
        ),
        "src/health.controller.ts": dedent(
            """
            import { Controller, Get } from '@nestjs/common'

            @Controller()
            export class HealthController {
              @Get('health')
              health() {
                return { status: 'ok' }
              }

              @Get()
              root() {
                return { service: 'ready' }
              }
            }
            """
        ),
        "Dockerfile": dedent(
            """
            FROM node:20-alpine AS build
            WORKDIR /app
            COPY package*.json tsconfig.json ./
            RUN npm ci
            COPY src ./src
            RUN npm run build

            FROM node:20-alpine
            WORKDIR /app
            COPY --from=build /app/dist ./dist
            COPY --from=build /app/node_modules ./node_modules
            COPY package.json ./
            EXPOSE 3000
            CMD ["node", "dist/main.js"]
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

            CI publishes `sha-<commit>` and `latest` tags to `{image_repo}` on pushes to `main`.
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


def build_react_repo_files(name: str, description: str, image_repo: str) -> dict[str, str]:
    return {
        ".gitignore": dedent(
            """
            node_modules/
            dist/
            .DS_Store
            """
        ),
        ".dockerignore": dedent(
            """
            node_modules
            dist
            .git
            .github
            """
        ),
        "README.md": render_template(
            """
            # {name}

            {description}

            ## Development

            ```bash
            npm install
            npm run dev
            ```

            ## Production build

            ```bash
            docker build -t {name}:local .
            docker run --rm -p 8080:80 {name}:local
            ```

            ## Image

            CI publishes `sha-<commit>` and `latest` tags to `{image_repo}` on pushes to `main`.
            """,
            name=name,
            description=description,
            image_repo=image_repo,
        ),
        "package.json": render_template(
            """
            {{
              "name": "{name}",
              "private": true,
              "version": "0.1.0",
              "type": "module",
              "scripts": {{
                "dev": "vite",
                "build": "vite build",
                "preview": "vite preview",
                "test": "echo \\"no tests yet\\" && exit 0"
              }},
              "dependencies": {{
                "react": "^18.3.1",
                "react-dom": "^18.3.1"
              }},
              "devDependencies": {{
                "@types/react": "^18.3.3",
                "@types/react-dom": "^18.3.0",
                "@vitejs/plugin-react": "^4.3.1",
                "vite": "^5.4.2"
              }}
            }}
            """,
            name=name,
        ),
        "vite.config.ts": dedent(
            """
            import { defineConfig } from 'vite'
            import react from '@vitejs/plugin-react'

            export default defineConfig({
              plugins: [react()],
            })
            """
        ),
        "index.html": render_template(
            """
            <!doctype html>
            <html lang="en">
              <head>
                <meta charset="utf-8" />
                <meta name="viewport" content="width=device-width, initial-scale=1" />
                <title>{name}</title>
              </head>
              <body>
                <div id="root"></div>
                <script type="module" src="/src/main.tsx"></script>
              </body>
            </html>
            """,
            name=name,
        ),
        "src/main.tsx": dedent(
            """
            import React from 'react'
            import ReactDOM from 'react-dom/client'
            import App from './App'

            ReactDOM.createRoot(document.getElementById('root')!).render(
              <React.StrictMode>
                <App />
              </React.StrictMode>,
            )
            """
        ),
        "src/App.tsx": render_template(
            """
            function App() {{
              return (
                <main style={{{{ fontFamily: 'system-ui, sans-serif', padding: '2rem' }}}}>
                  <h1>{name}</h1>
                  <p>{description}</p>
                </main>
              )
            }}

            export default App
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
            FROM node:20-alpine AS build
            WORKDIR /app
            COPY package.json package-lock.json* ./
            RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi
            COPY . .
            RUN npm run build

            FROM nginx:1.27-alpine
            COPY nginx.conf /etc/nginx/conf.d/default.conf
            COPY --from=build /app/dist /usr/share/nginx/html
            """
        ),
    }


def build_nextjs_repo_files(name: str, description: str, image_repo: str) -> dict[str, str]:
    return {
        ".gitignore": dedent(
            """
            node_modules/
            .next/
            out/
            .DS_Store
            """
        ),
        ".dockerignore": dedent(
            """
            node_modules
            .next
            out
            .git
            .github
            """
        ),
        "README.md": render_template(
            """
            # {name}

            {description}

            ## Development

            ```bash
            npm install
            npm run dev
            ```

            ## Production build

            ```bash
            docker build -t {name}:local .
            docker run --rm -p 3000:3000 {name}:local
            ```

            ## Image

            CI publishes `sha-<commit>` and `latest` tags to `{image_repo}` on pushes to `main`.
            """,
            name=name,
            description=description,
            image_repo=image_repo,
        ),
        "package.json": render_template(
            """
            {{
              "name": "{name}",
              "private": true,
              "version": "0.1.0",
              "scripts": {{
                "dev": "next dev",
                "build": "next build",
                "start": "next start",
                "test": "echo \\"no tests yet\\" && exit 0"
              }},
              "dependencies": {{
                "next": "^14.2.5",
                "react": "^18.3.1",
                "react-dom": "^18.3.1"
              }},
              "devDependencies": {{
                "@types/node": "^20.14.10",
                "@types/react": "^18.3.3",
                "@types/react-dom": "^18.3.0",
                "typescript": "^5.5.3"
              }}
            }}
            """,
            name=name,
        ),
        "tsconfig.json": dedent(
            """
            {
              "compilerOptions": {
                "target": "es5",
                "lib": ["dom", "dom.iterable", "esnext"],
                "allowJs": true,
                "skipLibCheck": true,
                "strict": true,
                "noEmit": true,
                "esModuleInterop": true,
                "module": "esnext",
                "moduleResolution": "bundler",
                "resolveJsonModule": true,
                "isolatedModules": true,
                "jsx": "preserve",
                "incremental": true,
                "plugins": [{ "name": "next" }],
                "paths": { "@/*": ["./src/*"] }
              },
              "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx"],
              "exclude": ["node_modules"]
            }
            """
        ),
        "next.config.js": dedent(
            """
            /** @type {import('next').NextConfig} */
            const nextConfig = {
              output: 'standalone',
            }

            module.exports = nextConfig
            """
        ),
        "src/app/layout.tsx": render_template(
            """
            export const metadata = {{
              title: '{name}',
              description: '{description}',
            }}

            export default function RootLayout({{ children }}: {{ children: React.ReactNode }}) {{
              return (
                <html lang="en">
                  <body>{{children}}</body>
                </html>
              )
            }}
            """,
            name=name,
            description=description,
        ),
        "src/app/page.tsx": render_template(
            """
            export default function Home() {{
              return (
                <main style={{{{ fontFamily: 'system-ui, sans-serif', padding: '2rem' }}}}>
                  <h1>{name}</h1>
                  <p>{description}</p>
                </main>
              )
            }}
            """,
            name=name,
            description=description,
        ),
        "src/app/api/health/route.ts": dedent(
            """
            import { NextResponse } from 'next/server'

            export function GET() {
              return NextResponse.json({ status: 'ok' })
            }
            """
        ),
        "Dockerfile": dedent(
            """
            FROM node:20-alpine AS deps
            WORKDIR /app
            COPY package.json package-lock.json* ./
            RUN npm ci

            FROM node:20-alpine AS build
            WORKDIR /app
            COPY --from=deps /app/node_modules ./node_modules
            COPY . .
            RUN npm run build

            FROM node:20-alpine AS runner
            WORKDIR /app
            ENV NODE_ENV=production
            COPY --from=build /app/public ./public
            COPY --from=build /app/.next/standalone ./
            COPY --from=build /app/.next/static ./.next/static
            EXPOSE 3000
            CMD ["node", "server.js"]
            """
        ),
    }


def build_vue_repo_files(name: str, description: str, image_repo: str) -> dict[str, str]:
    return {
        ".gitignore": dedent(
            """
            node_modules/
            dist/
            .DS_Store
            """
        ),
        ".dockerignore": dedent(
            """
            node_modules
            dist
            .git
            .github
            """
        ),
        "README.md": render_template(
            """
            # {name}

            {description}

            ## Development

            ```bash
            npm install
            npm run dev
            ```

            ## Production build

            ```bash
            docker build -t {name}:local .
            docker run --rm -p 8080:80 {name}:local
            ```

            ## Image

            CI publishes `sha-<commit>` and `latest` tags to `{image_repo}` on pushes to `main`.
            """,
            name=name,
            description=description,
            image_repo=image_repo,
        ),
        "package.json": render_template(
            """
            {{
              "name": "{name}",
              "private": true,
              "version": "0.1.0",
              "type": "module",
              "scripts": {{
                "dev": "vite",
                "build": "vite build",
                "preview": "vite preview",
                "test": "echo \"no tests yet\" && exit 0"
              }},
              "dependencies": {{
                "vue": "^3.5.13"
              }},
              "devDependencies": {{
                "@vitejs/plugin-vue": "^5.1.4",
                "vite": "^5.4.2"
              }}
            }}
            """,
            name=name,
        ),
        "vite.config.ts": dedent(
            """
            import { defineConfig } from 'vite'
            import vue from '@vitejs/plugin-vue'

            export default defineConfig({
              plugins: [vue()],
            })
            """
        ),
        "index.html": render_template(
            """
            <!doctype html>
            <html lang="en">
              <head>
                <meta charset="utf-8" />
                <meta name="viewport" content="width=device-width, initial-scale=1" />
                <title>{name}</title>
              </head>
              <body>
                <div id="app"></div>
                <script type="module" src="/src/main.js"></script>
              </body>
            </html>
            """,
            name=name,
        ),
        "src/main.js": dedent(
            """
            import { createApp } from 'vue'
            import App from './App.vue'

            createApp(App).mount('#app')
            """
        ),
        "src/App.vue": render_template(
            """
            <template>
              <main class="app-shell">
                <h1>{name}</h1>
                <p>{description}</p>
              </main>
            </template>

            <style scoped>
            .app-shell {{
              font-family: system-ui, sans-serif;
              padding: 2rem;
            }}
            </style>
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
            FROM node:20-alpine AS build
            WORKDIR /app
            COPY package.json package-lock.json* ./
            RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi
            COPY . .
            RUN npm run build

            FROM nginx:1.27-alpine
            COPY nginx.conf /etc/nginx/conf.d/default.conf
            COPY --from=build /app/dist /usr/share/nginx/html
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
    "python-django": TemplateSpec(
        key="python-django",
        display_name="Python + Django",
        container_port=8000,
        service_port=80,
        health_path="/health/",
        readiness_path="/health/",
        container_name="app",
        default_observability_mode="app-native",
        repo_files={},
    ),
    "python-flask": TemplateSpec(
        key="python-flask",
        display_name="Python + Flask",
        container_port=5000,
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
    "react": TemplateSpec(
        key="react",
        display_name="React (Vite)",
        container_port=80,
        service_port=80,
        health_path="/health",
        readiness_path="/health",
        container_name="web",
        default_observability_mode="ingress-derived",
        repo_files={},
    ),
    "nextjs": TemplateSpec(
        key="nextjs",
        display_name="Next.js",
        container_port=3000,
        service_port=80,
        health_path="/api/health",
        readiness_path="/api/health",
        container_name="web",
        default_observability_mode="app-native",
        repo_files={},
    ),
    "vue": TemplateSpec(
        key="vue",
        display_name="Vue",
        container_port=80,
        service_port=80,
        health_path="/",
        readiness_path="/",
        container_name="web",
        default_observability_mode="ingress-derived",
        repo_files={},
    ),
    "wordpress": TemplateSpec(
        key="wordpress",
        display_name="WordPress",
        container_port=80,
        service_port=80,
        health_path="/wp-login.php",
        readiness_path="/wp-login.php",
        container_name="web",
        default_observability_mode="ingress-derived",
        repo_files={},
    ),
    "node-express": TemplateSpec(
        key="node-express",
        display_name="Express.js",
        container_port=3000,
        service_port=80,
        health_path="/health",
        readiness_path="/health",
        container_name="app",
        default_observability_mode="app-native",
        repo_files={},
    ),
    "node-nestjs": TemplateSpec(
        key="node-nestjs",
        display_name="NestJS",
        container_port=3000,
        service_port=80,
        health_path="/health",
        readiness_path="/health",
        container_name="app",
        default_observability_mode="app-native",
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
    parser.add_argument("--dev-tag", default="latest", help="Initial dev image tag")
    parser.add_argument("--prod-tag", default="latest", help="Initial prod image tag")
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
    parser.add_argument(
        "--add-on",
        choices=("database",),
        default="",
        help="Optional service add-on to scaffold",
    )
    parser.add_argument(
        "--db-engine",
        choices=("postgres", "mysql"),
        default="postgres",
        help="Database engine for the database add-on (postgres or mysql)",
    )
    parser.add_argument(
        "--migration-command",
        default="",
        help="Optional database migration command; for postgres defaults to 'alembic upgrade head', for mysql skipped unless provided",
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
    public_host: str = "",
) -> None:
    if catalog_path.exists():
        existing = catalog_path.read_text(encoding="utf-8")
    else:
        existing = "services:\n"

    if f"service_id: {service_id}\n" in existing:
        raise SystemExit(f"service catalog entry already exists in {catalog_path}: {service_id}")
    if "services:" not in existing:
        raise SystemExit(f"expected top-level services: list in {catalog_path}")

    prod_public_host_line = f"        public_host: {yaml_string(public_host)}\n" if public_host else ""
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
        f"{prod_public_host_line}"
    )
    suffix = "" if existing.endswith("\n") else "\n"
    catalog_path.write_text(existing + suffix + entry, encoding="utf-8")


def gitops_database_files(
    *,
    name: str,
    namespace: str,
    db_engine: str,
    image_repo: str,
    base_tag: str,
    migration_command: str = "",
) -> dict[str, str]:
    """Generate database add-on manifests for the service."""
    base_image_pull_policy = "Always" if base_tag == "latest" else "IfNotPresent"
    db_name = f"{name}-{db_engine}"
    db_service_name = f"{db_name}"
    db_port = 5432 if db_engine == "postgres" else 3306
    db_container_port_str = str(db_port)
    db_image = "postgres:17.6" if db_engine == "postgres" else "mysql:8.0"

    files: dict[str, str] = {}

    # Database Secret template (SOPS-encrypted stub)
    if db_engine == "postgres":
        files[f"{db_name}-secret.env.example"] = dedent(
            """
            # SOPS-encrypted secret stub for {db_name}
            # Fill in the placeholder values, then encrypt with:
            #   sops -e {db_name}-secret.env > {db_name}-secret.enc.env
            # See docs/runbooks/sops-secrets.md for the full SOPS setup.
            POSTGRES_USER=appuser
            POSTGRES_PASSWORD=changeme
            POSTGRES_DB={name}_db
            """,
        ).format(db_name=db_name, name=name)
        files[f"{db_name}-secret.enc.yaml"] = dedent(
            """
            # SOPS-encrypted Secret stub
            # Populate this with encrypted credentials; see {db_name}-secret.env.example
            apiVersion: v1
            kind: Secret
            metadata:
              name: {db_name}
              namespace: {namespace}
            type: Opaque
            stringData:
              POSTGRES_USER: ENC[AES256_GCM,data:xxx,iv:xxx,tag:xxx,type:str]
              POSTGRES_PASSWORD: ENC[AES256_GCM,data:xxx,iv:xxx,tag:xxx,type:str]
              POSTGRES_DB: ENC[AES256_GCM,data:xxx,iv:xxx,tag:xxx,type:str]
            sops:
              kms: []
              gcp_kms: []
              azure_kv: []
              hc_vault: []
              age:
                - recipient: age1xxx
                  enc: |
                    -----BEGIN AGE ENCRYPTED FILE-----
                    ...
                    -----END AGE ENCRYPTED FILE-----
              lastmodified: "2026-03-12T00:00:00Z"
              mac: ENC[AES256_GCM,data:xxx,iv:xxx,tag:xxx,type:str]
              pgp: []
              encrypted_regex: ^(stringData|data)$
              version: 3.8.1
            """,
        ).format(db_name=db_name,namespace=namespace)
    else:  # mysql
        files[f"{db_name}-secret.env.example"] = dedent(
            """
            # SOPS-encrypted secret stub for {db_name}
            # Fill in the placeholder values, then encrypt with:
            #   sops -e {db_name}-secret.env > {db_name}-secret.enc.env
            # See docs/runbooks/sops-secrets.md for the full SOPS setup.
            MYSQL_ROOT_PASSWORD=changeme
            MYSQL_USER=appuser
            MYSQL_PASSWORD=changeme
            MYSQL_DATABASE={name}_db
            """,
        ).format(db_name=db_name, name=name)
        files[f"{db_name}-secret.enc.yaml"] = dedent(
            """
            # SOPS-encrypted Secret stub
            # Populate this with encrypted credentials; see {db_name}-secret.env.example
            apiVersion: v1
            kind: Secret
            metadata:
              name: {db_name}
              namespace: {namespace}
            type: Opaque
            stringData:
              MYSQL_ROOT_PASSWORD: ENC[AES256_GCM,data:xxx,iv:xxx,tag:xxx,type:str]
              MYSQL_USER: ENC[AES256_GCM,data:xxx,iv:xxx,tag:xxx,type:str]
              MYSQL_PASSWORD: ENC[AES256_GCM,data:xxx,iv:xxx,tag:xxx,type:str]
              MYSQL_DATABASE: ENC[AES256_GCM,data:xxx,iv:xxx,tag:xxx,type:str]
            sops:
              kms: []
              gcp_kms: []
              azure_kv: []
              hc_vault: []
              age:
                - recipient: age1xxx
                  enc: |
                    -----BEGIN AGE ENCRYPTED FILE-----
                    ...
                    -----END AGE ENCRYPTED FILE-----
              lastmodified: "2026-03-12T00:00:00Z"
              mac: ENC[AES256_GCM,data:xxx,iv:xxx,tag:xxx,type:str]
              pgp: []
              encrypted_regex: ^(stringData|data)$
              version: 3.8.1
            """,
        ).format(db_name=db_name, namespace=namespace)

    # Database Service
    files[f"{db_service_name}-service.yaml"] = render_template(
        """
        apiVersion: v1
        kind: Service
        metadata:
          name: {db_service_name}
          namespace: {namespace}
          labels:
            app.kubernetes.io/name: {name}
            app.kubernetes.io/component: {db_engine}
        spec:
          clusterIP: None
          selector:
            app.kubernetes.io/name: {name}
            app.kubernetes.io/component: {db_engine}
          ports:
            - name: {db_engine}
              port: {db_port}
              targetPort: {db_engine}
        """,
        db_service_name=db_service_name,
        namespace=namespace,
        name=name,
        db_engine=db_engine,
        db_port=db_container_port_str,
    )

    # Database StatefulSet
    if db_engine == "postgres":
        startup_probe = dedent(
            """
            startupProbe:
              exec:
                command:
                  - /bin/sh
                  - -c
                  - pg_isready -h 127.0.0.1 -p 5432 -U "$POSTGRES_USER" -d "$POSTGRES_DB"
              periodSeconds: 2
              timeoutSeconds: 2
              failureThreshold: 30
            readinessProbe:
              exec:
                command:
                  - /bin/sh
                  - -c
                  - pg_isready -h 127.0.0.1 -p 5432 -U "$POSTGRES_USER" -d "$POSTGRES_DB"
              periodSeconds: 5
              timeoutSeconds: 3
              failureThreshold: 6
            """
        )
    else:  # mysql
        startup_probe = dedent(
            """
            startupProbe:
              exec:
                command:
                  - mysqladmin
                  - ping
                  - -h
                  - 127.0.0.1
              periodSeconds: 2
              timeoutSeconds: 2
              failureThreshold: 30
            readinessProbe:
              exec:
                command:
                  - mysqladmin
                  - ping
                  - -h
                  - 127.0.0.1
              periodSeconds: 5
              timeoutSeconds: 3
              failureThreshold: 6
            """
        )

    mount_dir = "/var/lib/postgresql/data" if db_engine == "postgres" else "/var/lib/mysql"
    
    files[f"{db_name}-statefulset.yaml"] = f"""apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: {db_name}
  namespace: {namespace}
  labels:
    app.kubernetes.io/name: {name}
    app.kubernetes.io/component: {db_engine}
spec:
  serviceName: {db_service_name}
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: {name}
      app.kubernetes.io/component: {db_engine}
  template:
    metadata:
      labels:
        app.kubernetes.io/name: {name}
        app.kubernetes.io/component: {db_engine}
    spec:
      containers:
        - name: {db_engine}
          image: {db_image}
          imagePullPolicy: IfNotPresent
          ports:
            - name: {db_engine}
              containerPort: {db_port}
          envFrom:
            - secretRef:
                name: {db_name}
{indent_block(startup_probe.rstrip(), 10)}
          volumeMounts:
            - name: {db_engine}-data
              mountPath: {mount_dir}
          resources:
            requests:
              cpu: 100m
              memory: 256Mi
            limits:
              cpu: 500m
              memory: 512Mi
  volumeClaimTemplates:
    - metadata:
        name: {db_engine}-data
      spec:
        accessModes:
          - ReadWriteOnce
        resources:
          requests:
            storage: 10Gi
"""

    # NetworkPolicy allowing app to reach database
    files[f"networkpolicy-allow-{db_engine}-egress.yaml"] = render_template(
        """
        apiVersion: networking.k8s.io/v1
        kind: NetworkPolicy
        metadata:
          name: allow-{db_engine}-egress
          namespace: {namespace}
        spec:
          podSelector:
            matchLabels:
              app.kubernetes.io/name: {name}
              app.kubernetes.io/component: app
          policyTypes:
            - Egress
          egress:
            - to:
                - podSelector:
                    matchLabels:
                      app.kubernetes.io/name:  {name}
                      app.kubernetes.io/component: {db_engine}
              ports:
                - protocol: TCP
                  port: {db_port}
        """,
        db_engine=db_engine,
        namespace=namespace,
        name=name,
        db_port=db_container_port_str,
    )

    # NetworkPolicy allowing database to receive from app
    files[f"networkpolicy-allow-{db_engine}-ingress.yaml"] = render_template(
        """
        apiVersion: networking.k8s.io/v1
        kind: NetworkPolicy
        metadata:
          name: allow-{db_engine}-ingress
          namespace: {namespace}
        spec:
          podSelector:
            matchLabels:
              app.kubernetes.io/name: {name}
              app.kubernetes.io/component: {db_engine}
          policyTypes:
            - Ingress
          ingress:
            - from:
                - podSelector:
                    matchLabels:
                      app.kubernetes.io/name: {name}
                      app.kubernetes.io/component: app
              ports:
                - protocol: TCP
                  port: {db_port}
        """,
        db_engine=db_engine,
        namespace=namespace,
        name=name,
        db_port=db_container_port_str,
    )

    # Migration/Init job (optional, only if migration_command is provided or db_engine is postgres)
    if migration_command or db_engine == "postgres":
        migration_cmd = migration_command or "alembic upgrade head"
        if db_engine == "postgres":
            job_content = render_template(
                """
                apiVersion: batch/v1
                kind: Job
                metadata:
                  name: {name}-migrate
                  namespace: {namespace}
                  labels:
                    app.kubernetes.io/name: {name}
                    app.kubernetes.io/component: migration
                  annotations:
                    argocd.argoproj.io/hook: Sync
                    argocd.argoproj.io/hook-delete-policy: BeforeHookCreation
                spec:
                  backoffLimit: 3
                  activeDeadlineSeconds: 600
                  template:
                    metadata:
                      labels:
                        app.kubernetes.io/name: {name}
                        app.kubernetes.io/component: migration
                        homelab.io/db-client: "true"
                    spec:
                      serviceAccountName: {name}-backend
                      restartPolicy: OnFailure
                      containers:
                        - name: migrate
                          image: {image_repo}:{base_tag}
                          imagePullPolicy: {base_image_pull_policy}
                          command:
                            - /bin/sh
                            - -c
                            - |
                              set -eu
                              
                              # Wait until the Postgres service accepts TCP connections
                              python3 - <<'PY'
                              import socket
                              import time

                              host = "{db_service_name}"
                              port = 5432
                              for attempt in range(1, 61):
                                  try:
                                      with socket.create_connection((host, port), timeout=2):
                                          print(f"postgres reachable on attempt {{attempt}}")
                                          raise SystemExit(0)
                                  except OSError:
                                      time.sleep(2)
                              raise SystemExit("postgres not reachable after retries")
                              PY
                              
                              # Run migration command
                              {migration_cmd}
                          env:
                            - name: DATABASE_URL
                              valueFrom:
                                secretKeyRef:
                                  name: {db_name}
                                  key: DATABASE_URL
                """,
                name=name,
                namespace=namespace,
                image_repo=image_repo,
                base_tag=base_tag,
                base_image_pull_policy=base_image_pull_policy,
                db_service_name=db_service_name,
                migration_cmd=migration_cmd,
                db_name=db_name,
            )
        else:  # mysql
            job_content = render_template(
                """
                apiVersion: batch/v1
                kind: Job
                metadata:
                  name: {name}-init
                  namespace: {namespace}
                  labels:
                    app.kubernetes.io/name: {name}
                    app.kubernetes.io/component: init
                  annotations:
                    argocd.argoproj.io/hook: Sync
                    argocd.argoproj.io/hook-delete-policy: BeforeHookCreation
                spec:
                  backoffLimit: 3
                  activeDeadlineSeconds: 600
                  template:
                    metadata:
                      labels:
                        app.kubernetes.io/name: {name}
                        app.kubernetes.io/component: init
                    spec:
                      serviceAccountName: {name}-backend
                      restartPolicy: OnFailure
                      containers:
                        - name: init
                          image: mysql:8.0
                          imagePullPolicy: IfNotPresent
                          command:
                            - /bin/sh
                            - -c
                            - |
                              set -eu
                              
                              # Wait for MySQL to be ready
                              for i in $(seq 1 60); do
                                  if mysqladmin ping -h {db_service_name} -u root -p"$MYSQL_ROOT_PASSWORD" >/dev/null 2>&1; then
                                      echo "mysql reachable on attempt $i"
                                      break
                                  fi
                                  sleep 2
                              done
                              
                              # Run init command
                              {migration_cmd}
                          env:
                            - name: MYSQL_ROOT_PASSWORD
                              valueFrom:
                                secretKeyRef:
                                  name: {db_name}
                                  key: MYSQL_ROOT_PASSWORD
                """,
                name=name,
                namespace=namespace,
                db_service_name=db_service_name,
                migration_cmd=migration_cmd,
                db_name=db_name,
            )
        files[f"{name}-{'migrate' if db_engine == 'postgres' else 'init'}-job.yaml"] = job_content

    return files


def gitops_base_files(
    *,
    name: str,
    namespace: str,
    image_repo: str,
    template: TemplateSpec,
    observability_mode: str,
    base_tag: str,
    description: str,
    image_pull_secret: str,
    dev_host: str,
    add_app_component_label: bool = False,
) -> dict[str, str]:
    base_image_pull_policy = "Always" if base_tag == "latest" else "IfNotPresent"
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
        f"    app.kubernetes.io/instance: {name}",
        "    app.kubernetes.io/component: main-app" if add_app_component_label else None,
        "spec:",
        "  replicas: 1",
        "  selector:",
        "    matchLabels:",
        f"      app.kubernetes.io/name: {name}",
        "  template:",
        "    metadata:",
        "      labels:",
        f"        app.kubernetes.io/name: {name}",
        "        app.kubernetes.io/component: main-app" if add_app_component_label else None,
        "    spec:",
        f"      serviceAccountName: {name}",
        "      containers:",
        f"        - name: {template.container_name}",
        f"          image: {image_repo}:{base_tag}",
        f"          imagePullPolicy: {base_image_pull_policy}",
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

    resources = [
        "namespace.yaml",
        "serviceaccount.yaml",
        "deployment.yaml",
        "service.yaml",
        "ingress.yaml",
        "networkpolicy-default-deny.yaml",
        "networkpolicy-allow-dns-egress.yaml",
        "networkpolicy-allow-ingress.yaml",
    ]
    if observability_mode == "app-native":
        resources.insert(4, "servicemonitor.yaml")

    files = {
        "kustomization.yaml": (
            "apiVersion: kustomize.config.k8s.io/v1beta1\n"
            "kind: Kustomization\n"
            "resources:\n"
            + "".join(f"  - {resource}\n" for resource in resources)
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
        "deployment.yaml": "\n".join(line for line in deployment_lines if line is not None) + "\n",
        "service.yaml": render_template(
            """
            apiVersion: v1
            kind: Service
            metadata:
              name: {name}
              namespace: {namespace}
              labels:
                app.kubernetes.io/name: {name}
                app.kubernetes.io/instance: {name}
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

    if observability_mode == "app-native":
        files["servicemonitor.yaml"] = render_template(
            """
            apiVersion: monitoring.coreos.com/v1
            kind: ServiceMonitor
            metadata:
              name: {name}
              namespace: {namespace}
              labels:
                release: kube-prometheus-stack
            spec:
              selector:
                matchLabels:
                  app.kubernetes.io/name: {name}
              namespaceSelector:
                matchNames:
                  - {namespace}
              endpoints:
                - port: http
                  path: /metrics
                  interval: 30s
            """,
            name=name,
            namespace=namespace,
        )

    return files


def wordpress_base_files(
    *,
    name: str,
    namespace: str,
    image_repo: str,
    image_pull_secret: str,
    dev_host: str,
) -> dict[str, str]:
    db_secret_name = f"{name}-wordpress-db"
    db_service_name = f"{name}-mysql"

    serviceaccount = render_template(
        """
        apiVersion: v1
        kind: ServiceAccount
        metadata:
          name: {name}
          namespace: {namespace}
          labels:
            app.kubernetes.io/name: {name}
            app.kubernetes.io/component: web
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

    resources = [
        "namespace.yaml",
        "serviceaccount.yaml",
        "persistentvolumeclaim.yaml",
        "deployment.yaml",
        "service.yaml",
        "ingress.yaml",
        "mysql-service.yaml",
        "mysql-statefulset.yaml",
        "networkpolicy-default-deny.yaml",
        "networkpolicy-allow-dns-egress.yaml",
        "networkpolicy-allow-ingress.yaml",
        "networkpolicy-allow-mysql-egress.yaml",
        "networkpolicy-allow-mysql-ingress.yaml",
    ]

    base_tag = "latest"
    base_image_pull_policy = "Always" if base_tag == "latest" else "IfNotPresent"

    return {
        "kustomization.yaml": (
            "apiVersion: kustomize.config.k8s.io/v1beta1\n"
            "kind: Kustomization\n"
            "resources:\n"
            + "".join(f"  - {resource}\n" for resource in resources)
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
        "persistentvolumeclaim.yaml": render_template(
            """
            apiVersion: v1
            kind: PersistentVolumeClaim
            metadata:
              name: {name}-wp-content
              namespace: {namespace}
              labels:
                app.kubernetes.io/name: {name}
                app.kubernetes.io/component: web
            spec:
              accessModes:
                - ReadWriteOnce
              resources:
                requests:
                  storage: 10Gi
            """,
            name=name,
            namespace=namespace,
        ),
        "deployment.yaml": render_template(
            """
            apiVersion: apps/v1
            kind: Deployment
            metadata:
              name: {name}
              namespace: {namespace}
              labels:
                app.kubernetes.io/name: {name}
                app.kubernetes.io/instance: {name}
                app.kubernetes.io/component: web
            spec:
              replicas: 1
              selector:
                matchLabels:
                  app.kubernetes.io/name: {name}
                  app.kubernetes.io/component: web
              template:
                metadata:
                  labels:
                    app.kubernetes.io/name: {name}
                    app.kubernetes.io/component: web
                spec:
                  serviceAccountName: {name}
                  containers:
                    - name: web
                      image: {image_repo}:{base_tag}
                      imagePullPolicy: {base_image_pull_policy}
                      ports:
                        - name: http
                          containerPort: 80
                      env:
                        - name: WORDPRESS_DB_HOST
                          value: {db_service_name}:3306
                        - name: WORDPRESS_DB_USER
                          valueFrom:
                            secretKeyRef:
                              name: {db_secret_name}
                              key: WORDPRESS_DB_USER
                        - name: WORDPRESS_DB_PASSWORD
                          valueFrom:
                            secretKeyRef:
                              name: {db_secret_name}
                              key: WORDPRESS_DB_PASSWORD
                        - name: WORDPRESS_DB_NAME
                          valueFrom:
                            secretKeyRef:
                              name: {db_secret_name}
                              key: WORDPRESS_DB_NAME
                      readinessProbe:
                        httpGet:
                          path: /wp-login.php
                          port: http
                        initialDelaySeconds: 10
                        periodSeconds: 10
                      livenessProbe:
                        httpGet:
                          path: /wp-login.php
                          port: http
                        initialDelaySeconds: 20
                        periodSeconds: 20
                      volumeMounts:
                        - name: wp-content
                          mountPath: /var/www/html/wp-content
                      resources:
                        requests:
                          cpu: 100m
                          memory: 256Mi
                        limits:
                          cpu: 500m
                          memory: 512Mi
                  volumes:
                    - name: wp-content
                      persistentVolumeClaim:
                        claimName: {name}-wp-content
            """,
            name=name,
            namespace=namespace,
            image_repo=image_repo,
            db_service_name=db_service_name,
            db_secret_name=db_secret_name,
            base_tag=base_tag,
            base_image_pull_policy=base_image_pull_policy,
        ),
        "service.yaml": render_template(
            """
            apiVersion: v1
            kind: Service
            metadata:
              name: {name}
              namespace: {namespace}
              labels:
                app.kubernetes.io/name: {name}
                app.kubernetes.io/instance: {name}
                app.kubernetes.io/component: web
            spec:
              type: ClusterIP
              selector:
                app.kubernetes.io/name: {name}
                app.kubernetes.io/component: web
              ports:
                - name: http
                  port: 80
                  targetPort: http
            """,
            name=name,
            namespace=namespace,
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
                              number: 80
            """,
            name=name,
            namespace=namespace,
            dev_host=dev_host,
        ),
        "mysql-service.yaml": render_template(
            """
            apiVersion: v1
            kind: Service
            metadata:
              name: {db_service_name}
              namespace: {namespace}
              labels:
                app.kubernetes.io/name: {name}
                app.kubernetes.io/component: mysql
            spec:
              clusterIP: None
              selector:
                app.kubernetes.io/name: {name}
                app.kubernetes.io/component: mysql
              ports:
                - name: mysql
                  port: 3306
                  targetPort: mysql
            """,
            db_service_name=db_service_name,
            namespace=namespace,
            name=name,
        ),
        "mysql-statefulset.yaml": render_template(
            """
            apiVersion: apps/v1
            kind: StatefulSet
            metadata:
              name: {db_service_name}
              namespace: {namespace}
              labels:
                app.kubernetes.io/name: {name}
                app.kubernetes.io/component: mysql
            spec:
              serviceName: {db_service_name}
              replicas: 1
              selector:
                matchLabels:
                  app.kubernetes.io/name: {name}
                  app.kubernetes.io/component: mysql
              template:
                metadata:
                  labels:
                    app.kubernetes.io/name: {name}
                    app.kubernetes.io/component: mysql
                spec:
                  containers:
                    - name: mysql
                      image: mysql:8.0
                      imagePullPolicy: IfNotPresent
                      ports:
                        - name: mysql
                          containerPort: 3306
                      env:
                        - name: MYSQL_ROOT_PASSWORD
                          valueFrom:
                            secretKeyRef:
                              name: {db_secret_name}
                              key: MYSQL_ROOT_PASSWORD
                        - name: MYSQL_USER
                          valueFrom:
                            secretKeyRef:
                              name: {db_secret_name}
                              key: WORDPRESS_DB_USER
                        - name: MYSQL_PASSWORD
                          valueFrom:
                            secretKeyRef:
                              name: {db_secret_name}
                              key: WORDPRESS_DB_PASSWORD
                        - name: MYSQL_DATABASE
                          valueFrom:
                            secretKeyRef:
                              name: {db_secret_name}
                              key: WORDPRESS_DB_NAME
                      startupProbe:
                        exec:
                          command:
                            - mysqladmin
                            - ping
                            - -h
                            - 127.0.0.1
                        periodSeconds: 2
                        timeoutSeconds: 2
                        failureThreshold: 30
                      readinessProbe:
                        exec:
                          command:
                            - mysqladmin
                            - ping
                            - -h
                            - 127.0.0.1
                        periodSeconds: 5
                        timeoutSeconds: 3
                        failureThreshold: 6
                      volumeMounts:
                        - name: mysql-data
                          mountPath: /var/lib/mysql
                      resources:
                        requests:
                          cpu: 100m
                          memory: 256Mi
                        limits:
                          cpu: 500m
                          memory: 512Mi
              volumeClaimTemplates:
                - metadata:
                    name: mysql-data
                  spec:
                    accessModes:
                      - ReadWriteOnce
                    resources:
                      requests:
                        storage: 10Gi
            """,
            db_service_name=db_service_name,
            namespace=namespace,
            name=name,
            db_secret_name=db_secret_name,
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
                  app.kubernetes.io/component: web
              policyTypes:
                - Ingress
              ingress:
                - from:
                    - namespaceSelector:
                        matchLabels:
                          kubernetes.io/metadata.name: kube-system
                  ports:
                    - protocol: TCP
                      port: 80
            """,
            namespace=namespace,
            name=name,
        ),
        "networkpolicy-allow-mysql-egress.yaml": render_template(
            """
            apiVersion: networking.k8s.io/v1
            kind: NetworkPolicy
            metadata:
              name: allow-mysql-egress
              namespace: {namespace}
            spec:
              podSelector:
                matchLabels:
                  app.kubernetes.io/name: {name}
                  app.kubernetes.io/component: web
              policyTypes:
                - Egress
              egress:
                - to:
                    - podSelector:
                        matchLabels:
                          app.kubernetes.io/name: {name}
                          app.kubernetes.io/component: mysql
                  ports:
                    - protocol: TCP
                      port: 3306
            """,
            namespace=namespace,
            name=name,
        ),
        "networkpolicy-allow-mysql-ingress.yaml": render_template(
            """
            apiVersion: networking.k8s.io/v1
            kind: NetworkPolicy
            metadata:
              name: allow-mysql-ingress
              namespace: {namespace}
            spec:
              podSelector:
                matchLabels:
                  app.kubernetes.io/name: {name}
                  app.kubernetes.io/component: mysql
              policyTypes:
                - Ingress
              ingress:
                - from:
                    - podSelector:
                        matchLabels:
                          app.kubernetes.io/name: {name}
                          app.kubernetes.io/component: web
                  ports:
                    - protocol: TCP
                      port: 3306
            """,
            namespace=namespace,
            name=name,
        ),
    }


def wordpress_overlay_files(
    *,
    name: str,
    namespace: str,
    env_name: str,
    replicas: int,
    cpu_request: str,
    memory_request: str,
    cpu_limit: str,
    memory_limit: str,
    prod_host: str,
) -> dict[str, str]:
    db_secret_name = f"{name}-wordpress-db"
    files = {
        "kustomization.yaml": render_template(
            """
            apiVersion: kustomize.config.k8s.io/v1beta1
            kind: Kustomization
            resources:
              - ../../base
            generators:
              - wordpress-db-secret-generator.yaml
            commonLabels:
              homelab.env: {env_name}
            patches:
              - path: patch-deployment.yaml
            """,
            env_name=env_name,
        ),
        "wordpress-db-secret-generator.yaml": render_template(
            """
            apiVersion: viaduct.ai/v1
            kind: ksops
            metadata:
              name: wordpress-db-secret-generator
              annotations:
                config.kubernetes.io/function: |
                  exec:
                    path: ksops
            files:
              - wordpress-db-secret.enc.yaml
            """
        ),
        "wordpress-db-secret.enc.yaml": render_template(
            """
            # SOPS-encrypted Secret stub for WordPress + MySQL credentials.
            # Rotate by editing the placeholder values and re-encrypting with SOPS.
            # See docs/runbooks/sops-secrets.md for the full workflow.
            apiVersion: v1
            kind: Secret
            metadata:
              name: {db_secret_name}
              namespace: {namespace}
            type: Opaque
            stringData:
              WORDPRESS_DB_USER: ENC[AES256_GCM,data:xxx,iv:xxx,tag:xxx,type:str]
              WORDPRESS_DB_PASSWORD: ENC[AES256_GCM,data:xxx,iv:xxx,tag:xxx,type:str]
              WORDPRESS_DB_NAME: ENC[AES256_GCM,data:xxx,iv:xxx,tag:xxx,type:str]
              MYSQL_ROOT_PASSWORD: ENC[AES256_GCM,data:xxx,iv:xxx,tag:xxx,type:str]
            sops:
              kms: []
              gcp_kms: []
              azure_kv: []
              hc_vault: []
              age:
                - recipient: age1xxx
                  enc: |
                    -----BEGIN AGE ENCRYPTED FILE-----
                    ...
                    -----END AGE ENCRYPTED FILE-----
              lastmodified: "2026-03-25T00:00:00Z"
              mac: ENC[AES256_GCM,data:xxx,iv:xxx,tag:xxx,type:str]
              pgp: []
              encrypted_regex: ^(stringData|data)$
              version: 3.8.1
            """,
            db_secret_name=db_secret_name,
            namespace=namespace,
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
                    - name: web
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
            generators:
              - wordpress-db-secret-generator.yaml
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
    image_pull_policy = "Always" if image_tag == "latest" else "IfNotPresent"
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
                      imagePullPolicy: {image_pull_policy}
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
            image_pull_policy=image_pull_policy,
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
    if template in ("nextjs", "react", "vue"):
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

                  - name: Setup Node.js
                    uses: actions/setup-node@v4
                    with:
                      node-version: "20"
                      cache: npm

                  - name: Install dependencies
                    run: npm install

                  - name: Build
                    run: npm run build

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
                      tags: |
                        {image_repo}:sha-${{{{ github.sha }}}}
                        {image_repo}:latest
            """,
            name=name,
            image_repo=image_repo,
        )
    if template == "node-nestjs":
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

                  - name: Setup Node.js
                    uses: actions/setup-node@v4
                    with:
                      node-version: "20"
                      cache: npm

                  - name: Install dependencies
                    run: npm ci

                  - name: Build
                    run: npm run build

                  - name: Run tests
                    run: npm test

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
                      tags: |
                        {image_repo}:sha-${{{{ github.sha }}}}
                        {image_repo}:latest
            """,
            name=name,
            image_repo=image_repo,
        )
    if template == "node-express":
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

                  - name: Setup Node.js
                    uses: actions/setup-node@v4
                    with:
                      node-version: "20"
                      cache: npm

                  - name: Install dependencies
                    run: npm ci

                  - name: Run tests
                    run: npm test

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
                      tags: |
                        {image_repo}:sha-${{{{ github.sha }}}}
                        {image_repo}:latest
            """,
            name=name,
            image_repo=image_repo,
        )
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
                      tags: |
                        {image_repo}:sha-${{{{ github.sha }}}}
                        {image_repo}:latest
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
                  tags: |
                    {image_repo}:sha-${{{{ github.sha }}}}
                    {image_repo}:latest
        """,
        name=name,
        image_repo=image_repo,
    )


def scaffold_repo(args: argparse.Namespace, template: TemplateSpec, repo_output_dir: Path) -> None:
    if template.key == "wordpress":
        return
    if template.key == "python-django":
        files = build_python_django_repo_files(args.name, args.description, args.image_repo)
    elif template.key == "python-flask":
        files = build_python_flask_repo_files(args.name, args.description, args.image_repo)
    elif template.key == "static-nginx":
        files = build_static_nginx_repo_files(args.name, args.description, args.image_repo)
    elif template.key == "react":
        files = build_react_repo_files(args.name, args.description, args.image_repo)
    elif template.key == "nextjs":
        files = build_nextjs_repo_files(args.name, args.description, args.image_repo)
    elif template.key == "vue":
        files = build_vue_repo_files(args.name, args.description, args.image_repo)
    elif template.key == "node-express":
        files = build_node_express_repo_files(args.name, args.description, args.image_repo)
    elif template.key == "node-nestjs":
        files = build_node_nestjs_repo_files(args.name, args.description, args.image_repo)
    else:
        files = build_python_fastapi_repo_files(args.name, args.description, args.image_repo)

    files[f".github/workflows/build-{args.name}.yml"] = repo_workflow(args.name, args.image_repo, template.key)

    for relative_path, content in files.items():
        write_file(repo_output_dir / relative_path, content)


def scaffold_gitops(args: argparse.Namespace, template: TemplateSpec, gitops_root: Path, namespace: str, dev_host: str, prod_host: str) -> None:
    app_root = gitops_root / "apps" / args.name
    ensure_absent(app_root, "service manifest directory")

    if template.key == "wordpress":
        base_files = wordpress_base_files(
            name=args.name,
            namespace=namespace,
            image_repo=args.image_repo,
            image_pull_secret=args.image_pull_secret,
            dev_host=dev_host,
        )
        dev_overlay = wordpress_overlay_files(
            name=args.name,
            namespace=namespace,
            env_name="dev",
            replicas=args.dev_replicas,
            cpu_request="50m",
            memory_request="64Mi",
            cpu_limit="300m",
            memory_limit="256Mi",
            prod_host=prod_host,
        )
        prod_overlay = wordpress_overlay_files(
            name=args.name,
            namespace=namespace,
            env_name="prod",
            replicas=args.prod_replicas,
            cpu_request="100m",
            memory_request="128Mi",
            cpu_limit="500m",
            memory_limit="512Mi",
            prod_host=prod_host,
        )
    else:
        base_files = gitops_base_files(
            name=args.name,
            namespace=namespace,
            image_repo=args.image_repo,
            template=template,
            observability_mode=args.observability_mode or template.default_observability_mode,
            base_tag=args.dev_tag,
            description=args.description,
            image_pull_secret=args.image_pull_secret,
            dev_host=dev_host,
            add_app_component_label=hasattr(args, 'add_on') and args.add_on == 'database',
        )

        if hasattr(args, 'add_on') and args.add_on == 'database':
            db_engine = getattr(args, 'db_engine', 'postgres')
            migration_command = getattr(args, 'migration_command', '')
            db_addon_files = gitops_database_files(
                name=args.name,
                namespace=namespace,
                db_engine=db_engine,
                image_repo=args.image_repo,
                base_tag=args.dev_tag,
                migration_command=migration_command,
            )
            base_files.update(db_addon_files)

            kustomization_content = base_files['kustomization.yaml']
            db_addon_resources = [
                f"  - {args.name}-{db_engine}-statefulset.yaml",
                f"  - {args.name}-{db_engine}-service.yaml",
                f"  - networkpolicy-allow-{db_engine}-egress.yaml",
                f"  - networkpolicy-allow-{db_engine}-ingress.yaml",
                f"  - {args.name}-{db_engine}-secret.enc.yaml",
            ]
            if migration_command or db_engine == 'postgres':
                db_addon_resources.append(
                    f"  - {args.name}-{'migrate' if db_engine == 'postgres' else 'init'}-job.yaml"
                )
            kustomization_content = kustomization_content.rstrip() + "\n" + "\n".join(db_addon_resources) + "\n"
            base_files['kustomization.yaml'] = kustomization_content

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

    for relative_path, content in base_files.items():
        write_file(app_root / "base" / relative_path, content)

    for relative_path, content in dev_overlay.items():
        write_file(app_root / "envs" / "dev" / relative_path, content)

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
        public_host=prod_host,
    )


def main() -> None:
    args = parse_args()
    validate_service_name(args.name)

    if args.template == "wordpress" and args.image_pull_secret == "ghcr-pull-secret":
        args.image_pull_secret = ""

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
    if template.key != "wordpress":
        ensure_repo_output_dir(repo_output_dir, args.force)
        scaffold_repo(args, template, repo_output_dir)
    scaffold_gitops(args, template, gitops_root, namespace, dev_host, prod_host)

    if template.key != "wordpress":
        print(f"Generated service repo: {repo_output_dir}")
    else:
        print("No application repo scaffold generated for wordpress template.")
    print(f"Generated GitOps manifests under: {gitops_root / 'apps' / args.name}")
    print(f"Dev app manifest: {gitops_root / 'environments' / 'dev' / 'workloads' / f'{args.name}-app.yaml'}")
    print(f"Prod app manifest (not auto-enabled in single-cluster mode): {gitops_root / 'environments' / 'prod' / 'workloads' / f'{args.name}-app.yaml'}")
    print(f"Catalog metadata entry: {gitops_root / 'services.yaml'}")
    print("Next steps:")
    if template.key != "wordpress":
        print(f"  1. Review the generated repo files in {repo_output_dir}")
        print(f"  2. Run ./scripts/render-kustomize.sh {gitops_root / 'apps' / args.name / 'envs' / 'dev'}")
        print(
            f"  3. Open a PR in the workloads repo with apps/{args.name}, bootstrap/project-homelab.yaml, services.yaml, and environments/dev/workloads/{args.name}-app.yaml"
        )
        print("  4. Replace the default runbook URL in services.yaml if this service needs a dedicated runbook.")
        print("  5. Keep environments/prod/workloads/kustomization.yaml unchanged until a dedicated prod target exists.")
    else:
        print(f"  1. Run ./scripts/render-kustomize.sh {gitops_root / 'apps' / args.name / 'envs' / 'dev'}")
        print(
            f"  2. Open a PR in the workloads repo with apps/{args.name}, bootstrap/project-homelab.yaml, services.yaml, and environments/dev/workloads/{args.name}-app.yaml"
        )
        print("  3. Rotate the generated SOPS secret placeholders before syncing the WordPress deployment.")
        print("  4. Keep environments/prod/workloads/kustomization.yaml unchanged until a dedicated prod target exists.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
