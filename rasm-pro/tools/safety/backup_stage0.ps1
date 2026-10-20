# backup_stage0.ps1 - reproduce the stage0 backup bundle (one button).
# Writes only inside the backup folder. Never modifies project files.
# ASCII-only on purpose: Windows PowerShell 5.1 misreads UTF-8 .ps1 without BOM.
param(
    [string]$Repo = 'D:\withbord inmation',
    [string]$BackupRoot = 'D:\withbord inmation\backups\stage0-20261020'
)
$ErrorActionPreference = 'Continue'

$Python = "$Repo\rasm-pro\.venv\Scripts\python.exe"
$Manifest = "$Repo\rasm-pro\tools\safety\make_manifest.py"
$Ffmpeg = "$Repo\studio\runtime\ffmpeg.exe"

Write-Output "== 1/6 freeze current state =="
New-Item -ItemType Directory -Force "$BackupRoot\code", "$BackupRoot\data", "$BackupRoot\runtime" | Out-Null
& git -C $Repo status --porcelain | Out-File -Encoding utf8 "$BackupRoot\code\UNCOMMITTED-NOTE.txt"
"timestamp: $(Get-Date -Format o)" | Out-File -Append -Encoding utf8 "$BackupRoot\code\UNCOMMITTED-NOTE.txt"
& git -C $Repo diff | Out-File -Encoding utf8 "$BackupRoot\code\uncommitted.patch"

Write-Output "== 2/6 code bundle =="
& git -C $Repo bundle create "$BackupRoot\code\rasm-pro-code.bundle" --all 2>$null | Out-Null
$bundleRc = $LASTEXITCODE
& git -C $Repo bundle verify "$BackupRoot\code\rasm-pro-code.bundle" 2>$null | Out-Null
$verifyRc = $LASTEXITCODE
if ($bundleRc -ne 0 -or $verifyRc -ne 0) {
    throw "bundle create/verify failed (create=$bundleRc verify=$verifyRc)"
}
$hash = (Get-FileHash "$BackupRoot\code\rasm-pro-code.bundle" -Algorithm SHA256).Hash
$hash | Out-File -Encoding ascii "$BackupRoot\code\rasm-pro-code.bundle.sha256"
Write-Output "bundle OK sha256=$hash"

Write-Output "== 3/6 production data =="
$copies = @(
    @{ src = "$Repo\rasm-pro\projects";    dst = "$BackupRoot\data\rasm-pro\projects" },
    @{ src = "$Repo\rasm-pro\assets";      dst = "$BackupRoot\data\rasm-pro\assets" },
    @{ src = "$Repo\rasm-pro\library";     dst = "$BackupRoot\data\rasm-pro\library" },
    @{ src = "$Repo\rasm-pro\style_packs"; dst = "$BackupRoot\data\rasm-pro\style_packs" },
    @{ src = "$Repo\rasm-pro\docs";        dst = "$BackupRoot\data\rasm-pro\docs" },
    @{ src = "$Repo\studio\data";          dst = "$BackupRoot\data\studio\data" }
)
# Optional untracked work folder (may appear while the project is in use)
if (Test-Path "$Repo\rasm-pro\future-character-assets") {
    $copies += @{ src = "$Repo\rasm-pro\future-character-assets"; dst = "$BackupRoot\data\rasm-pro\future-character-assets" }
}
foreach ($c in $copies) {
    robocopy $c.src $c.dst /E /COPY:DAT /R:2 /W:2 /NFL /NDL /NP /MT:8 | Out-Null
    $rc = $LASTEXITCODE
    if ($rc -ge 8) { throw "robocopy failed ($rc): $($c.src)" }
    Write-Output ("copied rc=$rc : " + $c.src)
}

Write-Output "== 4/6 runtime package =="
foreach ($c in @(
        @{ src = "$Repo\studio\models";         dst = "$BackupRoot\runtime\models" },
        @{ src = "$Repo\studio\runtime";        dst = "$BackupRoot\runtime\runtime" },
        @{ src = "$Repo\rasm-pro\assets\fonts"; dst = "$BackupRoot\runtime\fonts" }
    )) {
    robocopy $c.src $c.dst /E /COPY:DAT /R:2 /W:2 /NFL /NDL /NP /MT:8 | Out-Null
    $rc = $LASTEXITCODE
    if ($rc -ge 8) { throw "robocopy failed ($rc): $($c.src)" }
    Write-Output ("copied rc=$rc : " + $c.src)
}

$envf = "$BackupRoot\runtime\ENVIRONMENT.txt"
"rasm-pro stage0 environment snapshot - $(Get-Date -Format o)" | Out-File -Encoding utf8 $envf
("python(rasm-pro): " + (& $Python --version 2>&1)) | Out-File -Append -Encoding utf8 $envf
"" | Out-File -Append -Encoding utf8 $envf
"pip freeze (rasm-pro venv):" | Out-File -Append -Encoding utf8 $envf
& $Python -m pip freeze 2>&1 | Out-File -Append -Encoding utf8 $envf
"" | Out-File -Append -Encoding utf8 $envf
"ffmpeg:" | Out-File -Append -Encoding utf8 $envf
& $Ffmpeg -version 2>&1 | Select-Object -First 1 | Out-File -Append -Encoding utf8 $envf

Write-Output "== 5/6 SHA256 manifests =="
& $Python $Manifest "$BackupRoot\MANIFEST-DATA.csv" "$BackupRoot\data\rasm-pro" "$BackupRoot\data\studio"
if ($LASTEXITCODE -ne 0) { throw "data manifest failed" }
& $Python $Manifest "$BackupRoot\MANIFEST-RUNTIME.csv" "$BackupRoot\runtime"
if ($LASTEXITCODE -ne 0) { throw "runtime manifest failed" }

Write-Output "== 6/6 verify =="
& "$PSScriptRoot\verify_stage0.ps1"
