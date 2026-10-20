# verify_stage0.ps1 - read-only checks for the stage0 backup outputs.
# ASCII-only on purpose: Windows PowerShell 5.1 misreads UTF-8 .ps1 without BOM.
$BackupRoot = 'D:\withbord inmation\backups\stage0-20261020'
$script:fail = 0
function Check([string]$name, [bool]$cond) {
    if ($cond) { Write-Output "OK    $name" } else { Write-Output "FAIL  $name"; $script:fail++ }
}

Write-Output "== code bundle =="
$code = "$BackupRoot\code\rasm-pro-code.bundle"
Check 'code bundle exists' (Test-Path $code)
if (Test-Path $code) {
    & git bundle verify $code 2>$null | Out-Null
    Check 'code bundle verify exit=0' ($LASTEXITCODE -eq 0)
    $heads = (& git bundle list-heads $code | Out-String)
    Check 'bundle has HEAD ed66355' ($heads -match 'ed66355')
    Check 'bundle has safety-pre tag' ($heads -match 'safety-pre-ed66355')
    $shaFile = "$BackupRoot\code\rasm-pro-code.bundle.sha256"
    Check 'bundle sha256 file exists' (Test-Path $shaFile)
    if (Test-Path $shaFile) {
        $expected = (Get-Content $shaFile -Raw).Trim()
        $actual = (Get-FileHash $code -Algorithm SHA256).Hash
        Check 'bundle sha256 matches' ($expected -eq $actual)
    }
}

Write-Output "== data manifest =="
$dataCsv = "$BackupRoot\MANIFEST-DATA.csv"
Check 'MANIFEST-DATA.csv exists' (Test-Path $dataCsv)
if (Test-Path $dataCsv) {
    $rows = Import-Csv $dataCsv
    $files = (Get-ChildItem "$BackupRoot\data" -Recurse -File).Count
    Check "data rows=$($rows.Count) equals disk=$files" ($rows.Count -eq $files)
    $sample = $rows | Get-Random -Count ([Math]::Min(5, $rows.Count))
    foreach ($row in $sample) {
        $full = Join-Path "$BackupRoot\data" $row.path
        $h = (Get-FileHash $full -Algorithm SHA256).Hash
        Check "sample hash $($row.path)" ($h -eq $row.sha256)
    }
}

Write-Output "== runtime manifest =="
$rtCsv = "$BackupRoot\MANIFEST-RUNTIME.csv"
Check 'MANIFEST-RUNTIME.csv exists' (Test-Path $rtCsv)
if (Test-Path $rtCsv) {
    $rows = Import-Csv $rtCsv
    $files = (Get-ChildItem "$BackupRoot\runtime" -Recurse -File).Count
    Check "runtime rows=$($rows.Count) equals disk=$files" ($rows.Count -eq $files)
    $sample = $rows | Get-Random -Count ([Math]::Min(3, $rows.Count))
    foreach ($row in $sample) {
        $full = Join-Path $BackupRoot $row.path
        $h = (Get-FileHash $full -Algorithm SHA256).Hash
        Check "sample hash $($row.path)" ($h -eq $row.sha256)
    }
}

Write-Output "== misc =="
Check 'environment snapshot exists' (Test-Path "$BackupRoot\runtime\ENVIRONMENT.txt")
Check 'external copy note exists' (Test-Path "$BackupRoot\EXTERNAL-COPY-PENDING.txt")

Write-Output '----'
if ($script:fail -eq 0) { Write-Output 'RESULT: ALL CHECKS PASSED' } else { Write-Output "RESULT: $($script:fail) CHECK(S) FAILED" }
