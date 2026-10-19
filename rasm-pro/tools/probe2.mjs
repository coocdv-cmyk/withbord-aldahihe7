// فحص بنية بيانات Iconify: أين يوجد الترخيص؟
async function tryJson(url) {
  try {
    const r = await fetch(url);
    if (!r.ok) return { url, ok: false, status: r.status };
    const j = await r.json();
    return { url, ok: true, json: j };
  } catch (e) {
    return { url, ok: false, error: e.message };
  }
}

const a = await tryJson("https://cdn.jsdelivr.net/npm/@iconify-json/tabler/icons.json");
console.log("== icons.json (tabler) ==");
if (a.ok) {
  console.log("keys:", Object.keys(a.json).join(", "));
  console.log("info:", JSON.stringify(a.json.info));
  console.log("license:", JSON.stringify(a.json.license));
  const one = Object.entries(a.json.icons || {})[0];
  console.log("sample icon:", JSON.stringify(one));
}

const b = await tryJson("https://cdn.jsdelivr.net/npm/@iconify-json/tabler/info.json");
console.log("\n== info.json (tabler) ==");
console.log(b.ok ? JSON.stringify(b.json, null, 2).slice(0, 1200) : `not available (${b.status || b.error})`);

const c = await tryJson("https://cdn.jsdelivr.net/npm/@iconify/collections/collections.json");
console.log("\n== @iconify/collections/collections.json ==");
if (c.ok) {
  const keys = Object.keys(c.json);
  console.log("عدد المجموعات:", keys.length);
  console.log("tabler:", JSON.stringify(c.json.tabler));
  console.log("solar:", JSON.stringify(c.json.solar));
  console.log("hugeicons:", JSON.stringify(c.json.hugeicons));
} else {
  console.log("فشل:", c.status || c.error);
}
