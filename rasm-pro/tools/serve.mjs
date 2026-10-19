#!/usr/bin/env node
/**
 * راسم — سيرفر محلي صغير لعرض أوراق المراجعة والمكتبة في المتصفح.
 *   node serve.mjs [rootDir] [port]
 */
import http from "node:http";
import fs from "node:fs";
import path from "node:path";

const ROOT = path.resolve(process.argv[2] || "C:/Users/USER/AppData/Local/Temp/opencode");
const PORT = parseInt(process.argv[3] || "8765", 10);

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".png": "image/png", ".jpg": "image/jpeg", ".md": "text/markdown; charset=utf-8",
};

http.createServer((req, res) => {
  try {
    let rel = decodeURIComponent((req.url || "/").split("?")[0]);
    if (rel === "/") rel = "/rasm-sheet-001.html";
    const file = path.normalize(path.join(ROOT, rel));
    if (!file.startsWith(ROOT)) { res.writeHead(403).end("forbidden"); return; }
    if (!fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.writeHead(404).end("not found"); return; }
    res.writeHead(200, { "content-type": MIME[path.extname(file).toLowerCase()] || "application/octet-stream" });
    fs.createReadStream(file).pipe(res);
  } catch (e) {
    res.writeHead(500).end(String(e.message));
  }
}).listen(PORT, "127.0.0.1", () => console.log(`راسم · سيرفر المعاينة: http://localhost:${PORT}/  (الجذر: ${ROOT})`));
