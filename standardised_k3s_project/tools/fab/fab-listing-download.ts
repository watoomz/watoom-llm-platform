// Operator tool: download the files of one OWNED non-Unreal Fab format (fbx, glb, ...) by listing uid. Owner approval is the caller's responsibility.
// Usage: bun run fab-listing-download.ts <listing-uid> <format-code> <out-dir>   Layout: <out-dir>/<format>/{metadata,<file>[,<zip>_extracted/]}
import { loadTokens } from "/data/ai/tools/epic-fab/src/auth.ts";
import { mkdirSync, writeFileSync, existsSync, statSync } from "node:fs";
const [uid, code, out] = process.argv.slice(2);
if (!uid || !code || !out) { console.error("usage: <listing-uid> <format-code> <out-dir>"); process.exit(2); }
const tokens = await loadTokens();
const H = { Authorization: `Bearer ${tokens.accessToken}`, "User-Agent": "epic-fab/0.1 (+linux)" };
const listing = await (await fetch(`https://www.fab.com/i/listings/${uid}`, { headers: H })).json() as any;
const formats = await (await fetch(`https://www.fab.com/i/listings/${uid}/asset-formats`, { headers: H })).json() as any[];
const fmt = formats.find((f) => f.assetFormatType?.code === code);
if (!fmt) { console.error(`no ${code} format on ${uid}; has ${formats.map((f) => f.assetFormatType?.code)}`); process.exit(3); }
const dir = `${out}/${code}`;
mkdirSync(dir, { recursive: true });
writeFileSync(`${dir}/metadata`, JSON.stringify({ assetNamespace: "fab", listing: { title: listing.title, uid, description: listing.description, user: listing.user, tags: listing.tags, licenses: listing.licenses }, format: code, files: fmt.files }, null, 1));
for (const file of fmt.files) {
  const dest = `${dir}/${file.name}`;
  if (existsSync(dest) && statSync(dest).size === file.fileSize) { console.log("have", file.name); continue; }
  const info = await (await fetch(`https://www.fab.com/p/egl/listings/${uid}/asset-formats/${code}/files/${file.uid}/download-info`, { headers: H })).json() as any;
  const url = info.downloadInfo?.[0]?.downloadUrl;
  if (!url) { console.error("no download url for", file.name); process.exit(4); }
  const r = await fetch(url);  // signed URL: no auth header
  if (!r.ok) { console.error("download failed", r.status, file.name); process.exit(5); }
  const buf = new Uint8Array(await r.arrayBuffer());
  if (file.fileSize && buf.length !== file.fileSize) { console.error(`size mismatch for ${file.name}: ${buf.length} != ${file.fileSize}`); process.exit(6); }
  await Bun.write(dest, buf);
  console.log("downloaded", file.name, buf.length);
}
