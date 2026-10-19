#!/usr/bin/env node
// Tally file types inside an asar and inventory non-node_modules assets.
const fs = require("fs");
const [, , asarPath] = process.argv;

const fd = fs.openSync(asarPath, "r");
const head = Buffer.alloc(16);
fs.readSync(fd, head, 0, 16, 0);
const headerSize = head.readUInt32LE(4);
const buf = Buffer.alloc(headerSize);
fs.readSync(fd, buf, 0, headerSize, 8);
const json = buf.subarray(buf.indexOf(0x7b), buf.lastIndexOf(0x7d) + 1).toString("utf8");
const header = JSON.parse(json);

const files = [];
(function walk(node, prefix) {
  for (const [name, entry] of Object.entries(node.files || {})) {
    const p = prefix ? prefix + "/" + name : name;
    if (entry.files) walk(entry, p);
    else files.push([p, entry.size]);
  }
})(header, "");

const ext = (p) => {
  const m = /\.([A-Za-z0-9]+)$/.exec(p);
  return (m ? m[1] : "(none)").toLowerCase();
};

console.log("TOTAL FILES: " + files.length);
const byExt = new Map();
for (const [p, size] of files) {
  const e = ext(p);
  const c = byExt.get(e) || { n: 0, b: 0 };
  c.n++; c.b += size;
  byExt.set(e, c);
}
console.log("--- by extension (all) ---");
[...byExt.entries()].sort((a, b) => b[1].b - a[1].b).forEach(([k, v]) =>
  console.log(String(v.n).padStart(7) + "  " + String(Math.round(v.b / 1024)).padStart(9) + " KB  ." + k)
);

const ASSET = new Set(["svg", "png", "jpg", "jpeg", "gif", "webp", "bmp", "ico",
  "mp3", "wav", "ogg", "m4a", "aac", "flac",
  "ttf", "otf", "woff", "woff2", "eot",
  "mp4", "webm", "mov", "avi"]);

const outside = files.filter(([p]) => !p.startsWith("node_modules/") && ASSET.has(ext(p)));
console.log("--- media/font assets OUTSIDE node_modules: " + outside.length + " files ---");
const byDir = new Map();
for (const [p, size] of outside) {
  const dir = p.split("/").slice(0, -1).join("/") || "(root)";
  const c = byDir.get(dir) || { n: 0, b: 0, exts: new Map() };
  c.n++; c.b += size;
  c.exts.set(ext(p), (c.exts.get(ext(p)) || 0) + 1);
  byDir.set(dir, c);
}
[...byDir.entries()].sort((a, b) => b[1].n - a[1].n).slice(0, 40).forEach(([d, v]) =>
  console.log(String(v.n).padStart(5) + "  " + String(Math.round(v.b / 1024)).padStart(7) + " KB  " + d +
    "   [" + [...v.exts.entries()].map(([e, n]) => e + ":" + n).join(", ") + "]")
);

const icons = files.filter(([p]) => p.startsWith("node_modules/@icons/"));
console.log("--- node_modules/@icons: " + icons.length + " files, " +
  Math.round(icons.reduce((a, [, s]) => a + s, 0) / 1024) + " KB ---");
const iconPkgs = new Map();
for (const [p] of icons) {
  const parts = p.split("/");
  const key = parts[2] || "(?)";
  iconPkgs.set(key, (iconPkgs.get(key) || 0) + 1);
}
[...iconPkgs.entries()].sort((a, b) => b[1] - a[1]).slice(0, 10).forEach(([k, v]) => console.log(String(v).padStart(6) + "  @" + k));

const audio = files.filter(([p]) => ["mp3", "wav", "ogg", "m4a", "aac", "flac"].includes(ext(p)));
console.log("--- AUDIO anywhere: " + audio.length + " files ---");
audio.slice(0, 20).forEach(([p, s]) => console.log(String(Math.round(s / 1024)).padStart(6) + " KB  " + p));

const fonts = files.filter(([p]) => ["ttf", "otf", "woff", "woff2"].includes(ext(p)) && !p.startsWith("node_modules/"));
console.log("--- FONTS outside node_modules: " + fonts.length + " ---");
fonts.slice(0, 30).forEach(([p, s]) => console.log(String(Math.round(s / 1024)).padStart(6) + " KB  " + p));

const big = files.filter(([p, s]) => !p.startsWith("node_modules/") && s > 200 * 1024)
  .sort((a, b) => b[1] - a[1]).slice(0, 25);
console.log("--- biggest non-node_modules files ---");
big.forEach(([p, s]) => console.log(String(Math.round(s / 1024)).padStart(8) + " KB  " + p));
