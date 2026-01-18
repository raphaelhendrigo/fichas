param(
  [string]$Url = $env:HEALTH_URL
)

if (-not $Url) {
  $Url = "http://localhost/healthz"
}

try {
  $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 10
  Write-Host ("OK {0} {1}" -f $response.StatusCode, $Url)
  exit 0
} catch {
  Write-Error ("Healthcheck falhou: {0}" -f $_.Exception.Message)
  exit 1
}
