#!/usr/bin/env node
// Inspect a source map and optionally reconstruct the original source tree.
const fs = require("fs");
const path = require("path");

const [, , cmd, mapPath, outDir, ...rest] = process.argv;
const map = JSON.parse(fs.readFileSync(mapPath, "utf8"));
const sources = map.sources || [];
const contents = map.sourcesContent || [];

if (cmd === "info") {
  console.log("file:", map.file);
  console.log("sourceRoot:", map.sourceRoot);
  console.log("sources:", sources.length, "| sourcesContent:", contents.length);
  const withContent = contents.filter(Boolean);
  console.log("entries with content:", withContent.length, "| total content chars:", withContent.reduce((a, s) => a + s.length, 0));
  const limit = Number(rest[0] || 30);
  for (let i = 0; i < Math.min(limit, sources.length); i++) {
    console.log(String(i).padStart(5), String(contents[i] ? contents[i].length : 0).padStart(8), sources[i]);
  }
  console.log("--- unique top segments ---");
  const segs = new Map();
  for (const s of sources) {
    const key = s.split("/").slice(0, 3).join("/");
    segs.set(key, (segs.get(key) || 0) + 1);
  }
  [...segs.entries()].sort((a, b) => b[1] - a[1]).slice(0, 40).forEach(([k, v]) => console.log(String(v).padStart(6), k));
} else if (cmd === "extract") {
  let written = 0;
  for (let i = 0; i < sources.length; i++) {
    const content = contents[i];
    if (!content) continue;
    let rel = sources[i].replace(/^[a-zA-Z]+:\/\/[^/]*\//, "");
    rel = rel.replace(/(\.\.\/)+/g, "").replace(/^\/+/, "").replace(/[<>:"|?*]/g, "_");
    const out = path.join(outDir, rel);
    fs.mkdirSync(path.dirname(out), { recursive: true });
    fs.writeFileSync(out, content);
    written++;
  }
  console.log("wrote", written, "files to", outDir);
}
