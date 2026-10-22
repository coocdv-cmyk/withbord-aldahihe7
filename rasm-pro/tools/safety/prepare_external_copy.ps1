# Prepare the external copy (the one physical thing only the owner can do).
#
# What this does:
#   1. a git bundle of the code (all branches) + a SHA256 file,
#   2. a manifest (SHA256) of the production data and the runtime,
#   3. a README with the exact commands to copy it to the external medium
#      and to verify it there.
#
# It does NOT copy anything to an external drive: that medium does not exist
# on this machine, and pretending otherwise is how the first stage stayed
# "partially open" for a week.
#
#   powershell -ExecutionPolicy Bypass -File tools\safety\prepare_external_copy.ps1
#   powershell -ExecutionPolicy Bypass -File tools\safety\verify_stage0.ps1

$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$Stamp = (Get-Date -Format "yyyyMMdd-HHmm")
$Out = Join-Path $Repo "backups\external-$Stamp"

Write-Host "== 1/4 the code bundle =="
New-Item -ItemType Directory -Force -Path (Join-Path $Out "code") | Out-Null
$Bundle = Join-Path $Out "code\rasm-pro-branches.bundle"
Push-Location $Repo
& git bundle create $Bundle stage6-contract main master
& git bundle verify $Bundle
Pop-Location
$hash = (Get-FileHash -Algorithm SHA256 $Bundle).Hash
"$hash  $(Split-Path -Leaf $Bundle)" | Out-File -FilePath "$Bundle.sha256" -Encoding ascii
Write-Host ("   bundle: {0} MB" -f [math]::Round((Get-Item $Bundle).Length / 1MB, 1))

Write-Host "== 2/4 the data manifest =="
New-Item -ItemType Directory -Force -Path (Join-Path $Out "data") | Out-Null
& python (Join-Path $Repo "rasm-pro\tools\safety\make_manifest.py") `
    (Join-Path $Out "data\MANIFEST-DATA.csv") (Join-Path $Repo "rasm-pro\projects")
& python (Join-Path $Repo "rasm-pro\tools\safety\make_manifest.py") `
    (Join-Path $Out "data\MANIFEST-RUNTIME.csv") (Join-Path $Repo "studio\models")

Write-Host "== 3/4 the README =="
$readme = @"
External copy - prepared $Stamp

WHAT IS HERE
  code\rasm-pro-branches.bundle   the whole code (all branches) + its SHA256
  data\MANIFEST-DATA.csv          SHA256 of every production file
  data\MANIFEST-RUNTIME.csv       SHA256 of the model files

WHAT IS NOT HERE (and why)
  The LFS objects (the 136 MB icon manifest) are NOT inside a bundle: they come
  from the remote.  After cloning, run:  git lfs pull
  The media (the rendered episodes) live in the repository history: cloning
  the bundle brings them back.

HOW TO COPY IT (on the machine that holds the medium)
  robocopy "$Out" E:\rasm-backup\ /E /R:2 /W:1
  (or copy the folder to a USB disk by hand)

HOW TO VERIFY IT (on the other machine, from the copy)
  git clone --no-hardlinks E:\rasm-backup\code\rasm-pro-branches.bundle rasm-restore
  cd rasm-restore
  git lfs pull
  cd rasm-pro
  python -m venv .venv
  .venv\Scripts\python.exe -m pip install -r requirements.txt pytest
  .venv\Scripts\python.exe -m pytest -q tests
  .venv\Scripts\python.exe tools\restore_drill.py --bundle E:\rasm-backup\code\rasm-pro-branches.bundle

THE CHECK THAT MATTERS
  A bundle is not a backup until it has been restored.  The drill above does
  the restore: clone, environment, tests, and a render.
"@
$readme | Out-File -FilePath (Join-Path $Out "README-EXTERNAL-COPY.txt") -Encoding utf8

Write-Host "== 4/4 done =="
Write-Host "Prepared: $Out"
Write-Host "Copy it to the external medium, then run the drill from the copy."
Write-Host "Size:"
Get-ChildItem -Recurse -File $Out | Measure-Object -Sum Length |
    ForEach-Object { "  {0} files, {1} MB" -f $_.Count, [math]::Round($_.Sum / 1MB, 1) }
