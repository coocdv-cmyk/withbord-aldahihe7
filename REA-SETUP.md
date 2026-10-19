# REA — حالة التسطيب على الجهاز

آخر تحديث: 2026-10-18

## مكان الريبو

- الريبو الكامل (بكل الساب-موديولز): `D:\withbord inmation\rea`
- الفرع/الكوميت: `main` @ `c12d9eda8` — الإصدار `rea-agents@6.7.0`
- `rea` مربوط جلوباليًا بـ npm link (junction)، فالنسخة الشغّالة هي نفسها نسخة الريبو مباشرة.

```
rea.cmd --version      # 6.7.0
rea.cmd --help         # قائمة الأوامر الكاملة
```

ملاحظة: سياسة PowerShell عندك تمنع تشغيل `rea.ps1` — استخدم `rea.cmd` أو غيّر السياسة:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

## البناء والتشغيل

```
cd "D:\withbord inmation\rea"
npm.cmd ci
npm.cmd run build:cached      # compile + skills
npm.cmd run verify:windows-native   # تحقق طبقة ويندوز الأصلية (نجح ok:true)
```

ناتج البناء: `dist/` و `skills/` (كلاهما متجاهَل في git).

## المحركات والأدوات المثبّتة

| الأداة | المسار | ملاحظات |
| --- | --- | --- |
| Ghidra 12.1.4 | `C:\tools\ghidra_12.1.4_PUBLIC` | المحرك الأساسي للتحليل الأصلي (تحليل ثابت، بدون تنفيذ) |
| Temurin JDK 21 | `C:\tools\jdk-21` | مطلوب لـ Ghidra و JADX |
| JADX headless MCP 0.7.1 | `%USERPROFILE%\.local\share\rea\android\jadx-headless-mcp-0.7.1-all.jar` | APK/DEX/JAR — البصمة SHA-256 متحققة |
| Android platform-tools (adb 37.0.1) | `C:\tools\platform-tools` | تحليل أجهزة/محاكيات أندرويد |
| Apktool 3.0.3 | `C:\tools\apktool` | لودر `apktool.bat` + `apktool.jar` |
| Wireshark/TShark 4.6.9 | `C:\Program Files\Wireshark` | تحليل pcap/pcapng |
| Chrome + Edge | مثبتان مسبقًا | تحليل المواقع عبر Playwright/CDP |

غير متاح على ويندوز: Hopper (ماك/لينكس فقط)، IDA Pro (يحتاج ترخيص منك)، Kuna (اختياري).

## متغيرات البيئة (مستوى المستخدم)

```
JAVA_HOME              = C:\tools\jdk-21
GHIDRA_INSTALL_DIR     = C:\tools\ghidra_12.1.4_PUBLIC
REA_JADX_MCP_JAR       = C:\Users\USER\.local\share\rea\android\jadx-headless-mcp-0.7.1-all.jar
REA_APKTOOL_COMMAND    = C:\tools\apktool\apktool.bat
REA_ADB_PATH           = C:\tools\platform-tools\adb.exe
REA_TSHARK_COMMAND     = C:\Program Files\Wireshark\tshark.exe
REA_CAPINFOS_COMMAND   = C:\Program Files\Wireshark\capinfos.exe
REA_ANALYSIS_PROVIDER  = ghidra
PATH += C:\tools\jdk-21\bin; C:\tools\platform-tools; C:\tools\apktool; C:\Program Files\Wireshark
```

## ربط الوكلاء (MCP + Skill)

`rea setup --yes --all-detected` طبّق على:

- OpenCode → `C:\Users\USER\.config\opencode\opencode.json`
- Codex → `C:\Users\USER\.codex\config.toml`
- ZCode → `C:\Users\USER\.zcode\cli\config.json`
- DeepSeek Harness → `C:\Users\USER\.dsh\cordis.patch.yml`
- Skill → `C:\Users\USER\.agents\skills\reverse-engineer-anything` (+ نسخة zcode)

كل تسجيل له نسخة احتياطية بجانبه بلاحقة `.rea.backup`.
كل التسجيلات `aligned` والـ skill `aligned` (v42، 207 أداة).

**مهم:** أعِد تشغيل الوكلاء بعد أي تغيير في متغيرات البيئة/الـ PATH، لأن عمليات الـ MCP بتورّث بيئة العميل الأب.

## تحقق عملي تم فعليًا

- `rea doctor` → `healthy: true` / `environment_healthy: true`
- Ghidra على ويندوز: فتح PE (winver.exe) → جرد 9 مقاطع، 63 دالة، 76 نص → استخراج pseudocode لدالة `entry` مع Assembly و callees.
- `npm run verify:windows-native` → `ok: true` (كل ضوابط DACL/Job Object/التنظيف).
- `analyze-javascript-application` على حزمة JS محلية → Evidence كامل.
- فحص عملاء adb / apktool / tshark → كلهم اتعرّفوا بنجاح.

## الاستخدام السريع

```
# تحليل ثابت لملف تنفيذي
rea.cmd inspect "TARGET.exe" --provider ghidra --format json

# تفكيك دالة
rea.cmd function "TARGET.exe" <address|symbol>

# تطبيق JavaScript/Electron
rea.cmd analyze-javascript-application "PATH" --json

# APK
rea.cmd inspect-android-package "app.apk" --json

# pcap
rea.cmd inspect-pcap-capture "capture.pcapng"
```

للمهام الكبيرة: `REA_GHIDRA_STARTUP_TIMEOUT_MS=600000` لو البدء بياخد وقت.
