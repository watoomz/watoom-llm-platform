// Operator-only: enrich uncategorised owned Fab assets with public listing facts (category, tags, formats, rigged /
// animated / animation count) using the EXISTING epic-fab sign-in. Read-only: one Fab search per title, exact title
// match only, bounded and rate limited, stops on any auth or rate-limit error. Never prints or stores tokens.
//
//   bun run tools/fab/fab_listing_facts.ts --index /data/ai/assets/catalog/asset-index.json \
//       --out /data/ai/assets/catalog/fab-listing-facts.json [--limit 200] [--delay-ms 1500] [--only-uncategorised|--all]
//
// Output is a facts JSON keyed by library asset id, in the format asset_advisor.py --facts consumes. Titles with no
// exact match go to <out>.unmatched.json instead of being guessed.
import {loadTokens, refreshIfNeeded} from "/data/ai/tools/epic-fab/src/auth.ts";
import {readFileSync, writeFileSync, existsSync} from "node:fs";

const arg = (name: string, fallback?: string) => {
  const i = process.argv.indexOf(name);
  return i >= 0 ? process.argv[i + 1] : fallback;
};
const index = arg("--index", "/data/ai/assets/catalog/asset-index.json")!;
const out = arg("--out", "/data/ai/assets/catalog/fab-listing-facts.json")!;
const limit = Number(arg("--limit", "200"));
const delayMs = Number(arg("--delay-ms", "1500"));
const all = process.argv.includes("--all");

const strip = (html: string) => html.replace(/<[^>]*>/g, " ").replace(/&nbsp;|&amp;|&#\d+;/g, " ").replace(/\s+/g, " ");
const yes = (m: RegExpMatchArray | null) => (m ? m[1].toLowerCase() === "yes" : undefined);

// Fab's own top-level category slug (the first segment of category.path) -> an asset_advisor taxonomy id. The advisor's
// keyword patterns were written for titles, so passing Fab's slug text would mis-match ("building-human-made" contains
// "human"). Unlisted slugs (e.g. "variety") get no category, so the advisor falls back to the title or stays
// uncategorised; tags are deliberately not forwarded because they mis-classify.
const TOP_LEVEL: Record<string, string> = {
  "environments": "environment", "building-human-made": "environment", "buildings-architecture": "environment",
  "nature-plants": "environment", "nature-terrain": "environment", "objects-decor": "environment",
  "vehicles-transportation": "environment", "weapons-combat": "environment",
  "sound-effects": "audio", "music": "audio", "ambient-sounds": "audio",
  "shaders": "materials", "art-traditional": "materials",
  "liquid": "vfx", "fire-explosions": "vfx", "spells-combat": "vfx",
  "widgets": "ui", "transition": "ui",
  "gameplay-features": "code_plugins", "game-mechanics": "code_plugins",
  "animations": "animations",
};
export function categoryFromPath(path: string): string | undefined {
  const [top, second] = String(path ?? "").split("/");
  if (top === "characters-creatures") {
    if (second === "creatures-monsters") return "creatures";
    if (second === "animals") return "animals";
    if (second === "grooms") return undefined;
    return "characters";
  }
  return TOP_LEVEL[top];
}

export function factsFromListing(listing: any) {
  const facts: Record<string, unknown> = {};
  const category = listing.category ?? {};
  const mapped = categoryFromPath(category.path);
  if (mapped) facts.category = mapped;
  const formats = (listing.assetFormats ?? []).map((f: any) => f?.assetFormatType?.name ?? f?.assetFormatType?.code).filter(Boolean);
  if (formats.length) facts.formats = formats;
  const details = (listing.assetFormats ?? []).map((f: any) => f?.technicalSpecs?.technicalDetails).filter((x: any) => typeof x === "string").map(strip).join(" ");
  const rigged = yes(details.match(/\bRigged:\s*(Yes|No)\b/i));
  const animated = yes(details.match(/\bAnimated:\s*(Yes|No)\b/i));
  const count = details.match(/Number of Animations:\s*(\d+)/i);
  if (rigged !== undefined) { facts.rigged = rigged; if (rigged) facts.has_skeletal_mesh = true; }
  if (animated !== undefined) facts.animated = animated;
  if (count) facts.anim_count = Number(count[1]);
  return facts;
}

if (import.meta.main) {
  let tokens = await loadTokens();
  if (!tokens) { console.error("Not authenticated. Run: /data/ai/bin/epic-fab auth"); process.exit(2); }
  tokens = await refreshIfNeeded(tokens);
  const doc = JSON.parse(readFileSync(index, "utf8"));
  const todo = (doc.assets as any[]).filter((a) => a.source === "ue-library" && (all || a.category === "uncategorised")).slice(0, limit);
  const facts: Record<string, unknown> = existsSync(out) ? JSON.parse(readFileSync(out, "utf8")) : {};
  const unmatched: Array<{id: string; title: string; reason: string}> = [];
  let done = 0;
  for (const asset of todo) {
    if (facts[asset.id]) continue;
    const r = await fetch("https://www.fab.com/i/listings/search?q=" + encodeURIComponent(asset.title) + "&count=10",
      {headers: {Authorization: "Bearer " + tokens.accessToken, Accept: "application/json"}});
    if (r.status === 401 || r.status === 403 || r.status === 429) { console.error("STOP: HTTP " + r.status); break; }
    if (!r.ok) { unmatched.push({id: asset.id, title: asset.title, reason: "HTTP " + r.status}); continue; }
    const rows: any[] = ((await r.json()) as any).results ?? [];
    const wanted = asset.title.trim().toLowerCase();
    const exact = rows.filter((x) => String(x.title ?? "").trim().toLowerCase() === wanted);
    if (exact.length !== 1) unmatched.push({id: asset.id, title: asset.title, reason: exact.length ? "ambiguous: " + exact.length + " exact title matches" : "no exact title match"});
    else {
      const f = factsFromListing(exact[0]);
      if (Object.keys(f).length) { facts[asset.id] = f; done++; } else unmatched.push({id: asset.id, title: asset.title, reason: "listing had no usable facts"});
    }
    await new Promise((res) => setTimeout(res, delayMs));
  }
  writeFileSync(out, JSON.stringify(facts, null, 1) + "\n");
  writeFileSync(out.replace(/\.json$/, "") + ".unmatched.json", JSON.stringify(unmatched, null, 1) + "\n");
  console.log(JSON.stringify({requested: todo.length, enriched: done, total_facts: Object.keys(facts).length, unmatched: unmatched.length}));
}
