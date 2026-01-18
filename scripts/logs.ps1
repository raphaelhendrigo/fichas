param(
  [string]$Service = "",
  [int]$Tail = 200,
  [switch]$Dev,
  [switch]$Tunnel
)

$files = @("docker-compose.yml")
if ($Dev) { $files += "docker-compose.dev.yml" }
if ($Tunnel) { $files += "docker-compose.tunnel.yml" }

$args = @("compose")
foreach ($file in $files) { $args += @("-f", $file) }
$args += @("logs", "-f", "--tail", $Tail)
if ($Service) { $args += $Service }

& docker @args
exit $LASTEXITCODE
