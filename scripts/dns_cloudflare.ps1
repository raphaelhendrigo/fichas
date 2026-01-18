param(
  [string]$ApiToken = $env:CLOUDFLARE_API_TOKEN,
  [string]$ZoneId = $env:CLOUDFLARE_ZONE_ID,
  [string]$ZoneName = $env:CLOUDFLARE_ZONE_NAME,
  [string]$RecordName = $env:CLOUDFLARE_RECORD_NAME,
  [string]$RecordType = $env:CLOUDFLARE_RECORD_TYPE,
  [string]$RecordContent = $env:CLOUDFLARE_RECORD_CONTENT,
  [int]$Ttl = [int]$env:CLOUDFLARE_TTL,
  [string]$Proxied = $env:CLOUDFLARE_PROXIED
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
if (-not $RecordType) { $RecordType = "A" }
if (-not $RecordContent) { Write-Error "CLOUDFLARE_RECORD_CONTENT obrigatorio."; exit 1 }
if (-not $Ttl) { $Ttl = 120 }

$recordNameFull = $RecordName
if ($RecordName -notmatch "\.") {
  if ($ZoneName) { $recordNameFull = "$RecordName.$ZoneName" }
}

$proxiedBool = ConvertTo-Bool -Value $Proxied -Default $false

$headers = @{
  Authorization = "Bearer $ApiToken"
  "Content-Type" = "application/json"
}
$base = "https://api.cloudflare.com/client/v4"

$lookup = Invoke-RestMethod -Method Get -Uri "$base/zones/$ZoneId/dns_records?type=$RecordType&name=$recordNameFull" -Headers $headers
if (-not $lookup.success) {
  Write-Error "Falha ao consultar DNS: $($lookup.errors | ConvertTo-Json -Depth 5)"
  exit 1
}

$record = $lookup.result | Select-Object -First 1
$payload = @{
  type = $RecordType
  name = $recordNameFull
  content = $RecordContent
  ttl = $Ttl
  proxied = $proxiedBool
} | ConvertTo-Json

if ($record) {
  $needsUpdate = ($record.content -ne $RecordContent) -or ([bool]$record.proxied -ne $proxiedBool) -or ([int]$record.ttl -ne $Ttl)
  if (-not $needsUpdate) {
    Write-Host "DNS sem alteracoes: $recordNameFull ($RecordType)"
    exit 0
  }
  $update = Invoke-RestMethod -Method Put -Uri "$base/zones/$ZoneId/dns_records/$($record.id)" -Headers $headers -Body $payload
  if (-not $update.success) {
    Write-Error "Falha ao atualizar DNS: $($update.errors | ConvertTo-Json -Depth 5)"
    exit 1
  }
  Write-Host "DNS atualizado: $recordNameFull ($RecordType -> $RecordContent)"
} else {
  $create = Invoke-RestMethod -Method Post -Uri "$base/zones/$ZoneId/dns_records" -Headers $headers -Body $payload
  if (-not $create.success) {
    Write-Error "Falha ao criar DNS: $($create.errors | ConvertTo-Json -Depth 5)"
    exit 1
  }
  Write-Host "DNS criado: $recordNameFull ($RecordType -> $RecordContent)"
}
