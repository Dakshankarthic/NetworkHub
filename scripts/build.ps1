$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    if (-not (Test-Path -LiteralPath 'src\bin\mihomo.exe') -or -not (Test-Path -LiteralPath 'src\bin\wintun.dll')) {
        throw 'Run python scripts/fetch_engine.py first.'
    }
    python -m PyInstaller --noconfirm --clean --onedir --windowed --name NetworkHub --paths src src/network_hub.py
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed.' }
    Copy-Item -LiteralPath src\bin -Destination dist\NetworkHub\bin -Recurse -Force
    Copy-Item -LiteralPath LICENSE,THIRD_PARTY.md,README.md -Destination dist\NetworkHub -Force
    Copy-Item -LiteralPath LICENSE -Destination dist\NetworkHub\bin\MIHOMO-COPYING.txt -Force
    New-Item -ItemType Directory -Path dist\NetworkHub\source -Force | Out-Null
    Get-ChildItem -LiteralPath src -Filter '*.py' | Copy-Item -Destination dist\NetworkHub\source -Force
    python scripts/collect_notices.py
    if ($LASTEXITCODE -ne 0) { throw 'License notice collection failed.' }
    Write-Host 'Built dist\NetworkHub\NetworkHub.exe. Distribute the whole NetworkHub folder.'
} finally {
    Pop-Location
}
