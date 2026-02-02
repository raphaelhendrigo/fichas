# DEPLOY.md

Este guia descreve o deploy mantendo o fluxo atual do projeto.

## 1) Deploy local / VPS (Docker Compose)
1) Ajuste o `.env` com as variaveis do ambiente.
2) Rode o deploy local:
   powershell -ExecutionPolicy Bypass -File .\scripts\deploy_local.ps1
3) Healthcheck:
   https://www.raphaelhendrigo.com.br/healthz

Se for remoto via SSH:
1) Configure `DEPLOY_SSH_HOST` e `DEPLOY_APP_PATH`.
2) Rode:
   powershell -ExecutionPolicy Bypass -File .\scripts\deploy_remote.ps1 -Host $env:DEPLOY_SSH_HOST -Path $env:DEPLOY_APP_PATH -Branch main

## 2) Deploy no GCP (Cloud Run + Cloud SQL)
Requisitos:
- gcloud instalado e logado
- Vision API e Storage API habilitadas

Passos:
1) Configure variaveis de ambiente (exemplo):
   GCP_PROJECT_ID=<seu-projeto>
   GCP_REGION=us-central1
   GCS_BUCKET=<bucket-de-uploads>
   GCS_OCR_BUCKET=<bucket-ocr> (pode ser o mesmo do GCS_BUCKET)
2) Execute:
   cd cloudrun
   .\deploy.ps1 -ProjectId <seu-projeto> -Region us-central1 -GcsBucket <bucket>
3) Rode migrations e seed (via Cloud SQL Auth Proxy) conforme README.md.

## 3) OCR Google (config)
Variaveis obrigatorias para OCR:
- GCP_OCR_PROVIDER=google_vision
- GCS_OCR_BUCKET (obrigatorio para PDF/TIFF)
- OCR_LANGUAGE_HINTS=pt (ou `pt,en`)

Local:
- Configure `GOOGLE_APPLICATION_CREDENTIALS` apontando para o JSON da service account.
- Monte o arquivo no container, se necessario.

Producao (Cloud Run):
- Use a Service Account do Cloud Run com acesso a Vision + Storage.

## 4) Rollback (Cloud Run)
1) Liste revisoes:
   gcloud run revisions list --service <service-name> --region <region>
2) Direcione trafego:
   gcloud run services update-traffic <service-name> --region <region> --to-revisions <REVISION>=100
