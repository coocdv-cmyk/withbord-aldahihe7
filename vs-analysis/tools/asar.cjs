#!/usr/bin/env node
// Minimal, robust ASAR reader: list | cat | extract
const fs = require("fs");
const path = require("path");

const [, , cmd, archive, ...rest] = process.argv;

function readHeader(file) {
  const fd = fs.openSync(file, "r");
  const head = Buffer.alloc(8);
  fs.readSync(fd, head, 0, 8, 0);
  const size = head.readUInt32LE(4);
  const pickle = Buffer.alloc(size);
  fs.readSync(fd, pickle, 0, size, 8);
  const start = pickle.indexOf(0x7b); // first '{'
  const end = pickle.lastIndexOf(0x7d); // last '}'
  const json = pickle.subarray(start, end + 1).toString("utf8");
  const header = JSON.parse(json);
  const dataBase = 8 + size;
  fs.closeSync(fd);
  return { header, dataBase };
}

function flatten(node, prefix, out) {
  for (const [name, value] of Object.entries(node.files || {})) {
    const p = prefix ? prefix + "/" + name : name;
    if (value.files) flatten(value, p, out);
    else out.push({ path: p, size: value.size || 0, offset: Number(value.offset) || 0, unpacked: !!value.unpacked });
  }
  return out;
}

const { header, dataBase } = readHeader(archive);
const files = flatten(header, "", []);

if (cmd === "list") {
  const groups = new Map();
  const depth = Number(rest[0] || 2);
  for (const f of files) {
    const key = f.path.split("/").slice(0, depth).join("/");
    const g = groups.get(key) || { n: 0, size: 0 };
    g.n++; g.size += f.size;
    groups.set(key, g);
  }
  const rows = [...groups.entries()].sort((a, b) => b[1].size - a[1].size);
  console.log("files:", files.length, "bytes:", files.reduce((a, f) => a + f.size, 0));
  for (const [k, g] of rows) console.log((Math.round(g.size / 1024) + " KB").padStart(11), String(g.n).padStart(6), k);
} else if (cmd === "cat") {
  const target = rest.join("/");
  const entry = files.find((f) => f.path === target);
  if (!entry) { console.error("not found:", target); process.exit(2); }
  const fd = fs.openSync(archive, "r");
  const buf = Buffer.alloc(entry.size);
  fs.readSync(fd, buf, 0, entry.size, dataBase + entry.offset);
  fs.closeSync(fd);
  process.stdout.write(buf);
} else if (cmd === "find") {
  const needle = (rest[0] || "").toLowerCase();
  const limit = Number(rest[1] || 200);
  const hits = files.filter((f) => f.path.toLowerCase().includes(needle)).slice(0, limit);
  for (const h of hits) console.log(String(h.size).padStart(10), h.path);
  console.log("matches:", hits.length, "of", files.filter((f) => f.path.toLowerCase().includes(needle)).length);
} else if (cmd === "extract") {
  const dest = rest[0];
  const filter = rest[1];
  const re = filter ? new RegExp(filter, "i") : null;
  const selected = re ? files.filter((f) => re.test(f.path)) : files;
  const fd = fs.openSync(archive, "r");
  for (const f of selected) {
    const out = path.join(dest, f.path);
    fs.mkdirSync(path.dirname(out), { recursive: true });
    const buf = Buffer.alloc(f.size);
    fs.readSync(fd, buf, 0, f.size, dataBase + f.offset);
    fs.writeFileSync(out, buf);
  }
  fs.closeSync(fd);
  console.log("extracted", selected.length, "files to", dest);
} else {
  console.error("usage: asar.cjs list|cat|find|extract <archive> [args]");
  process.exit(1);
}
