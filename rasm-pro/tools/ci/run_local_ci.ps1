# Local CI - the same checks the GitHub workflow runs, on this machine.
#
# Why: pushing `.github/workflows/*.yml` from this repository is refused
# ("refusing to allow an OAuth App to create or update workflow ... without
# `workflow` scope"), so the workflow file cannot reach GitHub from here.
# This script runs the identical steps locally and writes the same artifact.
#
#   powershell -ExecutionPolicy Bypass -File rasm-pro\tools\ci\run_local_ci.ps1
#
# Exit code = the pytest exit code (0 = green).  The report is written to
# rasm-pro/qa/ci/pytest-report.xml and the console output to
# rasm-pro/qa/ci/ci-console.txt (both are evidence, and travel with the code).
#
# NOTE: keep this file ASCII-only.  Windows PowerShell 5.1 reads .ps1 files
# as ANSI when there is no BOM, and non-ASCII bytes then break the parser.

$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$Rasm = Join-Path $Repo "rasm-pro"
$Out = Join-Path $Rasm "qa\ci"
New-Item -ItemType Directory -Force -Path $Out | Out-Null

$python = Join-Path $Rasm ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = (Get-Command python).Source
    Write-Host "using system python: $python"
}

Write-Host "== 1/3 compile check =="
& $python -m compileall -q (Join-Path $Rasm "engine") (Join-Path $Rasm "rasm.py") (Join-Path $Rasm "tools") (Join-Path $Repo "studio")
if ($LASTEXITCODE -ne 0) { Write-Host "compile failed"; exit 1 }

Write-Host "== 2/3 test suite =="
Push-Location $Rasm
& $python -m pytest -q tests --junitxml (Join-Path $Out "pytest-report.xml") 2>&1 |
    Tee-Object -FilePath (Join-Path $Out "ci-console.txt")
$code = $LASTEXITCODE
Pop-Location

Write-Host "== 3/3 result =="
if ($code -eq 0) {
    Write-Host "green - report: $Out\pytest-report.xml"
} else {
    Write-Host "red (exit $code) - report: $Out\pytest-report.xml"
}
exit $code
