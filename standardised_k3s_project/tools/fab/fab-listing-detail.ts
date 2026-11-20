// Read-only: resolve library-page titles that the UE library feed omits into listing detail (description, categories, per-format files).
// Input: a JSON array of titles, or of {title, publisher} (e.g. rows of the fab.com library export). With a publisher, every exact
// title match is checked and only the one whose seller is that publisher is taken (2026-11-19: common titles such as "Classic M4"
// or "Medieval House" have several listings; the first match was often someone else's). 300 ms between requests.
import { loadTokens } from "/data/ai/tools/epic-fab/src/auth.ts";
const tokens = await loadTokens();
const H = { Authorization: `Bearer ${tokens.accessToken}`, "User-Agent": "epic-fab/0.1 (+linux)" };
const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, "");
const rows: (string | { title: string; publisher?: string })[] = JSON.parse(await Bun.file(process.argv[2]).text());
const pause = () => new Promise((r) => setTimeout(r, 300));
const out: Record<string, unknown>[] = [];
for (const row of rows) {
  const title = typeof row === "string" ? row : row.title;
  const publisher = typeof row === "string" ? undefined : row.publisher;
  const entry: Record<string, unknown> = publisher ? { title, publisher } : { title };
  try {
    const q = await (await fetch(`https://www.fab.com/i/listings/search?q=${encodeURIComponent(title)}&count=20`, { headers: H })).json() as any;
    const results: any[] = q.results ?? q.listings ?? [];
    const exact = results.filter((r) => norm(r.title ?? "") === norm(title));
    if (!exact.length) { entry.error = "no exact search match"; entry.candidates = results.slice(0, 3).map((r) => r.title); out.push(entry); await pause(); continue; }
    let hit: any = null, listing: any = null;
    for (const r of exact) {
      await pause();
      const l = await (await fetch(`https://www.fab.com/i/listings/${r.uid}`, { headers: H })).json() as any;
      if (!publisher || norm(l?.user?.sellerName ?? "") === norm(publisher)) { hit = r; listing = l; break; }
    }
    if (!hit) { entry.error = "title found, publisher differs"; entry.candidates = exact.map((r) => r.uid); out.push(entry); continue; }
    entry.uid = hit.uid;
    entry.seller = listing?.user?.sellerName;
    const formats = await (await fetch(`https://www.fab.com/i/listings/${hit.uid}/asset-formats`, { headers: H })).json() as any[];
    entry.listing = listing;
    entry.formats = (formats ?? []).map((f) => ({ code: f.assetFormatType?.code, group: f.assetFormatType?.groupName, files: (f.files ?? []).map((x: any) => ({ name: x.name, size: x.fileSize, engineVersions: x.engineVersions })) }));
  } catch (e) { entry.error = String(e); }
  out.push(entry);
}
await Bun.write(process.argv[3], JSON.stringify(out));
console.log("resolved", out.filter((o) => o.uid).length, "of", out.length);
