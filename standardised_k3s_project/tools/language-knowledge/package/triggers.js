// Pure helpers for the language-knowledge triggers: find API/flag lookups in (a) tool error text and (b) model reasoning text,
// and format the answer as short, inert reference data. No I/O, no host access: the plugin wires these to hooks.

// ---- (a) tool errors -------------------------------------------------------------------------------------------------
// Each rule turns an engine error into a lookup {product, kind, query}. kind "symbol" = exact symbol, "command" = CLI flag.
const ERROR_RULES = [
  // Tool-error extraction stays scoped to the two runtimes with tested, stable error shapes; the new manuals are primarily
  // YAML/playbook and hardware reference cards, where errors vary by caller and reasoning text is the requested path.
  // Godot (GDScript runtime/parser and CLI)
  {product: "godot", re: /Invalid call\. Nonexistent function '([A-Za-z_]\w*)' in base '([A-Za-z_][\w.]*)'/g, to: (m) => ({kind: "symbol", query: `${m[2]}.${m[1]}`})},
  {product: "godot", re: /Cannot find member "([A-Za-z_]\w*)" in base "([A-Za-z_][\w.]*)"/g, to: (m) => ({kind: "symbol", query: `${m[2]}.${m[1]}`})},
  {product: "godot", re: /Invalid (?:access to property or key|get index) '([A-Za-z_]\w*)'[^\n]{0,40}?(?:base object of type|on base:?) '([A-Za-z_]\w*)/g, to: (m) => ({kind: "symbol", query: `${m[2]}.${m[1]}`})},
  {product: "godot", re: /(?:Function|The method) "([A-Za-z_]\w*)\(\)" (?:not found in base|isn't declared in the current class)(?: ([A-Za-z_]\w*))?/g, to: (m) => ({kind: "symbol", query: m[2] ? `${m[2]}.${m[1]}` : m[1]})},
  {product: "godot", re: /Identifier "([A-Za-z_]\w*)" not declared in the current scope/g, to: (m) => ({kind: "symbol", query: m[1]})},
  {product: "godot", re: /(?:Unrecognized|Unknown|Invalid) (?:command[- ]line )?(?:option|argument)s?[:\s]+'?"?(--?[A-Za-z][\w-]*)/gi, to: (m) => ({kind: "command", query: m[1]})},
  // Blender (bpy and CLI)
  {product: "blender", re: /AttributeError: module '(bpy\.[\w.]+)' has no attribute '([A-Za-z_]\w*)'/g, to: (m) => ({kind: "symbol", query: `${m[1]}.${m[2]}`})},
  {product: "blender", re: /AttributeError: '([A-Za-z_]\w*)' object has no attribute '([A-Za-z_]\w*)'/g, to: (m) => ({kind: "symbol", query: `${m[1]}.${m[2]}`})},
  {product: "blender", re: /Calling operator "(bpy\.ops\.[\w.]+)" error, could not be found/g, to: (m) => ({kind: "symbol", query: m[1]})},
  {product: "blender", re: /(?:unrecognized arguments?|Unknown (?:option|argument))[:\s]+'?"?(--?[A-Za-z][\w-]*)/gi, to: (m) => ({kind: "command", query: m[1]})},
];

export function extractErrorTopics(text, limit = 3) {
  const s = String(text ?? "").slice(0, 200000);
  const seen = new Set(), out = [];
  for (const rule of ERROR_RULES) {
    for (const m of s.matchAll(rule.re)) {
      const topic = {product: rule.product, ...rule.to(m)};
      const key = `${topic.product}|${topic.kind}|${topic.query}`;
      if (seen.has(key)) continue;
      seen.add(key); out.push(topic);
      if (out.length >= limit) return out;
    }
  }
  return out;
}

// ---- (b) reasoning ---------------------------------------------------------------------------------------------------
// "wait" alone is noise: a topic counts only when an uncertainty marker is within WINDOW characters of an API-looking token.
const UNCERTAIN = new RegExp("\\b(?:" + [
  "wait", "hmm+", "not (?:sure|certain)", "unsure", "uncertain", "unclear",
  "let me (?:check|verify|double[- ]check|think|recall|reconsider|investigate|figure|look|remember|re-?read|confirm)",
  "does(?:n't| not)? (?:\\w+ ){0,4}exist", "is there (?:a|an|any)", "if i recall", "is it (?:called|named)", "doesn't exist", "does not exist", "no such",
  // doubts about behaviour rather than names (importers, exporters, file side effects)
  "i (?:believe|suspect|assume)", "i need to (?:determine|find out|check|investigate|confirm|figure out)", "key question", "the question is", "what happens (?:if|when)",
  "does (?:godot|blender|the importer|the \\w+ importer|the (?:fbx|gltf|glb|obj|png|svg|wav) \\w+|it) (?:\\w+ ){0,3}?(?:overwrite|create|write|extract|skip|replace|regenerate|touch|modify|delete)",
  "(?:only|always) (?:writes|creates|overwrites)", "overwrite existing",
].join("|") + ")\\b", "gi");
const WINDOW = 160;
const CANDIDATES = [
  {kind: "symbol", re: /\b(bpy(?:\.[A-Za-z_]\w*){1,6})\b/g, product: "blender"},
  {kind: "symbol", re: /\b([A-Z][A-Za-z0-9]{2,})\.([a-z_][a-z0-9_]{2,})\b/g, join: (m) => `${m[1]}.${m[2]}`},
  // Follow the actual symbol namespaces in the registered non-engine manuals.
  {kind: "symbol", re: /\b(ansible\.module\.[a-z][a-z0-9_.-]*)\b/g, product: "ansible"},
  {kind: "symbol", re: /\b(k8s\.example\.[a-z0-9]+(?:-[a-z0-9]+)+)\b/g, product: "k8s-k3s"},
  {kind: "symbol", re: /\b(rhel\.system-role\.[a-z0-9-]+\.[a-z0-9-]+\.\d+)\b/g, product: "rhel-admin"},
  {kind: "symbol", re: /\b((?:hardware|pinout)\.[a-z0-9]+(?:[-_][a-z0-9]+)*)\b/g, product: "esp32-div"},
  {kind: "symbol", re: /\b(c\.(?:stdlib|posix|preprocessor)\.[a-z0-9_]+)\b/g, product: "c"},
  {kind: "symbol", re: /\b(cpp\.[a-z][a-z0-9_.]*)\b/g, product: "cpp"},
  {kind: "symbol", re: /\b(std::[A-Za-z_]\w*)\b/g, product: "cpp"},
  // Ansible module names are often plain prose rather than canonical IDs.
  {kind: "symbol", re: /\b([a-z][a-z0-9_]{2,})\s+module\b/gi, product: "ansible", bare: true},
  // C function doubts are usually phrased by bare name, no namespace prefix -- restrict to the functions actually carded.
  {kind: "symbol", re: /\b(printf|snprintf|fprintf|malloc|calloc|realloc|memcpy|strlen|strcmp|strncmp|fopen|pthread_create)\b/g, product: "c", bare: true},
  // GCC's C++-specific attribute names, same reasoning: plain prose, not cpp.gcc.attribute.* IDs.
  {kind: "symbol", re: /\b(abi_tag|init_priority|no_dangling|warn_unused)\b/g, product: "cpp", bare: true},
  {kind: "symbol", re: /\b([a-z_][a-z0-9_]{3,})\(\)/g, bare: true},
  {kind: "command", re: /(?<![\w-])(--[a-z][a-z0-9-]{2,})\b/g},
];
const GODOT_HINT = /\b(?:godot|gdscript|\.gd\b|node3d|node2d|packedscene|res:\/\/|signal|@export|@onready)/i;
const BLENDER_HINT = /\b(?:blender|bpy|\.blend\b|mesh|armature|bmesh|operator)/i;
const PRODUCT_HINTS = {
  ansible: /\b(?:ansible|ansible\.builtin|playbook|ansible module)\b/i,
  "k8s-k3s": /\b(?:kubernetes|k8s|kubectl|k3s|manifest|clusterrole|pod spec)\b/i,
  "rhel-admin": /\b(?:rhel|red hat|system role|linux system role|certificate_trust)\b/i,
  "esp32-div": /\b(?:esp32(?:-div)?|gpio\d+|ili9341|xpt2046|nrf24|cc1101)\b/i,
};


// ---- importer options -------------------------------------------------------------------------------------------------
// Godot writes every importer option into the asset's `.import` file; cards of kind import_option document them. Two ways in:
// an option key such as `fbx/embedded_image_handling` near a doubt, or an importer-behaviour doubt ("does the FBX importer overwrite ...").
const IMPORT_KEY = /\b(?:animation|array_mesh|fbx|gltf|import_script|materials|mesh_library|meshes|nodes|skins|compress|detect_3d|mipmaps|process|roughness|svg|edit|force|editor)\/[a-z][a-z0-9_]{2,}\b/g;
const IMPORT_WORD = /\bimport(?:s|ed|er|ers|ing)?\b|\.import\b/i;
const IMPORT_FORMAT = /\b(fbx|gltf|glb|obj|png|svg|wav|csv|jpe?g|webp)\b/i;
const OPTION_WORDS = /\b(embedded|extract(?:ed|s|ion)?|texture[s]?|image[s]?|material[s]?|compress(?:ion|ed)?|mipmaps?|lods?|tangents?|lightmap|shadow|skeleton|skin[s]?|animation[s]?|scale|root|naming|importer|discard|embed|basis|vram|lossless|lossy|normal)\b/gi;

function importTopics(s, marks, near) {
  const out = [];
  for (const m of s.matchAll(IMPORT_KEY)) if (near(m.index)) out.push({product: "godot", kind: "import", query: m[0].toLowerCase(), exact: true});
  for (const p of marks) {
    const seg = s.slice(Math.max(0, p - 220), p + 520);
    if (!IMPORT_WORD.test(seg)) continue;
    const ext = (IMPORT_FORMAT.exec(seg) ?? [])[1]?.toLowerCase();
    const words = [...new Set([...seg.matchAll(OPTION_WORDS)].map((m) => m[1].toLowerCase()))].slice(0, 6);
    if (!words.length) continue;
    out.push({product: "godot", kind: "import", query: [ext, ...words].filter(Boolean).join(" "), ext, exact: false});
    break;
  }
  return out;
}

export function extractReasoningTopics(text, limit = 3) {
  const s = String(text ?? "").slice(-6000);   // the latest reasoning is what matters; bound the scan
  const marks = [...s.matchAll(UNCERTAIN)].map((m) => m.index);
  if (!marks.length) return [];
  const near = (index) => marks.some((p) => Math.abs(p - index) <= WINDOW);
  const productOf = (explicit) => {
    if (explicit) return explicit;
    const matches = [GODOT_HINT.test(s) && "godot", BLENDER_HINT.test(s) && "blender", ...Object.entries(PRODUCT_HINTS).map(([p, re]) => re.test(s) && p)].filter(Boolean);
    return matches.length === 1 ? matches[0] : undefined;
  };
  const seen = new Set(), out = [];
  for (const t of importTopics(s, marks, near)) {
    const key = `${t.kind}|${t.query}`;
    if (seen.has(key)) continue;
    seen.add(key); out.push(t);
    if (out.length >= limit) return out;
  }
  for (const c of CANDIDATES) {
    for (const m of s.matchAll(c.re)) {
      if (!near(m.index)) continue;
      const query = c.join ? c.join(m) : m[1];
      if (/^(?:e|i)\.g$|^(?:self|math|json|os|sys)\./i.test(query)) continue;   // prose and non-engine namespaces
      const key = `${c.kind}|${query}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push({product: productOf(c.product), kind: c.kind, query, bare: Boolean(c.bare)});
      if (out.length >= limit) return out;
    }
  }
  return out;
}

// ---- answers ---------------------------------------------------------------------------------------------------------
const clip = (s, n) => (String(s ?? "").length > n ? String(s).slice(0, n - 1) + "…" : String(s ?? ""));

// Is `owner` a documented class/namespace? True if a card for it exists or any member card starts with "owner." (data may hold members only).
function ownerKnown(engine, product, owner, base) {
  if (Array.isArray(engine.cards)) return engine.cards.some((c) => c.product === product && typeof c.symbol === "string" && (c.symbol === owner || c.symbol.startsWith(owner + ".")));
  return engine.search(owner, {...base, limit: 3}).results.some((r) => r.match === "exact-symbol");
}

// engine: {search(query, opts)}; returns {topic, line} or null when there is nothing trustworthy to say.
// Blender cards are named bpy.types.<Struct>.<member>; reasoning and code often say <Struct>.<member>.
const blenderForms = (query) => (/^[A-Z]\w*\./.test(query) ? [`bpy.types.${query}`, query] : [query]);
const productForms = (product, query) => product === "blender" ? blenderForms(query)
  : product === "ansible" && /^[a-z][a-z0-9_]*$/i.test(query) ? [`ansible.module.ansible.builtin.${query}`, query]
  : product === "c" && /^[a-z_][a-z0-9_]*$/i.test(query) ? [`c.stdlib.${query}`, `c.posix.${query}`, `c.preprocessor.${query}`, query]
  : product === "cpp" ? (/^std::([A-Za-z_]\w*)$/.test(query) ? [`cpp.std.string.${query.slice(5)}`, query] : [`cpp.gcc.attribute.${query}`, query])
  : [query];
function editDistance(a, b) {
  const row = Array.from({length: b.length + 1}, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    let prev = row[0]; row[0] = i;
    for (let j = 1; j <= b.length; j++) { const keep = row[j]; row[j] = Math.min(row[j] + 1, row[j - 1] + 1, prev + (a[i - 1] === b[j - 1] ? 0 : 1)); prev = keep; }
  }
  return row[b.length];
}
// members of a documented owner that look like what was meant (typo, missing/extra letter, same prefix): "use_node" -> use_nodes
function similarMembers(engine, product, owner, member, base, limit = 3) {
  if (!Array.isArray(engine.cards) || member.length < 3) return [];
  const prefix = owner + ".";
  const found = [];
  for (const c of engine.cards) {
    if (c.product !== product || typeof c.symbol !== "string" || !c.symbol.startsWith(prefix)) continue;
    const name = c.symbol.slice(prefix.length);
    if (name.includes(".")) continue;
    const d = editDistance(member.toLowerCase(), name.toLowerCase());
    if (d <= 2 || (member.length >= 4 && (name.startsWith(member) || member.startsWith(name)))) found.push({symbol: c.symbol, d});
  }
  found.sort((x, y) => x.d - y.d || x.symbol.localeCompare(y.symbol));
  const out = [];
  for (const f of found.slice(0, limit)) {
    const hit = engine.search(f.symbol, {...base, limit: 3}).results.find((r) => r.match === "exact-symbol");
    if (hit) out.push(clip(hit.signature || hit.symbol, 150));
  }
  return out;
}

function importAnswer(engine, topic, versions) {
  const version = versions.godot;
  const base = {product: "godot", ...(version ? {version} : {}), kind: "import_option", detail: "standard"};
  const line = (hit) => `godot ${hit.version}: ${clip(hit.signature, 120)} (${hit.symbol}) - ${clip(hit.summary, 330)}`;
  if (topic.exact) {
    const hit = engine.search(topic.query, {...base, limit: 3}).results.find((r) => r.match === "exact-symbol");
    return hit ? {topic, line: line(hit)} : null;
  }
  // behaviour doubt: accept a hit only when it clearly is about what the doubt mentions (content words in its symbol/summary, right file type)
  const words = [...new Set(String(topic.query).split(/\s+/).filter((w) => w.length > 3 && w !== topic.ext))];
  for (const hit of engine.search(topic.query, {...base, limit: 5}).results) {
    const text = `${hit.symbol} ${hit.summary ?? ""}`.toLowerCase();
    if (topic.ext && !text.includes("." + topic.ext)) continue;
    if (words.filter((w) => text.includes(w.replace(/s$/, ""))).length >= 2) return {topic, line: line(hit)};
  }
  return null;
}

export function answerTopic(engine, topic, versions = {}) {
  if (topic.kind === "import") return importAnswer(engine, topic, versions);
  // Keep this fallback in sync with manuals/registry.json plus the two existing built-in manuals.
  const products = topic.product ? [topic.product] : ["godot", "blender", "ansible", "k8s-k3s", "rhel-admin", "esp32-div", "c", "cpp"];
  for (const product of products) {
    const version = versions[product];
    const base = {product, ...(version ? {version} : {}), detail: "standard"};
    if (topic.kind === "command") {
      const hit = engine.search(topic.query, {...base, kind: "cli_flag", limit: 3}).results.find((r) => r.match !== "keyword");
      if (hit) return {topic, line: `${product} ${hit.version}: ${clip(hit.signature || hit.symbol, 220)}${hit.summary ? " - " + clip(hit.summary, 200) : ""}`};
      continue;
    }
    const forms = productForms(product, topic.query);
    for (const query of forms) {
      const hit = engine.search(query, {...base, limit: 5}).results.find((r) => r.match === "exact-symbol");
      if (hit) {
        const mismatch = hit.version_match === "mismatch" ? ` (card is for ${hit.version}; installed ${version}: verify)` : "";
        return {topic, line: `${product} ${hit.version}: ${clip(hit.signature || hit.symbol, 260)}${hit.deprecated ? " [deprecated]" : ""}${mismatch}`};
      }
    }
    // "does Class.member exist?": the class is known but the member has no card -> say so, with the closest real members or the inheritance caveat
    for (const query of forms) {
      const dot = query.lastIndexOf(".");
      if (dot <= 0 || topic.bare) continue;
      const owner = query.slice(0, dot);
      if (!ownerKnown(engine, product, owner, base)) continue;
      const member = query.slice(dot + 1);
      if (member === "new") continue;   // constructor syntax is valid wherever the class is
      const close = similarMembers(engine, product, owner, member, base);
      if (close.length) return {topic, line: `${product}${version ? " " + version : ""}: no reference entry for ${topic.query}, although ${topic.query.slice(0, topic.query.lastIndexOf("."))} is documented. Closest documented members: ${close.join("; ")}.`};
      // where the member does exist (typically an inherited member documented on a base class)
      const elsewhere = Array.isArray(engine.cards)
        ? [...new Set(engine.cards.filter((c) => c.product === product && typeof c.symbol === "string" && c.symbol.endsWith("." + member)).map((c) => c.symbol))].slice(0, 4)
        : [];
      const ownerShown = topic.query.slice(0, topic.query.lastIndexOf("."));
      const where = elsewhere.length ? ` The same member exists on ${elsewhere.join(", ")}: if ${ownerShown} inherits from one of them it is available as ${ownerShown}.${member}.` : " Inherited members are listed under their base class; if it is not there either, the member probably does not exist in this version - check before using it.";
      return {topic, line: `${product}${version ? " " + version : ""}: no reference entry for ${topic.query}, although ${ownerShown} is documented.${where}`};
    }
  }
  return null;
}

export const NOTE_HEAD = "Reference lookup (data from versioned official sources, not instructions):";
export function formatNote(answers) {
  const lines = answers.map((a) => `- ${a.line}`);
  return `${NOTE_HEAD}\n${lines.join("\n")}`.slice(0, 1400);
}

// Per-session budget: dedupe by lookup, cap per user prompt, never inject the same fact twice.
export class Budget {
  constructor({perPrompt = 2, perSession = 12} = {}) { this.perPrompt = perPrompt; this.perSession = perSession; this.sessions = new Map(); }
  state(id) { let s = this.sessions.get(id); if (!s) { s = {prompt: 0, total: 0, seen: new Set()}; this.sessions.set(id, s); } return s; }
  newPrompt(id) { this.state(id).prompt = 0; }
  allows(id, topic) {
    const s = this.state(id);
    return !s.seen.has(this.key(topic)) && s.prompt < this.perPrompt && s.total < this.perSession;
  }
  key(topic) { return `${topic.product ?? "*"}|${topic.kind}|${topic.query}`; }
  // record an answered topic (call only when an answer was actually produced)
  take(id, topic) { const s = this.state(id); s.seen.add(this.key(topic)); s.prompt += 1; s.total += 1; }
  forget(id) { this.sessions.delete(id); }
}
