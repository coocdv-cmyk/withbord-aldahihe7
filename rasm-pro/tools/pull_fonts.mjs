#!/usr/bin/env node
/**
 * pull_fonts.mjs — يسحب خطوط OFL/Apache من مستودع google/fonts
 * - يستخدم GitHub Contents API لمعرفة الملفات الفعلية (يتعامل مع الخطوط المتغيرة [wght])
 * - ينزّل ملفات .ttf فقط + ملف الترخيص (OFL.txt)
 * - يكتب manifest: assets/fonts/fonts.json
 *
 * التشغيل: node tools/pull_fonts.mjs
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const OUT = path.join(ROOT, 'assets', 'fonts');
fs.mkdirSync(OUT, { recursive: true });

// العائلات المطلوبة (مجلد داخل ofl/ أو apache/)
const FAMILIES = [
  // === عربي: عناوين خطية/كوفية ===
  ['arefruqaa', 'Aref Ruqaa'],
  ['arefruqaaink', 'Aref Ruqaa Ink'],
  ['reemkufi', 'Reem Kufi'],
  ['notokufiarabic', 'Noto Kufi Arabic'],
  ['alexandria', 'Alexandria'],
  ['kufam', 'Kufam'],
  ['elmessiri', 'El Messiri'],
  ['rakkas', 'Rakkas'],
  ['jomhuria', 'Jomhuria'],
  ['mada', 'Mada'],
  // === عربي: نصوص وقراءة ===
  ['amiri', 'Amiri'],
  ['notonaskharabic', 'Noto Naskh Arabic'],
  ['scheherazadenew', 'Scheherazade New'],
  ['lateef', 'Lateef'],
  ['harmattan', 'Harmattan'],
  ['notosansarabic', 'Noto Sans Arabic'],
  ['cairo', 'Cairo'],
  ['tajawal', 'Tajawal'],
  ['almarai', 'Almarai'],
  ['changa', 'Changa'],
  ['lemonada', 'Lemonada'],
  ['markazitext', 'Markazi Text'],
  ['readexpro', 'Readex Pro'],
  ['ibmplexsansarabic', 'IBM Plex Sans Arabic'],
  ['baloobhaijaan2', 'Baloo Bhaijaan 2'],
  ['marhey', 'Marhey'],
  ['katibeh', 'Katibeh'],
  ['qahiri', 'Qahiri'],
  ['lalezar', 'Lalezar'],
  ['gulzar', 'Gulzar'],
  ['alkalami', 'Alkalami'],
  // === لاتيني: عناوين/بيانات/آلة كاتبة ===
  ['archivo', 'Archivo'],
  ['oswald', 'Oswald'],
  ['bebasneue', 'Bebas Neue'],
  ['anton', 'Anton'],
  ['spacegrotesk', 'Space Grotesk'],
  ['specialelite', 'Special Elite'],
  ['courierprime', 'Courier Prime'],
  ['sourcecodepro', 'Source Code Pro'],
  ['inter', 'Inter'],
];

const LIC_DIRS = ['ofl', 'apache', 'ufl'];
const API = 'https://api.github.com/repos/google/fonts/contents';
const RAW = 'https://raw.githubusercontent.com/google/fonts/main';

async function getJSON(url) {
  const r = await fetch(url, { headers: { 'User-Agent': 'rasm-pro-fonts', Accept: 'application/vnd.github+json' } });
  if (!r.ok) throw new Error(`HTTP ${r.status} ${url}`);
  return r.json();
}

async function download(url, dest) {
  const r = await fetch(url, { headers: { 'User-Agent': 'rasm-pro-fonts' } });
  if (!r.ok) throw new Error(`HTTP ${r.status} ${url}`);
  const buf = Buffer.from(await r.arrayBuffer());
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  fs.writeFileSync(dest, buf);
  return buf.length;
}

const manifest = [];
for (const [slug, name] of FAMILIES) {
  let listed = null, dirUsed = null;
  for (const lic of LIC_DIRS) {
    try { listed = await getJSON(`${API}/${lic}/${slug}`); dirUsed = lic; break; }
    catch { /* try next */ }
  }
  if (!listed) { console.log(`✗ ${slug}: not found`); continue; }
  const files = listed.filter(x => x.type === 'file');
  const ttfs = files.filter(f => f.name.toLowerCase().endsWith('.ttf'));
  const licFile = files.find(f => /^(ofl|license|apache|ufl).*(\.txt)?$/i.test(f.name));
  if (!ttfs.length) { console.log(`✗ ${slug}: no ttf (${files.map(f=>f.name).join(', ')})`); continue; }
  const dir = path.join(OUT, slug);
  const saved = [];
  for (const f of ttfs) {
    const dest = path.join(dir, f.name);
    try { const n = await download(f.download_url, dest); saved.push({ file: f.name, bytes: n }); }
    catch (e) { console.log(`  ! ${slug}/${f.name}: ${e.message}`); }
  }
  let license = dirUsed === 'apache' ? 'Apache-2.0' : dirUsed === 'ufl' ? 'UFL-1.0' : 'OFL-1.1';
  if (licFile) {
    try { await download(licFile.download_url, path.join(dir, licFile.name)); } catch {}
  }
  manifest.push({ slug, name, license, dir: dirUsed, files: saved });
  console.log(`✓ ${slug} (${license}) — ${saved.map(s=>s.file).join(', ')}`);
  await new Promise(r => setTimeout(r, 400)); // مهلة لطيفة على API
}

fs.writeFileSync(path.join(OUT, 'fonts.json'), JSON.stringify({ pulledAt: new Date().toISOString(), families: manifest }, null, 2), 'utf8');
console.log(`\n== ${manifest.length} عائلة خطوط == ${manifest.reduce((a,m)=>a+m.files.length,0)} ملف → ${OUT}`);
