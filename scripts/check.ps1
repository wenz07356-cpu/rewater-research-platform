[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $ProjectRoot ".env"
$Failures = [System.Collections.Generic.List[string]]::new()

function Test-GatewayUrl {
    param(
        [Parameter(Mandatory)] [string] $Name,
        [Parameter(Mandatory)] [string] $Url
    )

    try {
        Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 10 | Out-Null
        Write-Host "[OK] $Name" -ForegroundColor Green
    }
    catch {
        Write-Host "[FAIL] $Name" -ForegroundColor Red
        $Failures.Add("gateway")
    }
}

function Test-ContainerUrl {
    param(
        [Parameter(Mandatory)] [string] $Service,
        [Parameter(Mandatory)] [string] $Url
    )

    docker compose exec -T $Service python -c "import urllib.request; urllib.request.urlopen('$Url', timeout=5)" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] $Service" -ForegroundColor Green
    }
    else {
        Write-Host "[FAIL] $Service" -ForegroundColor Red
        $Failures.Add($Service)
    }
}

function Test-ContainerDependency {
    param(
        [Parameter(Mandatory)] [string] $Service,
        [Parameter(Mandatory)] [string] $Name,
        [Parameter(Mandatory)] [string] $EnvironmentVariable,
        [Parameter(Mandatory)] [int] $DefaultPort
    )

    $Code = "import os,socket; from urllib.parse import urlparse; value=os.environ['$EnvironmentVariable']; value=value if '://' in value else 'tcp://'+value; endpoint=urlparse(value); connection=socket.create_connection((endpoint.hostname, endpoint.port or $DefaultPort), 5); connection.close()"
    docker compose exec -T $Service python -c $Code 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] $Name" -ForegroundColor Green
    }
    else {
        Write-Host "[FAIL] $Name" -ForegroundColor Red
        $Failures.Add($Service)
    }
}

Push-Location $ProjectRoot
try {
    $Port = 8080
    if (Test-Path -LiteralPath $EnvFile -PathType Leaf) {
        $PortLine = Get-Content -LiteralPath $EnvFile | Where-Object { $_ -match '^\s*PLATFORM_PORT\s*=' } | Select-Object -Last 1
        if ($PortLine) {
            $ConfiguredPort = (($PortLine -split '=', 2)[1]).Trim()
            if ($ConfiguredPort) { $Port = $ConfiguredPort }
        }
    }

    $GatewayBaseUrl = "http://localhost:$Port"
    Test-GatewayUrl -Name "gateway health" -Url "$GatewayBaseUrl/health"
    Test-GatewayUrl -Name "platform home" -Url "$GatewayBaseUrl/"
    Test-GatewayUrl -Name "knowledge import page" -Url "$GatewayBaseUrl/knowledge/import"
    Test-GatewayUrl -Name "knowledge chat page" -Url "$GatewayBaseUrl/knowledge/chat"
    Test-GatewayUrl -Name "research page" -Url "$GatewayBaseUrl/research"
    Test-GatewayUrl -Name "knowledge import API" -Url "$GatewayBaseUrl/api/knowledge/import/health"
    Test-GatewayUrl -Name "knowledge query API" -Url "$GatewayBaseUrl/api/knowledge/query/health"
    Test-GatewayUrl -Name "research API" -Url "$GatewayBaseUrl/api/research/v1/openapi.json"

    Test-ContainerUrl -Service "knowledge-import" -Url "http://127.0.0.1:8000/health"
    Test-ContainerUrl -Service "knowledge-query" -Url "http://127.0.0.1:8001/health"
    Test-ContainerUrl -Service "research-api" -Url "http://127.0.0.1:8010/health"

    Test-ContainerDependency -Service "knowledge-query" -Name "external MongoDB" -EnvironmentVariable "MONGO_URL" -DefaultPort 27017
    Test-ContainerDependency -Service "knowledge-query" -Name "external Milvus" -EnvironmentVariable "MILVUS_URL" -DefaultPort 19530
    Test-ContainerDependency -Service "knowledge-query" -Name "external MinIO" -EnvironmentVariable "MINIO_ENDPOINT" -DefaultPort 9000
    Test-ContainerDependency -Service "research-worker" -Name "external Redis" -EnvironmentVariable "REDIS_URL" -DefaultPort 6379

    $WorkerPing = docker compose exec -T research-worker celery -A app.celery_app:celery_app inspect ping --timeout 5 2>$null
    if ($LASTEXITCODE -eq 0 -and ($WorkerPing -join "`n") -match "pong") {
        Write-Host "[OK] research-worker" -ForegroundColor Green
    }
    else {
        Write-Host "[FAIL] research-worker" -ForegroundColor Red
        $Failures.Add("research-worker")
    }

    if ($Failures.Count -gt 0) {
        foreach ($Service in ($Failures | Select-Object -Unique)) {
            Write-Host "`nRecent logs: $Service" -ForegroundColor Yellow
            docker compose logs --tail 40 $Service
        }
        throw "Health checks failed: $($Failures -join ', ')"
    }

    Write-Host "All core services are healthy." -ForegroundColor Green
}
finally {
    Pop-Location
}
