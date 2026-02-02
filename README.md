# Fichas TCM-SP (MVP)

MVP para cadastro de fichas de processos com FastAPI, Postgres e HTMX.
Foco em performance para ~60k fichas, multi-templates e anexos.

## Stack
- Python 3.12 + FastAPI
- SQLAlchemy 2 + Alembic
- Postgres (padrao)
- Jinja2 + HTMX + Tailwind CDN
- Docker + Docker Compose

## Rodar local (PowerShell + Docker)
1) Copie o arquivo de ambiente:
   Copy-Item .env.example .env
2) Ajuste no `.env`:
   - SECRET_KEY (obrigatorio)
   - APP_BASE_PATH=/fichas (ou vazio para raiz/subdominio)
3) Suba os containers:
   docker compose up -d --build
4) Rode migrations:
   docker compose exec app alembic upgrade head
5) Rode seed (admin + templates):
   docker compose exec app python scripts/seed_admin_and_templates.py

Acesse:
- HTTP: http://localhost/fichas (ou / se APP_BASE_PATH vazio)
- HTTPS (Nginx): https://localhost/fichas
Login: use ADMIN_SEED_EMAIL / ADMIN_SEED_PASSWORD do .env

## Rodar local (sem Docker)
```
cd app
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
$env:DATABASE_URL="postgresql+psycopg://fichas:fichas@localhost:5432/fichas"
alembic upgrade head
python scripts/seed_admin_and_templates.py
uvicorn fichas.main:app --host 0.0.0.0 --port 8080 --reload
```

## Templates a partir de PDFs
1) Extrair drafts:
```
python tools/extract_pdf_templates.py --input exemplos --output templates_draft
```
2) Ajustar manualmente (opcional):
```
python tools/map_template.py templates_draft/SEU_ARQUIVO.json
```
3) Importar no banco:
```
python tools/import_templates.py --path templates_draft
```
Ou dentro do container:
```
docker compose exec app python /app/tools/import_templates.py --path /app/templates_draft
```
Opcional (seed automatico):
```
$env:IMPORT_DRAFT_TEMPLATES="true"
docker compose exec app python scripts/seed_admin_and_templates.py
```

## Tests
docker compose exec app pytest

### OCR integration tests (opcional)
Rodam apenas quando `RUN_GCP_INTEGRATION_TESTS=1` e credenciais estao disponiveis.
Exemplo (local):
```
$env:RUN_GCP_INTEGRATION_TESTS="1"
$env:GOOGLE_APPLICATION_CREDENTIALS="C:\\caminho\\service-account.json"
$env:GCS_OCR_BUCKET="seu-bucket"
docker compose exec app pytest -k integration
```

## OCR (Google Cloud Vision)
Este projeto usa o Google Vision API para OCR (imagens e PDFs).

Requisitos no GCP:
- Vision API habilitada
- Storage API habilitada
- Service Account com permissao de Vision + Storage (roles `roles/vision.user` e `roles/storage.objectAdmin`)

Variaveis importantes (ver `.env.example`):
- `GCP_OCR_PROVIDER=google_vision`
- `GCS_OCR_BUCKET` (obrigatorio para OCR de PDF/TIFF)
- `OCR_LANGUAGE_HINTS=pt` (pode incluir mais, ex.: `pt,en`)
- `GOOGLE_APPLICATION_CREDENTIALS` (apenas local, apontando para o JSON da service account)

## Hospedagem local com HTTPS
Veja `README_LOCAL.md` para Nginx + HTTPS e Cloudflare Tunnel.

## Variaveis de ambiente
- DATABASE_URL=postgresql+psycopg://fichas:fichas@db:5432/fichas
- SECRET_KEY=... (obrigatorio)
- STORAGE_BACKEND=local|gcs
- LOCAL_STORAGE_PATH=./data/uploads
- GCS_BUCKET=nome-do-bucket
- GCP_OCR_PROVIDER=google_vision
- GCP_PROJECT_ID=...
- GCP_REGION=...
- GCS_OCR_BUCKET=...
- OCR_MAX_PAGES=10
- OCR_TIMEOUT_SECONDS=180
- OCR_RETRY=2
- OCR_LANGUAGE_HINTS=pt
- ADMIN_SEED_EMAIL=...
- ADMIN_SEED_PASSWORD=...
- APP_BASE_PATH=/fichas (ou vazio)
- IMPORT_DRAFT_TEMPLATES=true|false

## Deploy no GCP (Cloud Run + Cloud SQL)
Requisitos: gcloud instalado e logado, projeto ativo, billing habilitado.

1) Entre na pasta cloudrun:
   cd cloudrun
2) Execute o script de deploy (exemplo):
   .\deploy.ps1 -ProjectId <seu-projeto> -Region us-central1 -GcsBucket <bucket>
   O script cria/ajusta Cloud SQL, bucket (se informado) e faz deploy no Cloud Run.
   Para OCR de PDF, use o mesmo bucket ou configure `GCS_OCR_BUCKET`.

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
