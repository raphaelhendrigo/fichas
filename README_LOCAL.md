# README_LOCAL.md

Este guia prepara o ambiente local (Windows 11 + Docker Desktop) com HTTPS e subdominio de testes:
`https://lab.engenhodigitalweb.com.br/`
Nao altera o dominio principal `https://www.engenhodigitalweb.com.br/`.

## 1) Requisitos
- Docker Desktop (com suporte a `docker compose`)
- PowerShell
- Dominio no Cloudflare (para automacao de DNS). Se nao estiver, veja `DNS_MANUAL.md`.

## 2) Preparar o ambiente local
1) Copie o arquivo de ambiente:
   `Copy-Item .env.example .env`
2) Ajuste o `.env`:
   - `SECRET_KEY` (obrigatorio)
   - `COOKIE_SECURE=true` quando estiver usando HTTPS
   - `STORAGE_BACKEND=local`
3) Suba os containers:
   `docker compose up -d --build`
4) Rode migrations e seed:
   `docker compose exec app alembic upgrade head`
   `docker compose exec app python scripts/seed_admin_and_templates.py`

Acesso local:
- HTTP: `http://localhost`
- HTTPS (autoassinado ate gerar o Let's Encrypt): `https://localhost`
O Nginx gera certificado autoassinado quando nao encontra o Let's Encrypt em `certs/`.

## 3) Protecao opcional com Basic Auth
Crie o arquivo `nginx/htpasswd/htpasswd`:
```
docker run --rm httpd:2.4-alpine htpasswd -nbB usuario senha | Set-Content -Path .\nginx\htpasswd\htpasswd -NoNewline
```
Ative no `.env`:
```
ENABLE_BASIC_AUTH=true
```

## 4) Estrategia A: IP publico + port-forward + Let's Encrypt
### 4.1 DNS do subdominio (A record)
Exemplo (uma vez):
```
$env:CLOUDFLARE_API_TOKEN="..."
$env:CLOUDFLARE_ZONE_ID="..."
$env:CLOUDFLARE_ZONE_NAME="engenhodigitalweb.com.br"
$env:CLOUDFLARE_RECORD_NAME="lab"
$env:CLOUDFLARE_RECORD_CONTENT="SEU_IP_PUBLICO"
$env:CLOUDFLARE_TTL="120"
$env:CLOUDFLARE_PROXIED="false"
.\scripts\dns_cloudflare.ps1
```
DDNS (atualizacao automatica do IP):
```
.\scripts\ddns_cloudflare.ps1
```
Se o DNS estiver na Locaweb, crie o registro manualmente (TTL fixo 3600). Veja `DNS_MANUAL.md`.

### 4.2 Port-forward no roteador
Redirecione:
- Porta 80 -> IP do seu PC (container Nginx)
- Porta 443 -> IP do seu PC (container Nginx)

### 4.3 Certificado Let's Encrypt (HTTP-01)
```
docker compose --profile letsencrypt run --rm certbot certonly --webroot -w /var/www/certbot -d lab.engenhodigitalweb.com.br --email SEU_EMAIL --agree-tos --no-eff-email
docker compose restart nginx
```

### 4.4 Certificado Let's Encrypt via DNS-01 (sem porta 80)
Use o plugin `dns-cloudflare`:
```
New-Item -ItemType Directory -Force -Path .secrets | Out-Null
"dns_cloudflare_api_token = SEU_TOKEN" | Set-Content -Path .\.secrets\cloudflare.ini -NoNewline -Encoding ascii
docker run --rm -v ${PWD}/certs:/etc/letsencrypt -v ${PWD}/.secrets:/secrets certbot/dns-cloudflare certonly --dns-cloudflare --dns-cloudflare-credentials /secrets/cloudflare.ini -d lab.engenhodigitalweb.com.br --email SEU_EMAIL --agree-tos --no-eff-email
docker compose restart nginx
```

## 5) Estrategia B: Cloudflare Tunnel (sem abrir portas)
1) Defina variaveis no ambiente (ou no seu perfil do PowerShell):
```
$env:CLOUDFLARE_API_TOKEN="..."
$env:CLOUDFLARE_ACCOUNT_ID="..."
$env:CLOUDFLARE_ZONE_ID="..."
$env:CLOUDFLARE_ZONE_NAME="engenhodigitalweb.com.br"
$env:CLOUDFLARE_RECORD_NAME="lab"
$env:CLOUDFLARE_TUNNEL_NAME="engenhodigitalweb-lab"
$env:CLOUDFLARE_PROXIED="true"
```
2) Crie o tunnel e o DNS:
```
.\scripts\tunnel_cloudflare.ps1
```
Se o DNS estiver na Locaweb, use:
```
$env:CLOUDFLARE_SKIP_DNS="true"
.\scripts\tunnel_cloudflare.ps1
```
E crie manualmente o CNAME em Locaweb (veja `DNS_MANUAL.md`).
3) Suba com tunnel:
```
docker compose -f docker-compose.yml -f docker-compose.tunnel.yml up -d --build
```
O token fica em `.secrets/tunnel_token.txt` e consumido pelo compose.

Opcional: use Basic Auth no Nginx ou habilite Cloudflare Access no painel do Cloudflare.

## 6) Comandos rapidos (PowerShell)
Build + Up:
```
docker compose up -d --build
```
Com scripts:
```
.\scripts\up.ps1
.\scripts\up.ps1 -Dev
.\scripts\up.ps1 -Tunnel
```
Logs:
```
docker compose logs -f --tail 200
```
Down:
```
docker compose down
```
Restart:
```
docker compose restart nginx
```
Healthcheck:
```
.\scripts\health.ps1
```
DNS (Cloudflare):
```
.\scripts\dns_cloudflare.ps1
```
DDNS (Cloudflare):
```
.\scripts\ddns_cloudflare.ps1
```
Tunnel (Cloudflare):
```
.\scripts\tunnel_cloudflare.ps1
```

## 7) Observacoes
- `COOKIE_SECURE` deve ficar `true` quando acessar via HTTPS.
- Certificados e tokens nao devem ser versionados: use `.secrets/` e `certs/`.

## 8) Deploy atual no GCP (referencia)
- Alvo: Cloud Run (script `cloudrun/deploy.ps1`) com Cloud SQL Postgres e bucket GCS.
- Build: `cloudrun/cloudbuild.yaml` cria imagem no Artifact Registry.
- Variaveis importantes: `DATABASE_URL`, `SECRET_KEY`, `STORAGE_BACKEND=gcs`, `GCS_BUCKET`.

Rollback (sem afetar o dominio principal):
```
gcloud run revisions list --service fichas-mvp --region us-central1
gcloud run services update-traffic fichas-mvp --region us-central1 --to-revisions REVISION=100
```
