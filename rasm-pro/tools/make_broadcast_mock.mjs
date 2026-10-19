#!/usr/bin/env node
/**
 * راسم — نموذج «ستايل البثّ الإخباري» (Broadcast News Style)
 * يبني صفحة HTML حيّة: هل يُمكن للتطبيق أن يعمل بأسلوب قنوات الأخبار؟
 * يستخدم أصولًا حقيقية من مكتبتنا (SVG) ويرسمها بحركة القلم (Stroke Reveal).
 */
import fs from "node:fs";
import path from "node:path";
import readline from "node:readline";

const ROOT = "D:/withbord inmation/rasm-pro";
const LIB = path.join(ROOT, "library");
const MANIFEST = path.join(LIB, "manifest-icons.jsonl");
const OUT = process.argv[2] || "C:/Users/USER/AppData/Local/Temp/opencode/rasm-broadcast-mock.html";

const PREFER = ["tabler", "lucide", "ph", "iconoir", "carbon", "bi", "mynaui", "mingcute"];

const WANT = [
  "world", "chart-bar", "trending-up", "building", "users", "speakerphone",
  "bulb", "rocket", "cpu", "coin", "car", "microphone", "briefcase",
  "map-2", "globe", "presentation", "chart-pie", "arrow-up-right",
];

const LABELS = {
  world: "الاقتصاد العالمي",
  "chart-bar": "أرقام السوق",
  "trending-up": "نمو متصاعد",
  users: "المستخدمون",
  cpu: "الذكاء الاصطناعي",
  coin: "الاستثمار",
  globe: "الأسواق العالمية",
  building: "الشركات",
};

async function pickIcons() {
  const rl = readline.createInterface({ input: fs.createReadStream(MANIFEST), crlfDelay: Infinity });
  const found = {};
  for await (const line of rl) {
    if (!line.trim()) continue;
    let r;
    try { r = JSON.parse(line); } catch { continue; }
    if (r.style !== "stroke" || r.trust !== "core" || !r.file) continue;
    const n = r.name.toLowerCase();
    if (!WANT.includes(n)) continue;
    const score = PREFER.includes(r.prefix) ? PREFER.indexOf(r.prefix) : 99;
    if (!found[n] || score < found[n].score) found[n] = { ...r, score };
  }
  return found;
}

function inlineSvg(svg, delayStart, strokeW) {
  let i = 0;
  svg = svg.replace(/<svg[^>]*>/, "").replace(/<\/svg>/, "");
  svg = svg.replace(/<(path|circle|rect|line|polyline|polygon|ellipse)\b/g, (m, tag) => {
    const d = (delayStart + i * 0.28).toFixed(2);
    i++;
    return `<${tag} pathLength="1" style="animation-delay:${d}s" data-s="${strokeW}"`;
  });
  return svg;
}

async function main() {
  const icons = await pickIcons();
  const order = ["world", "chart-bar", "trending-up", "users", "cpu", "coin", "building", "globe"];
  const chosen = order.filter((k) => icons[k]);
  console.log("الأصول المستخدمة:", chosen.map((c) => `${c} (${icons[c].prefix})`).join(" · "));

  const cards = chosen.map((key, idx) => {
    const svg = fs.readFileSync(path.join(LIB, icons[key].file.replace(/\//g, path.sep)), "utf8");
    const inner = inlineSvg(svg, 1.1 + idx * 1.15, 1.7);
    const label = LABELS[key] || key;
    return `<figure class="art"><div class="pic">${inner}</div><figcaption>${label}</figcaption></figure>`;
  }).join("\n");

  const html = `<!DOCTYPE html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8">
<title>راسم — نموذج ستايل البثّ الإخباري</title>
<style>
  :root{ --navy:#0B1220; --navy2:#111C33; --red:#C8102E; --paper:#FFFFFF;
         --ink:#0F172A; --gold:#E8B23A; --tick:#F1F5F9; }
  *{ box-sizing:border-box; }
  body{ margin:0; min-height:100vh; display:flex; align-items:center; justify-content:center;
        background:#05070D; font-family:"Segoe UI",Tahoma,sans-serif; color:#fff; padding:20px; }
  .frame{ position:relative; width:min(1280px,96vw); aspect-ratio:16/9; background:var(--navy);
          border-radius:14px; overflow:hidden; box-shadow:0 30px 80px rgba(0,0,0,.6),0 0 0 1px #22304d;
          background-image:radial-gradient(1200px 600px at 70% 10%, #16233d 0%, #0B1220 60%); }
  /* ===== الشريط العلوي: العنوان الرئيسي ===== */
  .topbar{ position:absolute; inset:0 0 auto 0; height:13.5%; display:flex; align-items:center; gap:18px;
           background:linear-gradient(90deg,var(--red) 0 24%, rgba(200,16,46,0) 24.2%),
                      linear-gradient(90deg,#0E1830 0%,#132242 100%);
           border-bottom:3px solid var(--gold); padding:0 26px; }
  .kicker{ background:#fff; color:var(--red); font-weight:800; font-size:clamp(13px,1.5vw,22px);
           padding:6px 16px; border-radius:6px; letter-spacing:.5px; }
  .headline{ font-size:clamp(16px,2.3vw,34px); font-weight:800; white-space:nowrap; overflow:hidden;
             text-overflow:ellipsis; }
  .clock{ margin-inline-start:auto; font-weight:700; font-size:clamp(12px,1.4vw,20px); color:#cbd5e1;
          border-inline-start:2px solid #334155; padding-inline-start:16px; direction:ltr; }
  /* ===== لوح الوايت بورد ===== */
  .board{ position:absolute; right:4.5%; top:19%; width:62%; height:58%; background:var(--paper);
          border-radius:10px; box-shadow:0 18px 40px rgba(0,0,0,.45); padding:3.2% 3.4% 2.4%;
          background-image:linear-gradient(rgba(15,23,42,.035) 1px,transparent 1px),
                           linear-gradient(90deg,rgba(15,23,42,.035) 1px,transparent 1px);
          background-size:26px 26px; }
  .grid{ display:grid; grid-template-columns:repeat(4,1fr); gap:2%; height:100%; }
  .art{ margin:0; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:6px; }
  .pic{ width:100%; aspect-ratio:1/1; display:flex; align-items:center; justify-content:center; }
  .pic svg{ width:100%; height:100%; }
  .pic [pathLength]{ fill:none; stroke:var(--ink); stroke-width:1.7; stroke-linecap:round; stroke-linejoin:round;
                     stroke-dasharray:1; stroke-dashoffset:1; animation:draw .9s cubic-bezier(.35,0,.2,1) forwards; }
  @keyframes draw{ to{ stroke-dashoffset:0 } }
  figcaption{ color:#0f172a; font-weight:700; font-size:clamp(10px,1vw,15px); }
  /* ===== اللوحة الجانبية: أرقام ===== */
  .panel{ position:absolute; left:4.5%; top:19%; width:26%; height:58%; background:linear-gradient(180deg,#101A31,#0C1526);
          border:1px solid #22304d; border-radius:10px; padding:3% 3%; display:flex; flex-direction:column; gap:4%; }
  .panel h3{ margin:0; font-size:clamp(11px,1.1vw,16px); color:#93A4C4; font-weight:700; letter-spacing:.4px; }
  .row{ display:flex; flex-direction:column; gap:6px; }
  .row .lbl{ display:flex; justify-content:space-between; font-size:clamp(10px,.95vw,14px); color:#DCE6F8; }
  .row .lbl b{ color:var(--gold); direction:ltr; }
  .bar{ height:9px; border-radius:6px; background:#1E2A45; overflow:hidden; }
  .bar i{ display:block; height:100%; width:0; border-radius:6px; background:linear-gradient(90deg,var(--red),var(--gold));
          animation:grow 1.2s cubic-bezier(.2,.8,.2,1) forwards; }
  @keyframes grow{ to{ width:var(--w) } }
  .badge-live{ position:absolute; left:4.5%; bottom:26%; display:flex; align-items:center; gap:10px;
               background:var(--red); padding:8px 16px; border-radius:6px; font-weight:800;
               font-size:clamp(11px,1.2vw,18px); box-shadow:0 10px 24px rgba(200,16,46,.45); }
  .dot{ width:10px; height:10px; border-radius:50%; background:#fff; animation:pulse 1.1s infinite; }
  @keyframes pulse{ 50%{ opacity:.15 } }
  /* ===== الشريط السفلي: الاسم + الزحّافة ===== */
  .lower{ position:absolute; inset:auto 4.5% 12.5% 4.5%; display:flex; align-items:stretch; gap:0;
          box-shadow:0 14px 34px rgba(0,0,0,.5); border-radius:8px; overflow:hidden;
          transform:translateY(140%); animation:rise .6s .5s cubic-bezier(.2,.9,.2,1) forwards; }
  @keyframes rise{ to{ transform:translateY(0) } }
  .lower .who{ background:var(--red); padding:10px 20px; font-weight:800; font-size:clamp(12px,1.3vw,19px);
               display:flex; align-items:center; }
  .lower .what{ background:#0E1830F2; padding:10px 20px; display:flex; align-items:center;
                color:#D7E2F7; font-size:clamp(11px,1.15vw,17px); flex:1; }
  .ticker{ position:absolute; inset:auto 0 0 0; height:12.5%; background:var(--tick); color:#0B1220;
           display:flex; align-items:center; overflow:hidden; border-top:3px solid var(--red); }
  .ticker .tag{ background:var(--red); color:#fff; height:100%; display:flex; align-items:center;
                padding:0 22px; font-weight:800; font-size:clamp(12px,1.3vw,19px); flex:0 0 auto;
                clip-path:polygon(0 0,100% 0,92% 100%,0 100%); }
  .track{ display:flex; gap:60px; white-space:nowrap; animation:slide 26s linear infinite;
          font-weight:600; font-size:clamp(12px,1.35vw,20px); padding-inline-start:40px; }
  @keyframes slide{ to{ transform:translateX(60%) } }
  .logo{ position:absolute; left:4.5%; top:15.6%; background:#0B1220; border:1px solid #2A3A5C;
         border-radius:999px; padding:6px 18px; font-weight:800; letter-spacing:1px; font-size:clamp(11px,1.1vw,17px); }
  .note{ position:absolute; right:4.5%; bottom:14.5%; color:#8FA2C2; font-size:clamp(9px,.85vw,13px); }
</style></head>
<body>
<div class="frame">
  <div class="topbar">
    <span class="kicker">عاجل</span>
    <span class="headline">لماذا تتسارع أسواق الذكاء الاصطناعي في 2026؟ — تحليل بالأرقام</span>
    <span class="clock">21:45:07</span>
  </div>

  <div class="logo">راسم · نمط البثّ</div>

  <div class="board">
    <div class="grid">${cards}</div>
  </div>

  <div class="panel">
    <h3>مؤشرات الأداء (نمو سنوي)</h3>
    <div class="row"><span class="lbl"><span>سوق النماذج</span><b>+38%</b></span>
      <span class="bar"><i style="--w:88%;animation-delay:.9s"></i></span></div>
    <div class="row"><span class="lbl"><span>الاستثمار في الشرائح</span><b>+54%</b></span>
      <span class="bar"><i style="--w:96%;animation-delay:1.15s"></i></span></div>
    <div class="row"><span class="lbl"><span>المستخدمون العرب</span><b>+71%</b></span>
      <span class="bar"><i style="--w:74%;animation-delay:1.4s"></i></span></div>
    <div class="row"><span class="lbl"><span>المحتوى المرئي</span><b>+29%</b></span>
      <span class="bar"><i style="--w:61%;animation-delay:1.65s"></i></span></div>
  </div>

  <div class="badge-live"><span class="dot"></span> مباشر الآن</div>

  <div class="lower">
    <span class="who">تحليل خاص</span>
    <span class="what">كيف تصنع المعالجة العربية الفرق في محركات الفيديو — تقرير ميداني</span>
  </div>

  <div class="ticker">
    <span class="tag">الأخبار</span>
    <span class="track">
      <span>◆ المكتبة: 318,823 أصلًا موثّق الترخيص بالكامل</span>
      <span>◆ الرسم يتم بخط اليد على الشاشة — بلا صور جاهزة</span>
      <span>◆ تصدير محلي 4K · 60 إطارًا · عربي أولًا</span>
      <span>◆ 8 أنماط بصرية جاهزة + أنماط مخصّصة</span>
    </span>
  </div>

  <div class="note">نموذج تصميمي (ليس علامة تجارية) — الأصول من مكتبتنا مفتوحة الترخيص</div>
</div>
</body></html>`;

  fs.writeFileSync(OUT, html);
  console.log("تم:", OUT);
}

main().catch((e) => { console.error("فشل:", e); process.exit(1); });
