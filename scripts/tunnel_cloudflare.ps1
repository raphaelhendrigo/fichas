param(
  [string]$ApiToken = $env:CLOUDFLARE_API_TOKEN,
  [string]$AccountId = $env:CLOUDFLARE_ACCOUNT_ID,
  [string]$ZoneId = $env:CLOUDFLARE_ZONE_ID,
  [string]$ZoneName = $env:CLOUDFLARE_ZONE_NAME,
  [string]$RecordName = $env:CLOUDFLARE_RECORD_NAME,
  [string]$TunnelName = $env:CLOUDFLARE_TUNNEL_NAME,
  [int]$Ttl = [int]$env:CLOUDFLARE_TTL,
  [string]$Proxied = $env:CLOUDFLARE_PROXIED,
  [string]$TokenPath = ".secrets\\tunnel_token.txt",
  [string]$SkipDns = $env:CLOUDFLARE_SKIP_DNS
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
if (-not $AccountId) { Write-Error "CLOUDFLARE_ACCOUNT_ID obrigatorio."; exit 1 }
if (-not $RecordName) { Write-Error "CLOUDFLARE_RECORD_NAME obrigatorio."; exit 1 }
if (-not $TunnelName) { $TunnelName = "engenhodigitalweb-lab" }
if (-not $Ttl) { $Ttl = 120 }

$recordNameFull = $RecordName
if ($RecordName -notmatch "\.") {
  if ($ZoneName) { $recordNameFull = "$RecordName.$ZoneName" }
}

$skipDnsBool = ConvertTo-Bool -Value $SkipDns -Default $false
$proxiedBool = ConvertTo-Bool -Value $Proxied -Default $true

$headers = @{
  Authorization = "Bearer $ApiToken"
  "Content-Type" = "application/json"
}
$base = "https://api.cloudflare.com/client/v4"

$list = Invoke-RestMethod -Method Get -Uri "$base/accounts/$AccountId/cfd_tunnel?name=$TunnelName" -Headers $headers
if (-not $list.success) {
  Write-Error "Falha ao consultar tunnel: $($list.errors | ConvertTo-Json -Depth 5)"
  exit 1
}

$tunnel = $list.result | Select-Object -First 1
if (-not $tunnel) {
  $bytes = New-Object byte[] 32
  [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
  $secret = [System.Convert]::ToBase64String($bytes)
  $createBody = @{
    name = $TunnelName
    tunnel_secret = $secret
  } | ConvertTo-Json
  $create = Invoke-RestMethod -Method Post -Uri "$base/accounts/$AccountId/cfd_tunnel" -Headers $headers -Body $createBody
  if (-not $create.success) {
    Write-Error "Falha ao criar tunnel: $($create.errors | ConvertTo-Json -Depth 5)"
    exit 1
  }
  $tunnel = $create.result
}

$tunnelId = $tunnel.id
if (-not $tunnelId) {
  Write-Error "Tunnel sem ID retornado pela API."
  exit 1
}

$tokenResp = Invoke-RestMethod -Method Get -Uri "$base/accounts/$AccountId/cfd_tunnel/$tunnelId/token" -Headers $headers
if (-not $tokenResp.success) {
  Write-Error "Falha ao gerar token do tunnel: $($tokenResp.errors | ConvertTo-Json -Depth 5)"
  exit 1
}

$token = $tokenResp.result
if (-not $token) {
  Write-Error "Token vazio retornado pela API."
  exit 1
}

$tokenDir = Split-Path -Parent $TokenPath
if ($tokenDir) {
  New-Item -ItemType Directory -Path $tokenDir -Force | Out-Null
}
$token | Set-Content -Path $TokenPath -NoNewline -Encoding ascii

$cnameContent = "$tunnelId.cfargotunnel.com"

if (-not $skipDnsBool) {
  if (-not $ZoneId) { Write-Error "CLOUDFLARE_ZONE_ID obrigatorio."; exit 1 }
  $lookup = Invoke-RestMethod -Method Get -Uri "$base/zones/$ZoneId/dns_records?type=CNAME&name=$recordNameFull" -Headers $headers
  if (-not $lookup.success) {
    Write-Error "Falha ao consultar DNS: $($lookup.errors | ConvertTo-Json -Depth 5)"
    exit 1
  }

  $record = $lookup.result | Select-Object -First 1
  $payload = @{
    type = "CNAME"
    name = $recordNameFull
    content = $cnameContent
    ttl = $Ttl
    proxied = $proxiedBool
  } | ConvertTo-Json

  if ($record) {
    $needsUpdate = ($record.content -ne $cnameContent) -or ([bool]$record.proxied -ne $proxiedBool) -or ([int]$record.ttl -ne $Ttl)
    if ($needsUpdate) {
      $update = Invoke-RestMethod -Method Put -Uri "$base/zones/$ZoneId/dns_records/$($record.id)" -Headers $headers -Body $payload
      if (-not $update.success) {
        Write-Error "Falha ao atualizar DNS: $($update.errors | ConvertTo-Json -Depth 5)"
        exit 1
      }
    }
  } else {
    $create = Invoke-RestMethod -Method Post -Uri "$base/zones/$ZoneId/dns_records" -Headers $headers -Body $payload
    if (-not $create.success) {
      Write-Error "Falha ao criar DNS: $($create.errors | ConvertTo-Json -Depth 5)"
      exit 1
    }
  }
  Write-Host "DNS apontado: $recordNameFull -> $cnameContent"
} else {
  Write-Host "DNS nao alterado (CLOUDFLARE_SKIP_DNS=true)."
  Write-Host "Crie manualmente um CNAME: $recordNameFull -> $cnameContent"
}

Write-Host "Tunnel pronto: $TunnelName ($tunnelId)"
Write-Host "Token salvo em: $TokenPath"
