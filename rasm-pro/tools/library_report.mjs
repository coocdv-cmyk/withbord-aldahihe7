#!/usr/bin/env node
/**
 * راسم — تقرير المكتبة + ورقة المراجعة البصرية (Contact Sheet)
 *
 *   node library_report.mjs                      # تقرير إحصائي فقط
 *   node library_report.mjs --sheet 96 --out sheet.html
 *                                                # توليد ورقة مراجعة HTML مستقلة (SVG مضمّن)
 */
import fs from "node:fs";
import path from "node:path";
import readline from "node:readline";

const ROOT = "D:/withbord inmation/rasm-pro";
const LIB = path.join(ROOT, "library");
const MANIFEST = path.join(LIB, "manifest-icons.jsonl");
const STATS = path.join(LIB, "stats.json");

function arg(name, def) {
  const i = process.argv.indexOf("--" + name);
  return i >= 0 ? process.argv[i + 1] : def;
}

async function readManifest() {
  const rl = readline.createInterface({ input: fs.createReadStream(MANIFEST), crlfDelay: Infinity });
  const rows = [];
  for await (const line of rl) {
    if (!line.trim()) continue;
    try { rows.push(JSON.parse(line)); } catch { /* تجاهل */ }
  }
  return rows;
}

function walk(dir) {
  let files = 0, bytes = 0;
  const stack = [dir];
  while (stack.length) {
    const d = stack.pop();
    let ents = [];
    try { ents = fs.readdirSync(d, { withFileTypes: true }); } catch { continue; }
    for (const e of ents) {
      const p = path.join(d, e.name);
      if (e.isDirectory()) stack.push(p);
      else { files++; try { bytes += fs.statSync(p).size; } catch {} }
    }
  }
  return { files, bytes };
}

function fmtBytes(n) {
  if (n > 1073741824) return (n / 1073741824).toFixed(2) + " GB";
  if (n > 1048576) return (n / 1048576).toFixed(1) + " MB";
  return Math.round(n / 1024) + " KB";
}

function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

async function main() {
  const sheetN = parseInt(arg("sheet", "0"), 10);
  const outFile = arg("out", path.join(LIB, "review", "sheet.html"));

  console.log("═══ راسم · تقرير المكتبة ═══\n");
  const rows = await readManifest();
  console.log(`سطور المانيفست: ${rows.length.toLocaleString("en")}`);
  console.log(`مجموعات فريدة: ${new Set(rows.map(r => r.prefix)).size}`);

  const byStyle = {}, byLicense = {}, byTrust = {}, bySet = {};
  for (const r of rows) {
    byStyle[r.style] = (byStyle[r.style] || 0) + 1;
    byLicense[r.license] = (byLicense[r.license] || 0) + 1;
    byTrust[r.trust] = (byTrust[r.trust] || 0) + 1;
    bySet[r.prefix] = (bySet[r.prefix] || 0) + 1;
  }
  console.log("\nبالأسلوب:", JSON.stringify(byStyle));
  console.log("بالترخيص:", JSON.stringify(byLicense));
  console.log("بالثقة:", JSON.stringify(byTrust));

  const top = Object.entries(bySet).sort((a, b) => b[1] - a[1]).slice(0, 15);
  console.log("\nأكبر 15 مجموعة:");
  for (const [p, n] of top) console.log(`  ${p.padEnd(24)} ${String(n).padStart(7)}`);

  const svgDir = path.join(LIB, "svg");
  if (fs.existsSync(svgDir)) {
    const { files, bytes } = walk(svgDir);
    console.log(`\nملفات SVG على القرص: ${files.toLocaleString("en")}  |  ${fmtBytes(bytes)}`);
  }
  if (fs.existsSync(STATS)) {
    const st = JSON.parse(fs.readFileSync(STATS, "utf8"));
    console.log("الإجماليات:", JSON.stringify(st.totals));
  }

  if (!sheetN) return;

  // ===== ورقة المراجعة البصرية =====
  const cand = rows.filter(r => r.file && r.style === "stroke" && r.trust === "core");
  const byP = {};
  for (const r of cand) (byP[r.prefix] ||= []).push(r);
  const order = Object.entries(byP).sort((a, b) => b[1].length - a[1].length);
  const picked = [];
  let i = 0;
  while (picked.length < sheetN) {
    let added = false;
    for (const [, list] of order) {
      if (i < list.length && picked.length < sheetN) { picked.push(list[i]); added = true; }
    }
    if (!added) break;
    i++;
  }

  const cells = [];
  for (const r of picked) {
    const p = path.join(LIB, r.file.replace(/\//g, path.sep));
    let svg = "";
    try {
      svg = fs.readFileSync(p, "utf8");
      svg = svg.replace(/ width="[^"]*" height="[^"]*"/, ' width="100%" height="100%"');
    } catch {
      svg = `<div style="color:#c00;font-size:10px">ملف مفقود</div>`;
    }
    cells.push(`<figure class="cell"><div class="art">${svg}</div><figcaption><b>${esc(r.name)}</b><span>${esc(r.prefix)}</span></figcaption></figure>`);
  }

  const html = `<!DOCTYPE html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8">
<title>راسم — مراجعة المكتبة (${cells.length} أصلًا)</title>
<style>
  :root { --ink:#111827; --line:#e5e7eb; --bg:#f8fafc; }
  * { box-sizing: border-box; }
  body { margin:0; padding:24px; background:var(--bg); color:var(--ink);
         font-family: "Segoe UI", Tahoma, sans-serif; }
  header { display:flex; align-items:baseline; gap:16px; flex-wrap:wrap; margin-bottom:8px; }
  h1 { font-size:22px; margin:0; }
  .meta { color:#64748b; font-size:13px; }
  .legend { margin:10px 0 20px; display:flex; gap:14px; flex-wrap:wrap; font-size:12px; color:#475569; }
  .grid { display:grid; grid-template-columns: repeat(12, 1fr); gap:10px; }
  .cell { margin:0; background:#fff; border:1px solid var(--line); border-radius:10px;
          padding:8px 6px 4px; display:flex; flex-direction:column; align-items:center;
          color:var(--ink); }
  .art { width:100%; aspect-ratio:1/1; display:flex; align-items:center; justify-content:center; padding:6px; }
  .art svg { width:100%; height:100%; }
  figcaption { width:100%; text-align:center; margin-top:4px; line-height:1.25; }
  figcaption b { display:block; font-size:10px; font-weight:600; color:#0f172a;
                 white-space:nowrap; overflow:hidden; text-overflow:ellipsis; direction:ltr; }
  figcaption span { display:block; font-size:9px; color:#94a3b8; direction:ltr; }
  @media (max-width:1200px){ .grid { grid-template-columns: repeat(8,1fr); } }
  @media (max-width:800px){ .grid { grid-template-columns: repeat(5,1fr); } }
</style></head><body>
<header>
  <h1>راسم · ورقة مراجعة المكتبة</h1>
  <span class="meta">${cells.length} أصلًا · مجموعات خطية موثوقة · مرسومة بخط موحّد (Stroke)</span>
</header>
<div class="legend">
  <span>✅ كل الأصول بترخيص تجاري صريح (MIT · Apache · ISC · CC0 · OFL · CC-BY مع نسبة)</span>
  <span>🎯 العرض بخط أسود موحّد — الألوان تُضاف عند الرسم</span>
  <span>📋 الأسماء للمراجعة فقط، ولن تظهر للمستخدم</span>
</div>
<div class="grid">${cells.join("\n")}</div>
</body></html>`;

  fs.mkdirSync(path.dirname(outFile), { recursive: true });
  fs.writeFileSync(outFile, html);
  console.log(`\nورقة المراجعة: ${outFile}  (${cells.length} أصلًا)`);
  console.log(`المجموعات الممثلة: ${new Set(picked.map(p => p.prefix)).size}`);
}

main().catch(e => { console.error("فشل:", e); process.exit(1); });
