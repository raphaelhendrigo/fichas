param(
  [switch]$Dev,
  [switch]$Tunnel,
  [switch]$Volumes
)

$files = @("docker-compose.yml")
if ($Dev) { $files += "docker-compose.dev.yml" }
if ($Tunnel) { $files += "docker-compose.tunnel.yml" }

$args = @("compose")
foreach ($file in $files) { $args += @("-f", $file) }
$args += @("down")
if ($Volumes) { $args += @("-v") }

& docker @args
exit $LASTEXITCODE
