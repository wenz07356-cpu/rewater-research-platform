[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Push-Location $ProjectRoot
try {
    docker compose down
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose shutdown failed." }
    Write-Host "Platform stopped. Persistent volumes were preserved." -ForegroundColor Green
}
finally {
    Pop-Location
}
