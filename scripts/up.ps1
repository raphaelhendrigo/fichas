param(
  [switch]$Dev,
  [switch]$Tunnel
)

$files = @("docker-compose.yml")
if ($Dev) { $files += "docker-compose.dev.yml" }
if ($Tunnel) { $files += "docker-compose.tunnel.yml" }

$args = @("compose")
foreach ($file in $files) { $args += @("-f", $file) }
$args += @("up", "-d", "--build")

& docker @args
exit $LASTEXITCODE
