// Read-only: resolve library-page titles that the UE library feed omits into listing detail (description, categories, per-format files).
import { loadTokens } from "/data/ai/tools/epic-fab/src/auth.ts";
const tokens = await loadTokens();
const H = { Authorization: `Bearer ${tokens.accessToken}`, "User-Agent": "epic-fab/0.1 (+linux)" };
const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, "");
const titles: string[] = JSON.parse(await Bun.file(process.argv[2]).text());
const out: Record<string, unknown>[] = [];
for (const title of titles) {
  const entry: Record<string, unknown> = { title };
  try {
    const q = await (await fetch(`https://www.fab.com/i/listings/search?q=${encodeURIComponent(title)}&count=20`, { headers: H })).json() as any;
    const results: any[] = q.results ?? q.listings ?? [];
    const hit = results.find((r) => norm(r.title ?? "") === norm(title)) ?? null;
    if (!hit) { entry.error = "no exact search match"; entry.candidates = results.slice(0, 3).map((r) => r.title); out.push(entry); continue; }
    entry.uid = hit.uid;
    const listing = await (await fetch(`https://www.fab.com/i/listings/${hit.uid}`, { headers: H })).json() as any;
    const formats = await (await fetch(`https://www.fab.com/i/listings/${hit.uid}/asset-formats`, { headers: H })).json() as any[];
    entry.listing = listing;
    entry.formats = (formats ?? []).map((f) => ({ code: f.assetFormatType?.code, group: f.assetFormatType?.groupName, files: (f.files ?? []).map((x: any) => ({ name: x.name, size: x.fileSize, engineVersions: x.engineVersions })) }));
  } catch (e) { entry.error = String(e); }
  out.push(entry);
}
await Bun.write(process.argv[3], JSON.stringify(out));
console.log("resolved", out.filter((o) => o.uid).length, "of", out.length);
