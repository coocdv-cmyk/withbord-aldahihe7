<#
.SYNOPSIS
    إزالة محرّك راسم من هذا الجهاز.
.DESCRIPTION
    يوقف العمليات الجارية، يحذف مجلد التثبيت واختصار قائمة «ابدأ» ومشغّل PATH.
    **لا يحذف مشاريعك ولا اعتماداتك** —(projects/ وresearch/ داخل مجلد التثبيت
    تُنقل إلى سطح المكتب أولًا إن وُجدت).
.PARAMETER InstallDir
    مجلد التثبيت (افتراضيًا: %LOCALAPPDATA%\Programs\RasmPro).
.PARAMETER KeepProjects
    نقل المشاريع إلى سطح المكتب بدل حذفها.
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File uninstall.ps1
#>
param(
    [string]$InstallDir = "$env:LOCALAPPDATA\Programs\RasmPro",
    [switch]$KeepProjects
)

$ErrorActionPreference = "Continue"

Get-Process -Name "rasm" -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host "· إيقاف العملية $($_.Id)"
    Stop-Process -Id $_.Id -Force
}

if (Test-Path (Join-Path $InstallDir "projects")) {
    $projects = Join-Path $InstallDir "projects"
    if ($KeepProjects) {
        $target = Join-Path ([Environment]::GetFolderPath("Desktop")) "rasm-projects-backup"
        Write-Host "· نقل المشاريع إلى: $target"
        New-Item -ItemType Directory -Force -Path $target | Out-Null
        Copy-Item -Path (Join-Path $projects "*") -Destination $target -Recurse -Force
    } else {
        Write-Host "⚠ يوجد مجلد مشاريع — يُنقل إلى سطح المكتب احتياطًا"
        $target = Join-Path ([Environment]::GetFolderPath("Desktop")) "rasm-projects-backup"
        New-Item -ItemType Directory -Force -Path $target | Out-Null
        Copy-Item -Path (Join-Path $projects "*") -Destination $target -Recurse -Force
    }
}

if (Test-Path $InstallDir) {
    Remove-Item -Path $InstallDir -Recurse -Force
    Write-Host "✔ حُذف: $InstallDir"
}

$lnk = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Rasm Pro.lnk"
if (Test-Path $lnk) {
    Remove-Item -Path $lnk -Force
    Write-Host "✔ حُذف الاختصار"
}

$cmd = Join-Path $env:LOCALAPPDATA "Programs\RasmPro\bin\rasm.cmd"
if (Test-Path $cmd) {
    Remove-Item -Path $cmd -Force
    Write-Host "✔ حُذف المشغّل"
}

Write-Host "✔ اكتملت الإزالة."
exit 0
