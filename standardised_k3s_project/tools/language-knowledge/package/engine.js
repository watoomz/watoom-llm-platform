// The search/ranking index (postings, symbols, byId, lengths) stays RAM-resident and disk-I/O-free after load().
// Full card details use a warm 512-card cache; cold file-backed details incur bounded LRU-cached disk reads.
// Semantic vectors are NOT implemented in v1.
import {closeSync, openSync, readFileSync, readSync} from "node:fs";

const RRF_K = 60;
import {createHash} from "node:crypto";

const STOP = new Set(["the", "a", "an", "of", "to", "in", "for", "and", "or", "is", "how", "do", "i", "with", "on", "what"]);
export function tokenize(text) {
  const out = [];
  for (const raw of String(text ?? "").split(/[^A-Za-z0-9_]+/)) {
    if (!raw) continue;
    const lower = raw.toLowerCase();
    if (!STOP.has(lower)) out.push(lower);
    // split snake_case and CamelCase parts so "add_child" and "AddChild" meet "add" and "child"
    const parts = raw.replace(/([a-z0-9])([A-Z])/g, "$1 $2").split(/[_\s]+/).map((p) => p.toLowerCase()).filter((p) => p && p !== lower && !STOP.has(p));
    out.push(...parts);
  }
  return out;
}
const KIND_WEIGHT = {operator: 1.6, api_class: 1.3, rna_struct: 1.15, api_method: 1.1, import_option: 1.2};
const norm = (s) => String(s ?? "").trim().toLowerCase();
const versionParts = (v) => String(v ?? "").split(".").map((x) => parseInt(x, 10) || 0);
export function versionCompatible(cardVersion, wanted) {
  if (!wanted) return "unspecified";
  if (cardVersion === wanted) return "exact";
  const a = versionParts(cardVersion), b = versionParts(wanted);
  return a[0] === b[0] && a[1] === b[1] ? "compatible" : "mismatch";
}

class Lru {
  constructor(max) { this.max = max; this.map = new Map(); this.evictions = 0; }
  get(k) { if (!this.map.has(k)) return undefined; const v = this.map.get(k); this.map.delete(k); this.map.set(k, v); return v; }
  set(k, v) { this.map.delete(k); this.map.set(k, v); while (this.map.size > this.max) { this.map.delete(this.map.keys().next().value); this.evictions++; } }
}

export class Engine {
  constructor({cacheEntries = 256} = {}) {
    this.generation = 0; this.cards = []; this.lines = []; this.parsed = new Lru(512); this.byId = new Map(); this.symbols = new Map(); this.postings = new Map();
    this.lengths = []; this.avgLength = 1; this.cache = new Lru(cacheEntries); this.counters = {queries: 0, cacheHits: 0, diskReads: 0};
    this.sha = ""; this.loadedAt = 0; this.vectors = null; this.sourcePaths = []; this.fileIndex = null; this.offsets = null; this.byteLengths = null; this.openFiles = new Map();
  }
  // Build a complete new generation off to the side, then swap the reference (readers never see a partial index).
  load(paths) {
    const sourcePaths = Array.isArray(paths) ? paths : [paths];
    const chunks = [], records = [];
    for (let fileIndex = 0; fileIndex < sourcePaths.length; fileIndex++) {
      this.counters.diskReads++;
      const buf = readFileSync(sourcePaths[fileIndex]);
      chunks.push(buf.toString("utf8"));
      let start = 0;
      for (let end = 0; end <= buf.length; end++) if (end === buf.length || buf[end] === 10) {
        const line = buf.subarray(start, end).toString("utf8");
        if (line.trim()) records.push({line, fileIndex, offset: start, length: end - start});
        start = end + 1;
      }
    }
    return this._loadText(chunks.join("\n"), records, sourcePaths);
  }
  loadText(text) {
    return this._loadText(text, null, []);
  }
  _loadText(text, sourceRecords, sourcePaths) {
    const cards = [], lines = [], locations = [], seen = new Set();
    const inputLines = sourceRecords ?? text.split("\n").filter((line) => line.trim()).map((line) => ({line}));
    for (const record of inputLines) {
      const {line} = record;
      if (!line.trim()) continue;
      const card = JSON.parse(line);
      for (const key of ["id", "product", "version", "kind", "symbol", "signature", "source", "trust_tier", "status"])
        if (card[key] === undefined || card[key] === null) throw new Error(`card ${card.id ?? "?"} missing ${key}`);
      if (seen.has(card.id)) continue; seen.add(card.id);
      cards.push({id: card.id, product: norm(card.product), language: norm(card.language), version: card.version, kind: card.kind,
        symbol: card.symbol, deprecated: !!card.deprecated, quarantined: card.status === "quarantined"});
      lines.push(line);
      locations.push(record);
    }
    const next = {cards, lines: sourceRecords ? [] : lines, byId: new Map(), symbols: new Map(), postings: new Map(), lengths: [],
      sourcePaths: sourceRecords ? [...new Set(sourcePaths)] : [], fileIndex: sourceRecords ? new Uint32Array(cards.length) : null,
      offsets: sourceRecords ? new Float64Array(cards.length) : null, byteLengths: sourceRecords ? new Uint32Array(cards.length) : null};
    const pathIndexes = sourceRecords ? new Map(next.sourcePaths.map((p, i) => [p, i])) : null;
    if (sourceRecords) locations.forEach((loc, i) => { next.fileIndex[i] = pathIndexes.get(sourcePaths[loc.fileIndex]); next.offsets[i] = loc.offset; next.byteLengths[i] = loc.length; });
    const nextParsed = new Lru(512);
    next.lengths = [];
    cards.forEach((meta, i) => {
      const card = JSON.parse(lines[i]);
      nextParsed.set(i, card);
      next.byId.set(card.id, i);
      for (const name of new Set([card.symbol, ...(card.aliases ?? [])].map(norm))) {
        if (!next.symbols.has(name)) next.symbols.set(name, []);
        next.symbols.get(name).push(i);
      }
      const tail = norm(card.symbol).split(".").pop();
      if (tail && tail !== norm(card.symbol)) { if (!next.symbols.has("~" + tail)) next.symbols.set("~" + tail, []); next.symbols.get("~" + tail).push(i); }
      const tokens = [...tokenize(card.symbol), ...tokenize(card.symbol), ...tokenize(card.signature), ...tokenize(card.summary), ...(card.aliases ?? []).flatMap(tokenize)];
      next.lengths.push(tokens.length || 1);
      const tf = new Map(); for (const t of tokens) tf.set(t, (tf.get(t) ?? 0) + 1);
      for (const [t, n] of tf) { if (!next.postings.has(t)) next.postings.set(t, []); next.postings.get(t).push([i, n]); }
    });
    for (const [term, list] of next.postings) {
      const ids = new Int32Array(list.length), tfs = new Uint8Array(list.length);
      list.forEach(([i, n], k) => { ids[k] = i; tfs[k] = Math.min(255, n); });
      next.postings.set(term, {ids, tfs});
    }
    for (const [name, list] of next.symbols) if (list.length === 1) next.symbols.set(name, Int32Array.of(list[0]));
    const oldFiles = this.openFiles;
    Object.assign(this, next, {parsed: nextParsed, openFiles: new Map(), avgLength: next.lengths.reduce((a, b) => a + b, 0) / Math.max(1, next.lengths.length), generation: this.generation + 1,
      sha: createHash("sha256").update(text).digest("hex").slice(0, 16), loadedAt: Date.now()});
    for (const fd of oldFiles.values()) closeSync(fd);
    this.cache = new Lru(this.cache.max);
    return {cards: cards.length, generation: this.generation, sha: this.sha};
  }
  // Int8-quantised, L2-normalised vectors in card order (see admin/embed_cards.py). Verified against the card snapshot sha.
  loadVectors(binPath, meta) {
    if (meta.cards_sha !== this.sha) throw new Error(`vectors built for cards ${meta.cards_sha}, loaded cards are ${this.sha}`);
    const buf = readFileSync(binPath); this.counters.diskReads++;
    if (buf.length !== meta.count * meta.dim || meta.count !== this.cards.length) throw new Error("vector file does not match card count");
    this.vectors = {dim: meta.dim, model: meta.model, data: new Int8Array(buf.buffer, buf.byteOffset, buf.length)};
    return {vectors: meta.count, dim: meta.dim};
  }
  semantic(queryVector, q, top = 50) {
    const {dim, data} = this.vectors; if (queryVector.length !== dim) return [];
    const qv = Int8Array.from(queryVector, (x) => Math.round(x * 127)), scored = [];
    for (let i = 0; i < this.cards.length; i++) {
      if (!this.filter(i, q)) continue;
      let dot = 0, o = i * dim; for (let k = 0; k < dim; k++) dot += qv[k] * data[o + k];
      if (scored.length < top || dot > scored[scored.length - 1][1]) {
        scored.push([i, dot]); scored.sort((a, b) => b[1] - a[1]); if (scored.length > top) scored.pop();
      }
    }
    return scored;
  }
  filter(i, q) {
    const c = this.cards[i];
    if (q.product && c.product !== norm(q.product)) return false;
    if (q.language && c.language !== norm(q.language)) return false;
    if (q.kind && c.kind !== q.kind) return false;
    return !c.quarantined;
  }
  rank(query, q) {
    const scores = new Map(), why = new Map();
    const add = (i, s, reason) => { scores.set(i, (scores.get(i) ?? 0) + s); if (!why.has(i)) why.set(i, reason); };
    const exact = norm(query.replace(/\(.*$/, ""));
    for (const i of this.symbols.get(exact) ?? []) if (this.filter(i, q)) add(i, 1000, "exact-symbol");
    for (const i of this.symbols.get("~" + exact) ?? []) if (this.filter(i, q)) add(i, 400, "member-name");
    const N = this.cards.length;
    for (const term of new Set(tokenize(query))) {
      const list = this.postings.get(term); if (!list || list.ids.length > N * 0.2) continue;
      const df = list.ids.length, idf = Math.log(1 + (N - df + 0.5) / (df + 0.5));
      for (let k = 0; k < df; k++) {
        const i = list.ids[k], tf = list.tfs[k];
        if (this.filter(i, q))
          add(i, idf * (tf * 2.2) / (tf + 1.2 * (0.25 + 0.75 * this.lengths[i] / this.avgLength)) * (KIND_WEIGHT[this.cards[i].kind] ?? 1), "keyword");
      }
    }
    return [...scores].map(([i, s]) => {
      const c = this.cards[i], v = versionCompatible(c.version, q.version);
      // version policy: exact > compatible > mismatch (kept, but demoted and flagged); never silently substituted
      return {i, score: s * (v === "exact" || v === "unspecified" ? 1 : v === "compatible" ? 0.7 : 0.15) + (c.deprecated ? -0.5 : 0), version_match: v, match: why.get(i)};
    }).sort((a, b) => b.score - a.score || this.cards[a.i].id.localeCompare(this.cards[b.i].id));
  }
  card(i) {
    let c = this.parsed.get(i);
    if (!c) {
      if (this.fileIndex) {
        const fileIndex = this.fileIndex[i], path = this.sourcePaths[fileIndex];
        let fd = this.openFiles.get(fileIndex);
        if (fd === undefined) { fd = openSync(path, "r"); this.openFiles.set(fileIndex, fd); }
        const bytes = Buffer.alloc(this.byteLengths[i]);
        let read = 0;
        while (read < bytes.length) read += readSync(fd, bytes, read, bytes.length - read, this.offsets[i] + read);
        c = JSON.parse(bytes.toString("utf8"));
        this.counters.diskReads++;
      } else c = JSON.parse(this.lines[i]);
      this.parsed.set(i, c);
    }
    return c;
  }
  view(hit, detail) {
    const c = this.card(hit.i);
    const out = {id: c.id, symbol: c.symbol, kind: c.kind, version: c.version, signature: c.signature, version_match: hit.version_match, match: hit.match,
      status: c.status, source: c.source.uri ?? c.source.revision, trust_tier: c.trust_tier};
    if (c.deprecated) out.deprecated = true;
    if (detail !== "quick") { out.summary = c.summary; out.params = c.params; out.returns = c.returns; out.constraints = c.constraints; }
    if (detail === "full") { out.examples = c.examples; out.source = c.source; out.license = c.license; }
    return out;
  }
  search(query, opts = {}) {
    this.counters.queries++;
    const q = {product: opts.product, language: opts.language, version: opts.version, kind: opts.kind};
    const limit = Math.max(1, Math.min(20, opts.limit ?? 8)), budget = Math.min(4000, opts.budget ?? 1500);
    const key = JSON.stringify([this.generation, query, q, limit, budget, opts.detail ?? "standard", opts.queryVector ? 1 : 0]);
    const hit = this.cache.get(key); if (hit) { this.counters.cacheHits++; return hit; }
    const detail = opts.detail ?? "standard", results = []; let used = 0, truncated = false;
    let ranked = this.rank(query, q);
    if (opts.queryVector && this.vectors) {
      // reciprocal-rank fusion; exact-symbol hits keep priority because they head the lexical list
      const fused = new Map(), seenAt = new Map(ranked.map((h) => [h.i, h]));
      ranked.slice(0, 50).forEach((h, r) => fused.set(h.i, (fused.get(h.i) ?? 0) + 1 / (RRF_K + r)));
      this.semantic(opts.queryVector, q).forEach(([i], r) => fused.set(i, (fused.get(i) ?? 0) + 1 / (RRF_K + r)));
      ranked = [...fused].sort((a, b) => b[1] - a[1]).slice(0, 50).map(([i]) => seenAt.get(i) ?? {i, score: 0, version_match: versionCompatible(this.cards[i].version, q.version), match: "semantic"});
      const exact = this.rank(query, q).filter((h) => h.match === "exact-symbol");
      ranked = [...exact, ...ranked.filter((h) => !exact.some((e) => e.i === h.i))];
    }
    for (const h of ranked.slice(0, limit)) {
      const v = this.view(h, detail), cost = Math.ceil(JSON.stringify(v).length / 4);
      if (results.length && used + cost > budget) { truncated = true; break; }
      results.push(v); used += cost;
    }
    const warnings = [];
    if (opts.version && results.length && results.every((r) => r.version_match === "mismatch")) warnings.push(`No card matches version ${opts.version}; showing other versions, verify before use.`);
    const response = {generation: this.generation, query, count: results.length, approx_tokens: used, truncated, warnings, results};
    this.cache.set(key, response);
    return response;
  }
  get(id, detail = "full") {
    this.counters.queries++;
    const i = this.byId.get(id); return i === undefined ? null : this.view({i, version_match: "unspecified", match: "id"}, detail);
  }
  status() {
    return {generation: this.generation, cards: this.cards.length, sha: this.sha, vectors: this.vectors ? {dim: this.vectors.dim, model: this.vectors.model} : null, products: [...new Set(this.cards.map((c) => `${c.product}@${c.version}`))].sort(),
      terms: this.postings.size, cache_entries: this.cache.map.size, cache_evictions: this.cache.evictions, ...this.counters,
      rss_mib: Math.round(process.memoryUsage().rss / 1048576)};
  }
}
