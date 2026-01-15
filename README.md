# Fichas TCM-SP (MVP)

MVP para cadastro de fichas de processos com FastAPI, Postgres e HTMX.
Foco em performance para ~60k fichas, multi-templates e anexos.

## Stack
- Python 3.12 + FastAPI
- SQLAlchemy 2 + Alembic
- Postgres (padrao)
- Jinja2 + HTMX + Tailwind CDN
- Docker + Docker Compose

## Rodar local (PowerShell)
1) Copie o arquivo de ambiente:
   Copy-Item .env.example .env
2) Suba os containers:
   docker compose up --build
3) Rode migrations:
   docker compose exec app alembic upgrade head
4) Rode seed (admin + templates):
   docker compose exec app python scripts/seed_admin_and_templates.py

Acesse: http://localhost:8080
Login: use ADMIN_SEED_EMAIL / ADMIN_SEED_PASSWORD do .env

## Tests
docker compose exec app pytest

## Variaveis de ambiente
- DATABASE_URL=postgresql+psycopg://fichas:fichas@db:5432/fichas
- SECRET_KEY=... (obrigatorio)
- STORAGE_BACKEND=local|gcs
- LOCAL_STORAGE_PATH=./data/uploads
- GCS_BUCKET=nome-do-bucket
- ADMIN_SEED_EMAIL=...
- ADMIN_SEED_PASSWORD=...

## Deploy no GCP (Cloud Run + Cloud SQL)
Requisitos: gcloud instalado e logado, projeto ativo, billing habilitado.

1) Entre na pasta cloudrun:
   cd cloudrun
2) Execute o script de deploy (exemplo):
   .\deploy.ps1 -ProjectId <seu-projeto> -Region us-central1 -GcsBucket <bucket>
   O script cria/ajusta Cloud SQL, bucket (se informado) e faz deploy no Cloud Run.

3) Rode migrations e seed via Cloud SQL Auth Proxy:
   gcloud sql instances describe fichas-postgres --format="value(connectionName)"
   # Em outro terminal:
   cloud-sql-proxy <connectionName> --port 5432
   # Em PowerShell:
   $env:DATABASE_URL="postgresql+psycopg://fichas:<senha>@localhost:5432/fichas"
   cd ..\app
   alembic upgrade head
   python scripts/seed_admin_and_templates.py

## Migrar para on-prem
1) Copie o projeto para o servidor.
2) Ajuste DATABASE_URL e STORAGE_BACKEND=local no .env.
3) docker compose up --build
4) Rode migrations e seed (mesmos comandos acima).
