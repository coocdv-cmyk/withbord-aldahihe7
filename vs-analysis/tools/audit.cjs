#!/usr/bin/env node
// Audit the recovered VideoScribe source tree: total size, LOC, and import resolution.
const fs = require("fs");
const path = require("path");

const root = process.argv[2];
const SRC = path.join(root, "js");

function walk(dir, out = []) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p, out);
    else out.push(p);
  }
  return out;
}

const files = walk(SRC);
const exts = new Map();
let loc = 0;
let bytes = 0;
for (const f of files) {
  const ext = path.extname(f) || "(none)";
  exts.set(ext, (exts.get(ext) || 0) + 1);
  const s = fs.readFileSync(f, "utf8");
  bytes += s.length;
  loc += s.split("\n").length;
}
console.log("files:", files.length, "| LOC:", loc, "| chars:", bytes);
console.log("--- by extension ---");
[...exts.entries()].sort((a, b) => b[1] - a[1]).forEach(([k, v]) => console.log(String(v).padStart(6), k));

// import resolution for app-internal aliases (js/... and relative)
const extTry = ["", ".ts", ".tsx", ".js", ".jsx", ".json", ".svg", ".png", "/index.ts", "/index.tsx", "/index.js", "/index.jsx"];
const missing = new Map();
let imports = 0;
let resolved = 0;
const re = /(?:from\s+|import\s*\(\s*|require\(\s*)['"]([^'"]+)['"]/g;
for (const f of files) {
  const s = fs.readFileSync(f, "utf8");
  let m;
  while ((m = re.exec(s))) {
    let spec = m[1];
    if (spec.startsWith("js/")) {
      imports++;
      const base = path.join(root, "js", spec.slice(3));
      if (extTry.some((e) => fs.existsSync(base + e))) resolved++;
      else missing.set(spec, (missing.get(spec) || 0) + 1);
    } else if (spec.startsWith("./") || spec.startsWith("../")) {
      imports++;
      const base = path.resolve(path.dirname(f), spec);
      if (extTry.some((e) => fs.existsSync(base + e))) resolved++;
      else missing.set(path.relative(root, base), (missing.get(path.relative(root, base)) || 0) + 1);
    }
  }
}
console.log("--- internal imports ---");
console.log("total internal imports:", imports, "| resolved:", resolved, "| unresolved:", imports - resolved);
console.log("distinct unresolved targets:", missing.size);
const worst = [...missing.entries()].sort((a, b) => b[1] - a[1]).slice(0, 40);
for (const [k, v] of worst) console.log(String(v).padStart(4), k);
