param(
  [switch]$Dev,
  [switch]$Tunnel
)

$files = @("docker-compose.yml")
if ($Dev) { $files += "docker-compose.dev.yml" }
if ($Tunnel) { $files += "docker-compose.tunnel.yml" }

$args = @("compose")
foreach ($file in $files) { $args += @("-f", $file) }
$args += @("build", "--no-cache")

& docker @args
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$args = @("compose")
foreach ($file in $files) { $args += @("-f", $file) }
$args += @("up", "-d")

& docker @args
exit $LASTEXITCODE
