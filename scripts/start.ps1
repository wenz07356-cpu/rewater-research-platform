[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $ProjectRoot ".env"

if (-not (Test-Path -LiteralPath $EnvFile -PathType Leaf)) {
    throw "Missing root .env file. Run: Copy-Item .env.example .env"
}

function Get-DotEnvValue {
    param(
        [Parameter(Mandatory)] [string] $Name,
        [Parameter(Mandatory)] [string] $Default
    )

    $Pattern = "^\s*$([regex]::Escape($Name))\s*="
    $Line = Get-Content -LiteralPath $EnvFile | Where-Object { $_ -match $Pattern } | Select-Object -Last 1
    if (-not $Line) { return $Default }
    $Value = (($Line -split '=', 2)[1]).Trim().Trim('"').Trim("'")
    if (-not $Value) { return $Default }
    return $Value
}

function Resolve-HostPath {
    param([Parameter(Mandatory)] [string] $Path)

    if ([System.IO.Path]::IsPathRooted($Path)) { return $Path }
    return Join-Path $ProjectRoot $Path
}

$RequiredModels = @(
    (Resolve-HostPath (Get-DotEnvValue -Name "BGE_M3_HOST_PATH" -Default "models\bge-m3")),
    (Resolve-HostPath (Get-DotEnvValue -Name "BGE_RERANKER_HOST_PATH" -Default "models\bge-reranker-v2-m3"))
)

$MissingModels = @($RequiredModels | Where-Object {
    -not (Test-Path -LiteralPath $_ -PathType Container)
})
if ($MissingModels.Count -gt 0) {
    throw "Missing local model directories: $($MissingModels -join ', ')"
}

Push-Location $ProjectRoot
try {
    docker compose config --quiet
    if ($LASTEXITCODE -ne 0) { throw "Compose configuration validation failed." }

    docker compose up -d --build
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose startup failed." }

    Write-Host "Containers started. Waiting for health checks..."
    $Deadline = (Get-Date).AddMinutes(10)
    do {
        $Pending = @()
        foreach ($Service in @("gateway", "knowledge-import", "knowledge-query", "research-api")) {
            $Status = docker compose ps --format json $Service | ConvertFrom-Json
            if (-not $Status -or $Status.Health -ne "healthy") {
                $Pending += $Service
            }
        }
        if ($Pending.Count -eq 0) { break }
        Start-Sleep -Seconds 5
    } while ((Get-Date) -lt $Deadline)

    if ($Pending.Count -gt 0) {
        docker compose ps
        throw "Services did not become healthy within 10 minutes: $($Pending -join ', ')"
    }

    & (Join-Path $PSScriptRoot "check.ps1")

    $Port = 8080
    $PortLine = Get-Content -LiteralPath $EnvFile | Where-Object { $_ -match '^\s*PLATFORM_PORT\s*=' } | Select-Object -Last 1
    if ($PortLine) {
        $ConfiguredPort = (($PortLine -split '=', 2)[1]).Trim()
        if ($ConfiguredPort) { $Port = $ConfiguredPort }
    }

    Write-Host "Platform is ready: http://localhost:$Port" -ForegroundColor Green
    Write-Host "Run .\scripts\check.ps1 for a complete health check."
}
finally {
    Pop-Location
}
