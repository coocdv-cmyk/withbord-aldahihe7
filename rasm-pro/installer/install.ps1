<#
.SYNOPSIS
    تثبيت محرّك راسم على جهاز Windows (محلي بالكامل — بلا سحابة وبلا اشتراك).
.DESCRIPTION
    ينسخ حزمة المحرّك إلى مجلد التثبيت، ويكتب سجلّ البصمات، وينشئ اختصارًا
    في قائمة «ابدأ».  لا يُثبَّت أي服务 ولا يُعدَّل النظام إلا اختصارًا.
.PARAMETER InstallDir
    مجلد التثبيت (افتراضيًا: %LOCALAPPDATA%\Programs\RasmPro).
.PARAMETER NoShortcuts
    تخطّي اختصار قائمة «ابدأ».
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File install.ps1
#>
param(
    [string]$InstallDir = "$env:LOCALAPPDATA\Programs\RasmPro",
    [switch]$NoShortcuts
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$payload = Join-Path $here "rasm"

if (-not (Test-Path $payload)) {
    Write-Host "✘ لا توجد حزمة المحرّك بجوار المثبّت: $payload" -ForegroundColor Red
    exit 2
}

Write-Host "· التثبيت في: $InstallDir"
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

# نسخ المحتوى (لا يُحذف شيء من مجلد الوجود إلا محتويات الحزمة)
Get-ChildItem -Path $payload -Force | ForEach-Object {
    Copy-Item -Path $_.FullName -Destination $InstallDir -Recurse -Force
}

# سجل البصمات: ما ثُبِّت بالضبط (يصلح للتحقق لاحقًا)
$manifest = Join-Path $InstallDir "MANIFEST.sha256"
$lines = Get-ChildItem -Path $InstallDir -Recurse -File |
    Where-Object { $_.Name -ne "MANIFEST.sha256" } |
    ForEach-Object {
        $hash = (Get-FileHash -Path $_.FullName -Algorithm SHA256).Hash.ToLower()
        $rel = $_.FullName.Substring($InstallDir.Length).TrimStart('\').Replace('\', '/')
        "$hash  $rel"
    }
$lines | Set-Content -Path $manifest -Encoding ASCII
Write-Host "✔ سجل البصمات: $manifest ($($lines.Count) ملفًا)"

# مشغّل على PATH (اختياري)
$binDir = Join-Path $env:LOCALAPPDATA "Programs\RasmPro\bin"
New-Item -ItemType Directory -Force -Path $binDir | Out-Null
$cmd = @"
@echo off
setlocal
set "RASM_HOME=%LOCALAPPDATA%\Programs\RasmPro"
"%LOCALAPPDATA%\Programs\RasmPro\rasm.exe" %*
"@
Set-Content -Path (Join-Path $binDir "rasm.cmd") -Value $cmd -Encoding ASCII
Write-Host "✔ المشغّل: $binDir\rasm.cmd"

if (-not $NoShortcuts) {
    $startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
    $lnk = Join-Path $startMenu "Rasm Pro.lnk"
    try {
        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut($lnk)
        $shortcut.TargetPath = Join-Path $InstallDir "rasm.exe"
        $shortcut.WorkingDirectory = $InstallDir
        $shortcut.Description = "محرّك راسم — فيديو وايت بورد"
        $shortcut.Save()
        Write-Host "✔ الاختصار: $lnk"
    } catch {
        Write-Host "⚠ تعذّر إنشاء الاختصار (لا يهمّ التثبيت): $_"
    }
}

Write-Host ""
Write-Host "✔ التثبيت مكتمل. جرّب:"
Write-Host "   & `"$InstallDir\rasm.exe`" --help"
Write-Host "   & `"$binDir\rasm.cmd`" --help"
exit 0
