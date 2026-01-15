param(
  [string]$ProjectId = $env:GCP_PROJECT_ID,
  [string]$Region = $env:GCP_REGION,
  [string]$ServiceName = "fichas-mvp",
  [string]$InstanceName = "fichas-postgres",
  [string]$DbEdition = "enterprise",
  [string]$DbTier = "db-f1-micro",
  [string]$DbName = "fichas",
  [string]$DbUser = "fichas",
  [string]$DbPassword = $env:DB_PASSWORD,
  [string]$SecretKey = $env:SECRET_KEY,
  [string]$GcsBucket = $env:GCS_BUCKET,
  [string]$AdminSeedEmail = $env:ADMIN_SEED_EMAIL,
  [string]$AdminSeedPassword = $env:ADMIN_SEED_PASSWORD
)

if (-not $ProjectId) {
  Write-Error "ProjectId obrigatorio. Use -ProjectId ou defina GCP_PROJECT_ID."
  exit 1
}

if (-not $Region) { $Region = "us-central1" }
if (-not $DbPassword) { $DbPassword = [guid]::NewGuid().ToString("N") }
if (-not $SecretKey) { $SecretKey = [guid]::NewGuid().ToString("N") }
if (-not $AdminSeedEmail) { $AdminSeedEmail = "admin@tcm.sp.gov.br" }
if (-not $AdminSeedPassword) { $AdminSeedPassword = "admin123" }

if (-not $GcsBucket) {
  Write-Error "GcsBucket obrigatorio para storage no GCP. Use -GcsBucket ou defina GCS_BUCKET."
  exit 1
}

gcloud config set project $ProjectId
gcloud services enable run.googleapis.com sqladmin.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com

gcloud sql instances describe $InstanceName 2>$null
if ($LASTEXITCODE -ne 0) {
  gcloud sql instances create $InstanceName --database-version=POSTGRES_16 --edition=$DbEdition --tier=$DbTier --region=$Region
}

$dbExists = gcloud sql databases list --instance $InstanceName --format="value(name)" | Select-String -SimpleMatch $DbName
if (-not $dbExists) {
  gcloud sql databases create $DbName --instance $InstanceName
}

$userExists = gcloud sql users list --instance $InstanceName --format="value(name)" | Select-String -SimpleMatch $DbUser
if (-not $userExists) {
  gcloud sql users create $DbUser --instance $InstanceName --password $DbPassword
} else {
  gcloud sql users set-password $DbUser --instance $InstanceName --password $DbPassword
}

gcloud storage buckets describe "gs://$GcsBucket" 2>$null
if ($LASTEXITCODE -ne 0) {
  gcloud storage buckets create "gs://$GcsBucket" --location=$Region
}

$connectionName = gcloud sql instances describe $InstanceName --format="value(connectionName)"
$databaseUrl = "postgresql+psycopg://${DbUser}:${DbPassword}@/${DbName}?host=/cloudsql/${connectionName}"
$repoRoot = Resolve-Path "$PSScriptRoot\\.."

gcloud run deploy $ServiceName `
  --source $repoRoot `
  --region $Region `
  --allow-unauthenticated `
  --add-cloudsql-instances $connectionName `
  --set-env-vars "DATABASE_URL=$databaseUrl,SECRET_KEY=$SecretKey,STORAGE_BACKEND=gcs,GCS_BUCKET=$GcsBucket,ADMIN_SEED_EMAIL=$AdminSeedEmail,ADMIN_SEED_PASSWORD=$AdminSeedPassword"

Write-Host "Deploy concluido. Rode migrations e seed via Cloud SQL Auth Proxy."
