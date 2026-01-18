param(
  [string]$ApiToken = $env:CLOUDFLARE_API_TOKEN,
  [string]$ZoneId = $env:CLOUDFLARE_ZONE_ID,
  [string]$ZoneName = $env:CLOUDFLARE_ZONE_NAME,
  [string]$RecordName = $env:CLOUDFLARE_RECORD_NAME,
  [int]$Ttl = [int]$env:CLOUDFLARE_TTL,
  [string]$Proxied = $env:CLOUDFLARE_PROXIED,
  [string]$IpUrl = $env:DDNS_IP_URL
)

function ConvertTo-Bool {
  param([string]$Value, [bool]$Default = $false)
  if ([string]::IsNullOrWhiteSpace($Value)) { return $Default }
  switch ($Value.ToLowerInvariant()) {
    "true" { return $true }
    "1" { return $true }
    "yes" { return $true }
    "y" { return $true }
    "false" { return $false }
    "0" { return $false }
    "no" { return $false }
    "n" { return $false }
    default { return $Default }
  }
}

if (-not $ApiToken) { Write-Error "CLOUDFLARE_API_TOKEN obrigatorio."; exit 1 }
if (-not $ZoneId) { Write-Error "CLOUDFLARE_ZONE_ID obrigatorio."; exit 1 }
if (-not $RecordName) { Write-Error "CLOUDFLARE_RECORD_NAME obrigatorio."; exit 1 }
if (-not $Ttl) { $Ttl = 120 }
if (-not $IpUrl) { $IpUrl = "https://api.ipify.org" }

$recordNameFull = $RecordName
if ($RecordName -notmatch "\.") {
  if ($ZoneName) { $recordNameFull = "$RecordName.$ZoneName" }
}

$proxiedBool = ConvertTo-Bool -Value $Proxied -Default $false

$publicIp = (Invoke-RestMethod -Method Get -Uri $IpUrl -TimeoutSec 10).Trim()
if (-not $publicIp) {
  Write-Error "Falha ao detectar IP publico."
  exit 1
}

$headers = @{
  Authorization = "Bearer $ApiToken"
  "Content-Type" = "application/json"
}
$base = "https://api.cloudflare.com/client/v4"

$lookup = Invoke-RestMethod -Method Get -Uri "$base/zones/$ZoneId/dns_records?type=A&name=$recordNameFull" -Headers $headers
if (-not $lookup.success) {
  Write-Error "Falha ao consultar DNS: $($lookup.errors | ConvertTo-Json -Depth 5)"
  exit 1
}

$record = $lookup.result | Select-Object -First 1
$payload = @{
  type = "A"
  name = $recordNameFull
  content = $publicIp
  ttl = $Ttl
  proxied = $proxiedBool
} | ConvertTo-Json

if ($record) {
  $needsUpdate = ($record.content -ne $publicIp) -or ([bool]$record.proxied -ne $proxiedBool) -or ([int]$record.ttl -ne $Ttl)
  if (-not $needsUpdate) {
    Write-Host "IP publico sem alteracao: $publicIp"
    exit 0
  }
  $update = Invoke-RestMethod -Method Put -Uri "$base/zones/$ZoneId/dns_records/$($record.id)" -Headers $headers -Body $payload
  if (-not $update.success) {
    Write-Error "Falha ao atualizar DNS: $($update.errors | ConvertTo-Json -Depth 5)"
    exit 1
  }
  Write-Host "DNS atualizado: $recordNameFull -> $publicIp"
} else {
  $create = Invoke-RestMethod -Method Post -Uri "$base/zones/$ZoneId/dns_records" -Headers $headers -Body $payload
  if (-not $create.success) {
    Write-Error "Falha ao criar DNS: $($create.errors | ConvertTo-Json -Depth 5)"
    exit 1
  }
  Write-Host "DNS criado: $recordNameFull -> $publicIp"
}
