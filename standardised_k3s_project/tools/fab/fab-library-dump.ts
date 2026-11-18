// Read-only: dump the authenticated UE-format Fab library with full raw records. Usage: bun run fab-library-dump.ts <out.json>
import { loadTokens } from "/data/ai/tools/epic-fab/src/auth.ts";
import { listLibrary } from "/data/ai/tools/epic-fab/src/api.ts";
const tokens = await loadTokens();
const items = await listLibrary(tokens);
await Bun.write(process.argv[2], JSON.stringify(items.map((i) => ({ id: i.id, title: i.title, type: i.type, ownedAt: i.ownedAt, raw: i.raw }))));
console.log("items", items.length);
