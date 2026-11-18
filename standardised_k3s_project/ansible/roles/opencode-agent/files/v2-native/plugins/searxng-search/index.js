// Native Promise-plugin provider: reuse OpenCode's websearch registry and tool.
// SearXNG merges many engines (~50-170 hits); keep the top 30, not the first 10.
const MAX_RESULTS = 30;
function queriesFor(query) {
  // Preserve quoted phrases while progressively relaxing over-specific queries.
  const terms = (query.match(/"[^"]*"|\S+/g) || []).flatMap(term => {
    if (term.startsWith('"')) return [term];
    if (/^v?\d+(?:\.\d+)+(?:[-+]\S+)?$/.test(term)) return [];
    return term.replace(/(\w)-(\w)/g, "$1 $2").split(/\s+/);
  });
  return [...new Set([query, ...[4, 2].filter(n => terms.length >= n).map(n => terms.slice(0, n).join(" "))])];
}

export async function search(query, signal, fetcher = fetch) {
  if (typeof query !== "string" || !query.trim() || query.length > 2000) throw new Error("Search query must contain 1-2000 characters");
  const original = query.trim();
  // All retries share one deadline and the caller's cancellation signal.
  const timeout = AbortSignal.timeout(20000);
  const requestSignal = signal ? AbortSignal.any([signal, timeout]) : timeout;
  const failures = new Set();
  // SearXNG has no boolean operators; a literal OR/AND makes engines match unrelated pages.
  const cleaned = original.replace(/\s+(?:OR|AND)\s+/g, " ").replace(/\s+/g, " ").trim() || original;
  const queries = queriesFor(cleaned);
  for (const current of queries) {
    requestSignal.throwIfAborted();
    const url = new URL("http://searxng.searxng.svc.cluster.local:8080/search");
    url.searchParams.set("q", current);
    url.searchParams.set("format", "json");
    const response = await fetcher(url, {signal: requestSignal, headers: {Accept: "application/json"}, redirect: "error"});
    if (!response.ok) throw new Error("SearXNG HTTP " + response.status);
    const text = await response.text();
    if (text.length > 2 * 1024 * 1024) throw new Error("SearXNG response exceeds 2MiB");
    const data = JSON.parse(text);
    if (!Array.isArray(data.results)) throw new Error("Invalid SearXNG results");
    for (const item of (Array.isArray(data.unresponsive_engines) ? data.unresponsive_engines : []).slice(0, 10)) {
      if (Array.isArray(item)) failures.add(item.map(x => String(x).slice(0, 200)).join(": "));
    }
    const seen = new Set();
    const results = data.results.flatMap(item => {
      if (!item || typeof item.url !== "string") return [];
      let target; try { target = new URL(item.url); } catch { return []; }
      if (!["http:", "https:"].includes(target.protocol) || seen.has(target.href)) return [];
      seen.add(target.href);
      return [{url: target.href, title: String(item.title || "").slice(0, 500), content: String(item.content || "").slice(0, 4000), time: {}}];
    }).slice(0, MAX_RESULTS);
    if (!results.length) continue;
    if (current !== original) {
      results[0].content = ("[Search broadened from " + JSON.stringify(original) + " to " + JSON.stringify(current) + "; verify relevance.]\n" + results[0].content).slice(0, 4000);
    }
    return results;
  }
  throw new Error("SearXNG returned no usable results after " + queries.length + " attempt(s)."
    + (failures.size ? " Upstream engine errors: " + [...failures].join("; ") + "." : "")
    + " Try a different focused query or an authoritative source directly.");
}
export default {
  id: "watoom.websearch.searxng",
  async setup(ctx) {
    await ctx.websearch.transform(editor => {
      editor.add({id: "searxng", name: "SearXNG (WatooM)", execute: (input, context) => search(input.query, context.signal)});
    });
  }
};
