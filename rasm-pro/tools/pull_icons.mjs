#!/usr/bin/env node
/**
 * راسم — سحب مكتبة الأيقونات المفتوحة من Iconify مع بوابة ترخيص آلية
 *
 *   node pull_icons.mjs --probe     # عرض المجموعات وتراخيصها وقرار القبول (بدون تحميل)
 *   node pull_icons.mjs             # التحميل الكامل + المانيفست + تصدير SVG للمجموعات الخطية
 *
 * القواعد:
 *  - لا يدخل أصل بلا ترخيص مسموح صريح.
 *  - الترخيص يُقرأ من الكتالوج الرسمي @iconify/collections (المصدر الموثوق).
 *  - يُستبعد كل ما هو علامات تجارية/إيموجي ملوّن (لأسباب قانونية وبصرية).
 *  - التكرار يُستبعد عالميًا ببصمة SHA-256.
 */
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";

const ROOT = "D:/withbord inmation/rasm-pro";
const RAW = path.join(ROOT, "library/raw/iconify");
const SVG_DIR = path.join(ROOT, "library/svg");
const MANIFEST = path.join(ROOT, "library/manifest-icons.jsonl");
const STATS = path.join(ROOT, "library/stats.json");
const CREDITS = path.join(ROOT, "library/CREDITS.md");
const COLLECTIONS_URL = "https://cdn.jsdelivr.net/npm/@iconify/collections/collections.json";
const CDN = (p) => `https://cdn.jsdelivr.net/npm/@iconify-json/${p}/icons.json`;

const OK = new Set(["MIT", "ISC", "Apache-2.0", "CC0-1.0", "Unlicense", "0BSD", "BSD-2-Clause", "BSD-3-Clause", "OFL-1.1"]);
const ATTR = new Set(["CC-BY-4.0", "CC-BY-3.0", "MPL-2.0"]);

// استبعاد: علامات تجارية، إيموجي ملوّن، وشعارات شركات
const EXCLUDE = [
  "simple-icons", "devicon", "devicon-plain", "skill-icons", "logos", "streamline-logos",
  "cib", "fa6-brands", "fa-brands", "fa7-brands", "bxl", "cryptocurrency",
  "cryptocurrency-color", "token", "token-branded", "selfhst", "gcp", "k8s", "unjs",
  "subway", "twemoji", "openmoji", "noto", "noto-v1", "emojione", "emojione-v1",
  "fluent-emoji", "fluent-emoji-flat", "fluent-emoji-high-contrast", "fxemoji",
  "streamline-emojis", "flag", "flagpack", "circle-flags", "cif", "arcticons",
  "file-icons", "vscode-icons", "catppuccin-icons", "tabler-brand", "material-icon-theme",
];

// مجموعات موثوقة المصدر (معروف صاحبها ومستودعها) — البقية تُوسم "review" للفحص قبل الشحن
const TRUSTED = [
  "tabler", "lucide", "lucide-extended", "lucide-lab", "material-symbols",
  "material-symbols-light", "mdi", "mdi-light", "ph", "ri", "iconoir", "bi", "carbon",
  "solar", "mingcute", "majesticons", "fluent", "fluent-mdl2", "basil", "cil",
  "hugeicons", "gravity-ui", "teenyicons", "pixelarticons", "octicon", "fa6-solid",
  "fa6-regular", "fa7-solid", "fa7-regular", "fa-solid", "fa-regular", "fa", "jam",
  "line-md", "quill", "codicon", "icon-park", "icon-park-outline", "icon-park-solid",
  "icon-park-twotone", "heroicons", "heroicons-outline", "heroicons-solid", "feather",
  "clarity", "mage", "akar-icons", "charm", "circum", "uil", "uis", "uit", "bx", "bxs",
  "eva", "ep", "gg", "flowbite", "grommet-icons", "ant-design", "radix-icons",
  "simple-line-icons", "system-uicons", "prime", "oui", "ooui", "foundation",
  "raphael", "bytesize", "maki", "temaki", "game-icons", "healthicons", "medical-icon",
  "academicons", "bpmn", "memory", "pinhead", "whh", "ion", "wi", "la", "f7", "eos-icons",
  "icons8", "zondicons", "fe", "feather", "matita", "humbleicons", "proicons",
  "openmoji", "gis", "map", "meteocons", "covid", "glyphs", "energy-icons",
  "dinkie-icons", "lsicon", "at-icons", "qlementine-icons", "sidekickicons", "famicons",
];

const EXPORT_CAP_PER_SET = 2500; // تصدير SVG للمجموعات الخطية فقط

const probe = process.argv.includes("--probe");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function sha256(s) {
  return crypto.createHash("sha256").update(s).digest("hex");
}
function safeName(n) {
  return n.replace(/[^A-Za-z0-9._-]/g, "_");
}
function bytes(n) {
  return n > 1048576 ? (n / 1048576).toFixed(1) + "MB" : Math.round(n / 1024) + "KB";
}

async function fetchJson(url, tries = 3) {
  for (let i = 0; i < tries; i++) {
    try {
      const r = await fetch(url, { headers: { "user-agent": "rasm-library-builder/1.0" } });
      if (r.status === 429) { await sleep(1500 * (i + 1)); continue; }
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return await r.json();
    } catch (e) {
      if (i === tries - 1) throw e;
      await sleep(800 * (i + 1));
    }
  }
}

function classify(meta) {
  if (meta.palette) return "palette";
  const tags = (meta.tags || []).join(" ").toLowerCase();
  if (tags.includes("uses stroke")) return "stroke";
  return "fill";
}

function buildSvg(json, icon, w, h) {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}">${icon.body}</svg>`;
}

function resolveAlias(json, name, depth = 0) {
  if (depth > 3) return null;
  const al = json.aliases?.[name];
  if (!al) return null;
  const parent = json.icons?.[al.parent] || resolveAlias(json, al.parent, depth + 1);
  if (!parent) return null;
  return { ...parent, ...(al.width ? { width: al.width } : {}), ...(al.height ? { height: al.height } : {}) };
}

async function main() {
  console.log("═══ راسم · باني المكتبة ═══\n");
  const all = await fetchJson(COLLECTIONS_URL);
  const prefixes = Object.keys(all);
  console.log(`الكتالوج: ${prefixes.length} مجموعة متاحة على Iconify\n`);

  const accepted = [];
  const rejected = [];
  for (const p of prefixes) {
    const meta = all[p];
    const spdx = meta?.license?.spdx || "unknown";
    if (EXCLUDE.includes(p)) { rejected.push({ p, spdx, why: "مستبعد (علامة تجارية/إيموجي)" }); continue; }
    if (OK.has(spdx)) accepted.push({ p, meta, spdx, attr: false });
    else if (ATTR.has(spdx)) accepted.push({ p, meta, spdx, attr: true });
    else rejected.push({ p, spdx, why: "ترخيص غير مسموح" });
  }

  if (probe) {
    console.log("المجموعات المقبولة:");
    console.log("prefix".padEnd(26) + "ictr".padStart(7) + "  license".padEnd(14) + "style".padEnd(9) + "total");
    console.log("-".repeat(78));
    let sum = 0;
    for (const { p, meta, spdx, attr } of accepted.sort((a, b) => (b.meta.total || 0) - (a.meta.total || 0))) {
      const t = meta.total || 0; sum += t;
      console.log(p.padEnd(26) + String(t).padStart(7) + "  " + (spdx + (attr ? "*" : "")).padEnd(14) + classify(meta).padEnd(9) + " ");
    }
    console.log("-".repeat(78));
    console.log(`المقبولة: ${accepted.length} مجموعة | إجمالي الأيقونات: ${sum}`);
    console.log(`المرفوضة: ${rejected.length}`);
    const why = {};
    for (const r of rejected) why[r.why] = (why[r.why] || 0) + 1;
    console.log("أسباب الرفض:", JSON.stringify(why, null, 0));
    return;
  }

  // ===== التحميل =====
  fs.mkdirSync(RAW, { recursive: true });
  fs.mkdirSync(SVG_DIR, { recursive: true });

  const manifest = fs.createWriteStream(MANIFEST, { flags: "w" });
  const stats = { generatedAt: new Date().toISOString(), source: COLLECTIONS_URL, sets: [], totals: {} };
  const seen = new Map();
  let totalIcons = 0, exported = 0, dupes = 0;
  const credits = new Map();

  const CONC = 6;
  for (let i = 0; i < accepted.length; i += CONC) {
    const chunk = accepted.slice(i, i + CONC);
    const got = await Promise.all(chunk.map(async (s) => {
      try {
        const json = await fetchJson(CDN(s.p));
        return { ...s, json };
      } catch (e) {
        console.log(`  ✗ ${s.p}: ${e.message}`);
        return null;
      }
    }));
    for (const item of got) {
      if (!item) continue;
      const { p, meta, spdx, attr, json } = item;
      const defW = json.width || meta.height || 24;
      const defH = json.height || meta.height || 24;
      const cat = classify(meta);
      const rawFile = path.join(RAW, safeName(p) + ".json");
      fs.writeFileSync(rawFile, JSON.stringify(json));

      let setCount = 0, setExport = 0, setDup = 0;
      const exportThisSet = cat === "stroke" && !EXCLUDE.includes(p);
      const outDir = path.join(SVG_DIR, safeName(p));
      if (exportThisSet) fs.mkdirSync(outDir, { recursive: true });

      const emit = (name, icon, aliasOf) => {
        if (!icon?.body) return;
        const w = icon.width || defW, h = icon.height || defH;
        const svg = buildSvg(json, icon, w, h);
        const hash = sha256(svg);
        const id = `${p}/${name}`;
        if (seen.has(hash)) { setDup++; dupes++; return; }
        seen.set(hash, id);
        setCount++; totalIcons++;
        let outFile = null;
        if (exportThisSet && setExport < EXPORT_CAP_PER_SET) {
          outFile = `svg/${safeName(p)}/${safeName(name)}.svg`;
          fs.writeFileSync(path.join(SVG_DIR, safeName(p), safeName(name) + ".svg"), svg);
          setExport++; exported++;
        }
        manifest.write(JSON.stringify({
          id, prefix: p, name, aliasOf: aliasOf || null, style: cat,
          trust: TRUSTED.includes(p) ? "core" : "review",
          license: spdx, attrRequired: attr, licenseUrl: meta?.license?.url || null,
          setName: meta?.name || p, source: `@iconify-json/${p}`,
          canvas: [w, h], bytes: svg.length, sha256: hash,
          file: outFile, tags: [], status: "raw",
        }) + "\n");
      };

      for (const [name, icon] of Object.entries(json.icons || {})) {
        if (icon.hidden) continue;
        emit(name, icon, null);
      }
      for (const name of Object.keys(json.aliases || {})) {
        const icon = resolveAlias(json, name);
        if (icon) emit(name, icon, json.aliases[name]?.parent || null);
      }

      credits.set(p, { spdx, title: meta?.license?.title, url: meta?.license?.url, name: meta?.name, total: setCount });
      stats.sets.push({ prefix: p, name: meta?.name, license: spdx, attr, style: cat, trust: TRUSTED.includes(p) ? "core" : "review", icons: setCount, exported: setExport, dupes: setDup });
      console.log(`  ✓ ${p.padEnd(24)} ${String(setCount).padStart(6)} أيقونة  |  SVG: ${String(setExport).padStart(5)}  |  ${spdx}`);
    }
  }

  await new Promise((res) => manifest.end(res));
  stats.totals = {
    sets: stats.sets.length,
    icons: totalIcons,
    exportedSvg: exported,
    dedupedOut: dupes,
    strokeSets: stats.sets.filter((s) => s.style === "stroke").length,
    fillSets: stats.sets.filter((s) => s.style === "fill").length,
    paletteSets: stats.sets.filter((s) => s.style === "palette").length,
    coreSets: stats.sets.filter((s) => s.trust === "core").length,
    reviewSets: stats.sets.filter((s) => s.trust === "review").length,
  };
  fs.writeFileSync(STATS, JSON.stringify(stats, null, 2));

  const cl = [
    "# نسب المصادر (CREDITS) — إلزامي عرضه في «عن البرنامج»",
    "",
    `تم التوليد آليًا — ${new Date().toISOString()}`,
    "",
    "| المجموعة | الاسم | الترخيص | الرابط | عدد الأصول |",
    "|---|---|---|---|---|",
  ];
  for (const [p, c] of [...credits.entries()].sort()) {
    cl.push(`| ${p} | ${c.name || ""} | ${c.spdx}${c.title && c.title !== c.spdx ? " (" + c.title + ")" : ""} | ${c.url || ""} | ${c.total} |`);
  }
  fs.writeFileSync(CREDITS, cl.join("\n") + "\n");

  console.log("\n══════════ النتيجة ══════════");
  console.log(`مجموعات: ${stats.totals.sets}  |  أيقونات: ${stats.totals.icons}`);
  console.log(`ملفات SVG جاهزة: ${exported}  |  مكرر مستبعد: ${dupes}`);
  console.log(`خطية (Uses Stroke): ${stats.totals.strokeSets} مجموعة  |  مصمتة: ${stats.totals.fillSets}  |  ملوّنة: ${stats.totals.paletteSets}`);
  console.log(`\nالمانيفست: ${MANIFEST}`);
  console.log(`الإحصاءات: ${STATS}`);
  console.log(`النسب: ${CREDITS}`);
}

main().catch((e) => { console.error("فشل:", e); process.exit(1); });
