param(
  [Alias('Host')]
  [string]$SshHost = $env:DEPLOY_SSH_HOST,
  [string]$Path = $env:DEPLOY_APP_PATH,
  [string]$Branch = $env:DEPLOY_BRANCH,
  [switch]$SkipMigrations
)

if (-not $SshHost) { Write-Error "DEPLOY_SSH_HOST obrigatorio."; exit 1 }
if (-not $Path) { $Path = "D:\\OneDrive - tcm.sp.gov.br\\Fichas" }
if (-not $Branch) { $Branch = "main" }

$lines = @(
  '$ErrorActionPreference = "Stop"'
  '$userProfile = [Environment]::GetFolderPath("UserProfile")'
  'if ($userProfile) { $env:USERPROFILE = $userProfile; $env:HOME = $userProfile }'
  '$defaultDockerConfig = Join-Path $env:USERPROFILE ".docker\\config.json"'
  'New-Item -ItemType Directory -Force (Split-Path $defaultDockerConfig) | Out-Null'
  '''{"auths":{}}'' | Set-Content -Encoding ascii $defaultDockerConfig'
  '$dockerConfig = Join-Path $env:TEMP "docker-config-nocreds"'
  'New-Item -ItemType Directory -Force $dockerConfig | Out-Null'
  '''{}'' | Set-Content -Encoding ascii (Join-Path $dockerConfig "config.json")'
  '$env:DOCKER_CONFIG = $dockerConfig'
  '$env:DOCKER_BUILDKIT = "0"'
  '$env:COMPOSE_DOCKER_CLI_BUILD = "0"'
  "Set-Location -LiteralPath `"$Path`""
  'git fetch --all'
  "git checkout $Branch"
  "git pull origin $Branch"
  'docker --config $dockerConfig compose build --pull=false'
  'if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }'
  'docker --config $dockerConfig compose up -d --no-build'
  'if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }'
)

if (-not $SkipMigrations) {
  $lines += 'docker --config $dockerConfig compose exec app alembic upgrade head'
  $lines += 'if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }'
}

$remoteScript = $lines -join "`n"
$encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($remoteScript))
$command = "powershell -NoProfile -EncodedCommand $encoded"

& ssh $SshHost $command
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
