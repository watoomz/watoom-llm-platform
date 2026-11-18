/* WatooM Command Center — live renderer. Pure vanilla JS, no deps/CDN.
 * Polls the helper-api /cc/* JSON endpoints and draws a dataflow topology,
 * instrument tiles and a world attack map. Fail-soft: a failed poll keeps the
 * last-good view and marks the feed stale rather than blanking the page. */
(() => {
  "use strict";
  const SVGNS = "http://www.w3.org/2000/svg";
  const $ = (id) => document.getElementById(id);
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const el = (tag, attrs, text) => {
    const n = document.createElementNS(SVGNS, tag);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    if (text != null) n.textContent = text;
    return n;
  };
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const fmtTime = (iso) => {
    if (!iso) return "";
    const d = new Date(iso);
    return isNaN(d) ? "" : d.toLocaleTimeString();
  };

  let lastOK = 0;
  async function getJSON(path) {
    const r = await fetch(path, { cache: "no-store" });
    if (!r.ok) throw new Error(path + " -> " + r.status);
    return r.json();
  }

  // ---- header liveness ----------------------------------------------------
  function markLive(ok) {
    const dot = $("live-dot"), txt = $("live-txt");
    if (ok) { lastOK = Date.now(); dot.classList.remove("stale"); txt.textContent = "live · " + new Date().toLocaleTimeString(); }
    else { dot.classList.add("stale"); txt.textContent = "stale · retrying"; }
  }

  // ---- status strip -------------------------------------------------------
  const sev = (v, warn, bad) => (v >= bad ? "bad" : v >= warn ? "warn" : "good");
  function strip(m) {
    const g = m.gpu || {}, w = m.wan || {}, h = m.host || {}, k = m.k3s || {}, s = m.services || {};
    const cells = [
      ["CPU", h.cpu_pct, "%", sev(h.cpu_pct, 70, 88)],
      ["Memory", h.mem_used_pct, "%", sev(h.mem_used_pct, 75, 90)],
      ["Disk", h.disk_used_pct, "%", sev(h.disk_used_pct, 80, 92)],
      ["GPU", g.present ? g.util_pct : "—", "%", g.present ? sev(g.util_pct, 101, 102) : ""],
      ["GPU temp", g.present ? g.temp_c : "—", "°C", g.present ? sev(g.temp_c, 78, 86) : ""],
      ["VRAM", g.present ? g.mem_used_pct : "—", "%", g.present ? sev(g.mem_used_pct, 90, 97) : ""],
      ["WAN in", w.present ? w.rx_human : "—", "", ""],
      ["Services", (s.ok != null ? s.ok + "/" + s.total : "—"), "", s.error ? "bad" : "good"],
    ];
    $("strip").innerHTML = cells.map(([kk, v, u, c]) =>
      `<div class="cc-stat"><span class="k">${kk}</span><span class="v ${c}">${v}${u ? `<span class="u"> ${u}</span>` : ""}</span></div>`
    ).join("");
  }

  // ---- instrument tiles ---------------------------------------------------
  function tile(label, valHTML, cls, pct, barCls) {
    const bar = pct != null ? `<div class="cc-bar"><i class="${barCls || ""}" style="width:${clamp(pct, 0, 100)}%"></i></div>` : "";
    return `<div class="cc-tile"><span class="label">${label}</span><span class="val ${cls || ""}">${valHTML}</span>${bar}</div>`;
  }
  const group = (title, tag, tiles) =>
    `<div class="cc-group"><h3>${title}${tag ? `<span class="tag">${tag}</span>` : ""}</h3>` +
    `<div class="cc-tiles">${tiles.join("")}</div></div>`;
  const uptime = (s) => {
    if (!s) return "—";
    const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600);
    return d > 0 ? `${d}d ${h}h` : `${h}h ${Math.floor((s % 3600) / 60)}m`;
  };
  function tiles(m) {
    const g = m.gpu || {}, w = m.wan || {}, h = m.host || {}, k = m.k3s || {}, s = m.services || {};
    const groups = [];

    const server = [
      tile("Host load", `${h.load1} <span class="cc-dim">/ ${h.cpu_cores}c</span>`, sev(h.cpu_pct, 70, 88), h.cpu_pct, sev(h.cpu_pct, 70, 88)),
      tile("Memory free", h.mem_available || "—", sev(h.mem_used_pct, 75, 90), h.mem_used_pct, sev(h.mem_used_pct, 75, 90)),
      tile("Disk free", h.disk_available || "—", sev(h.disk_used_pct, 80, 92), h.disk_used_pct, sev(h.disk_used_pct, 80, 92)),
      tile("Uptime", uptime(h.uptime_s), "", null),
    ];
    groups.push(group("Server", `${h.cpu_cores}c`, server));

    if (g.present) {
      groups.push(group("GPU", "GPU · 20 Gi", [
        tile("GPU util", g.util_pct + "%", "", g.util_pct, "good"),
        tile("GPU power", g.power_w + " W", "", null),
        tile("GPU temp", g.temp_c + " °C", sev(g.temp_c, 78, 86), null),
        tile("VRAM", `${(g.mem_used_mib / 1024).toFixed(1)}/${(g.mem_total_mib / 1024).toFixed(1)} Gi`, sev(g.mem_used_pct, 90, 97), g.mem_used_pct, sev(g.mem_used_pct, 90, 97)),
      ]));
    }

    const issueCount = Array.isArray(s.issues) ? s.issues.length : (s.issues ?? 0);
    const cluster = [
      tile("Pods running", String(k.pods_running ?? "—"), "good", null),
      tile("Pods failed", String(k.pods_failed ?? 0), k.pods_failed ? "bad" : "good", null),
    ];
    if (k.pods_pending) cluster.push(tile("Pods pending", String(k.pods_pending), "warn", null));
    cluster.push(tile("Service issues", String(issueCount), issueCount ? "serious" : "good", null));
    groups.push(group("Cluster (k3s)", `${s.ok ?? "—"}/${s.total ?? "—"} up`, cluster));

    const net = [];
    if (h.net_rx_human) net.push(tile("Host net rx / tx", `${h.net_rx_human} <span class="cc-dim">/</span> ${h.net_tx_human}`, "", null));
    if (w.present) {
      net.push(tile("WAN rx / tx", `${w.rx_human} <span class="cc-dim">/</span> ${w.tx_human}`, "", null));
      net.push(tile("WAN drops/s", String(w.wan_drops_per_s ?? 0), (w.wan_drops_per_s || 0) > 0 ? "warn" : "good", null));
      net.push(tile("Router CPU", w.router_cpu_pct + "%", sev(w.router_cpu_pct, 60, 85), w.router_cpu_pct, sev(w.router_cpu_pct, 60, 85)));
    }
    if (net.length) groups.push(group("Network", null, net));

    $("tiles").innerHTML = groups.join("");
  }

  // ---- LLM serving panel --------------------------------------------------
  function llm(m) {
    const L = m.llm || {};
    $("llm-ts").textContent = fmtTime(m.ts) || "";
    if (!L.present) {
      $("llm-head").innerHTML = `<div class="m"><span class="k">serving</span><span class="v">— <small>no llama feed</small></span></div>`;
      $("llm-table").innerHTML = "";
      return;
    }
    const active = L.models.find((x) => x.up) || null;
    const headCell = (k, v, cls) => `<div class="m"><span class="k">${k}</span><span class="v ${cls || ""}">${v}</span></div>`;
    $("llm-head").innerHTML = [
      headCell("GPU owner", active ? `<span title="${active.model}">${active.model}</span>` : "idle <small>no lease</small>", active ? "accent" : "warn"),
      headCell("Gen throughput", active && active.gen_tps != null ? `${active.gen_tps}<small> tok/s</small>` : "—", ""),
      headCell("In flight", `${L.requests_processing}<small> proc · ${L.requests_deferred} queued</small>`, L.requests_deferred ? "warn" : ""),
      headCell("Router 30m", `${L.router_req_30m}<small> req · ${L.router_fail_30m} fail</small>`, L.router_fail_30m ? "warn" : "good"),
    ].join("");

    const cell = (v, u, extra) => `<span class="n ${v == null ? "dim" : ""}${extra ? " " + extra : ""}">${v == null ? "—" : v}${v != null && u ? `<span class="u"> ${u}</span>` : ""}</span>`;
    const ctxHuman = (n) => (n == null ? null : n >= 1000 ? Math.round(n / 1000) + "k" : String(n));
    const rows = [
      `<div class="r head"><span>Model</span><span class="n">tok/s</span><span class="n">context</span><span class="n c4">MTP acc.</span><span class="n">slots</span></div>`,
    ];
    L.models.forEach((x) => {
      rows.push(`<div class="r ${x.up ? "on" : ""}">` +
        `<span class="mdl"><i class="led"></i><b>${x.model}</b>${x.up ? ' <span class="cc-dim">· owner</span>' : ""}</span>` +
        cell(x.gen_tps) +
        cell(ctxHuman(x.ctx_max), "tok") +
        cell(x.mtp_accept_pct == null ? null : x.mtp_accept_pct + "%", "", "c4") +
        cell(x.slots) +
        `</div>`);
    });
    $("llm-table").innerHTML = rows.join("");
  }

  // ---- topology -----------------------------------------------------------
  const POS = {
    wan: [95, 260], edge: [260, 260], ingress: [440, 260],
    media: [660, 110], llm: [660, 260], platform: [660, 410], observability: [885, 260],
  };
  const NW = 150, NH = 56;
  const cx = (id) => (POS[id] ? POS[id][0] + NW / 2 : 0);
  const cy = (id) => (POS[id] ? POS[id][1] + NH / 2 : 0);
  function topology(t) {
    const svg = $("flow");
    svg.innerHTML = "";
    const prev = topology._prev || {};
    const now = {};
    (t.nodes || []).forEach((n) => (now[n.id] = n.status));
    // edges first (under nodes)
    (t.edges || []).forEach((e) => {
      if (!POS[e.from] || !POS[e.to]) return;
      const x1 = cx(e.from), y1 = cy(e.from), x2 = cx(e.to), y2 = cy(e.to);
      const mx = (x1 + x2) / 2;
      const d = `M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`;
      svg.appendChild(el("path", { d, class: "edge" }));
      const cls = e.severity === "error" ? "edge-error" : "edge-flow";
      svg.appendChild(el("path", { d, class: cls }));
    });
    // nodes
    (t.nodes || []).forEach((n) => {
      if (!POS[n.id]) return;
      const [x, y] = POS[n.id];
      const g = el("g", {});
      g.appendChild(el("rect", { x, y, width: NW, height: NH, rx: 6, class: "node-box " + n.status }));
      g.appendChild(el("circle", { cx: x + 14, cy: y + 15, class: "node-led " + n.status }));
      g.appendChild(el("text", { x: x + 28, y: y + 20, class: "node-label" }, n.label));
      if (n.detail) g.appendChild(el("text", { x: x + 12, y: y + 42, class: "node-detail" }, n.detail));
      // flash newly-degraded nodes
      if (!reduce && prev[n.id] && prev[n.id] !== n.status && n.status !== "ok") {
        const fl = el("rect", { x: x - 3, y: y - 3, width: NW + 6, height: NH + 6, rx: 8,
          fill: "none", stroke: "var(--critical)", "stroke-width": 2 });
        fl.appendChild(el("animate", { attributeName: "stroke-opacity", from: "1", to: "0", dur: "1.4s", repeatCount: "3" }));
        g.appendChild(fl);
      }
      svg.appendChild(g);
    });
    topology._prev = now;
    $("flow-ts").textContent = fmtTime(t.ts);
  }

  // ---- world attack map ---------------------------------------------------
  const MW = 1000, MH = 500;
  const px = (lon) => (lon + 180) / 360 * MW;
  const py = (lat) => (90 - lat) / 180 * MH;
  // Two persistent layers so the scan markers ("radars") always paint ABOVE the
  // land, regardless of when the async geojson fetch resolves. The base layer is
  // created first (graticule + opaque land); the hit layer is created after it in
  // document order, and SVG paint order = document order.
  let landDrawn = false;
  function mapLayers() {
    const svg = $("map");
    let base = svg.querySelector("g.map-base");
    let hits = svg.querySelector("g.map-hits");
    if (!base) { base = el("g", { class: "map-base" }); svg.appendChild(base); }
    if (!hits) { hits = el("g", { class: "map-hits" }); svg.appendChild(hits); }
    return { base, hits };
  }
  async function drawLand(base) {
    if (landDrawn) return;
    for (let lon = -150; lon <= 150; lon += 30) base.appendChild(el("line", { x1: px(lon), y1: 0, x2: px(lon), y2: MH, class: "graticule" }));
    for (let lat = -60; lat <= 60; lat += 30) base.appendChild(el("line", { x1: 0, y1: py(lat), x2: MW, y2: py(lat), class: "graticule" }));
    try {
      const geo = await getJSON("/command-center/world-land-110m.geojson");
      const path = (ring) => "M" + ring.map(([lon, lat]) => `${px(lon).toFixed(1)} ${py(lat).toFixed(1)}`).join(" L") + "Z";
      (geo.features || []).forEach((f) => {
        const gm = f.geometry; if (!gm) return;
        const polys = gm.type === "Polygon" ? [gm.coordinates] : gm.type === "MultiPolygon" ? gm.coordinates : [];
        polys.forEach((poly) => { const d = poly.map(path).join(" "); base.appendChild(el("path", { d, class: "land" })); });
      });
      landDrawn = true;
    } catch (e) { /* no land outline -> bubbles still plot over graticule */ }
  }
  function tip(ev, html) {
    const t = $("cc-tip");
    if (!html) { t.classList.remove("on"); return; }
    t.innerHTML = html; t.classList.add("on");
    t.style.left = Math.min(ev.clientX + 14, innerWidth - 250) + "px";
    t.style.top = (ev.clientY + 14) + "px";
  }
  function attacks(a) {
    const { base, hits } = mapLayers();
    drawLand(base);            // populate the base layer (behind) — async-safe
    hits.textContent = "";     // clear only the marker layer
    $("atk-ts").textContent = fmtTime(a.ts) || "";
    if (!a.present) { $("atk-sum").textContent = "no firewall log feed"; return; }
    if (!a.geo) $("atk-sum").textContent = `${a.total_events} drops · ${a.unique_sources} sources · geo table absent`;
    else $("atk-sum").textContent = `${a.total_events} drops · ${a.unique_sources} sources · ${(a.countries || []).length} countries · ${a.window_hours}h`;

    const cs = (a.countries || []).filter((c) => c.cc !== "??" && (c.lat || c.lon));
    const max = cs.reduce((m, c) => Math.max(m, c.count), 1);
    const prevCount = attacks._max || 0;
    cs.forEach((c, i) => {
      const r = 3 + Math.sqrt(c.count / max) * 17;
      const hot = i === 0 || c.count >= max * 0.6;
      const dot = el("circle", { cx: px(c.lon).toFixed(1), cy: py(c.lat).toFixed(1), r: r.toFixed(1),
        class: "hit" + (hot ? " hot" : "") + (!reduce && a.total_events > prevCount ? " pulse" : "") });
      dot.addEventListener("mousemove", (ev) => tip(ev, `<b>${c.name}</b> (${c.cc})<br>${c.count} drops · ${c.sources} src`));
      dot.addEventListener("mouseleave", () => tip(null));
      hits.appendChild(dot);
    });
    attacks._max = a.total_events;

    // home marker (public IP) — AU centroid if geo known for it, else lower-right
    const pub = a.public_ip;
    const home = el("circle", { cx: px(133).toFixed(1), cy: py(-27).toFixed(1), r: 4.5, class: "home" });
    home.addEventListener("mousemove", (ev) => tip(ev, `<b>public IP</b><br>${pub || "—"}`));
    home.addEventListener("mouseleave", () => tip(null));
    hits.appendChild(home);

    // leaderboard
    $("atk-top").innerHTML = (a.countries || []).filter((c) => c.cc !== "??").slice(0, 8)
      .map((c) => `<div class="row"><span class="cc">${c.cc} ${c.name}</span><span class="ct">${c.count}</span></div>`).join("")
      || `<div class="row"><span class="cc cc-dim">no geolocated sources</span><span class="ct"></span></div>`;
  }

  // ---- poll loop ----------------------------------------------------------

  // ---- workers (Bazzite / RIG) ---------------------------------------------
  // Everything from the snapshot is set with textContent: failure reasons come from job output and must never be parsed as HTML.
  const WK_LABEL = { bazzite: "Bazzite", rig: "RIG", server: "Server", moss: "MOSS Image", meshy: "Meshy" };
  let wkFilter = "all", wkLast = null, wkRows = 16;
  const dur = (s) => {
    if (s == null || !isFinite(s)) return "";
    s = Math.max(0, Math.round(s));
    return s < 60 ? s + "s" : s < 3600 ? Math.floor(s / 60) + "m " + (s % 60) + "s" : Math.floor(s / 3600) + "h " + Math.floor((s % 3600) / 60) + "m";
  };
  const ago = (t, now) => (t ? dur(now - t) + " ago" : "—");
  const clock = (t) => (t ? new Date(t * 1000).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "—");
  const gb = (b) => (b == null ? "—" : (b / 2 ** 30).toFixed(1) + " GiB");
  const OUTCOME = {
    completed: ["PASS", "good"], failed: ["FAILED", "bad"], running: ["RUNNING", "accent"], queued_or_running: ["PENDING", "accent"],
    stale: ["STALE", "warn"], stale_running: ["STALE RUNNING", "warn"], needs_review: ["REVIEW", "warn"], unknown: ["UNKNOWN", ""],
  };
  const h = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; };
  const chip = (state) => { const [t, c] = OUTCOME[state] || OUTCOME.unknown; return h("span", "chip " + c, t); };

  function wkCard(kind, w, now) {
    const card = h("div", "cc-wk");
    const top = h("div", "top");
    top.append(h("span", "led"), h("span", "name", WK_LABEL[kind] || kind));
    const lines = [], facts = [];
    let state = "unknown", label = "unknown";
    if (kind === "bazzite") {
      if (w.reachable === false) { state = "offline"; label = "offline"; lines.push(["Unreachable over SSH", w.error || ""]); }
      else if (w.reachable === true) {
        state = w.busy ? "working" : "idle"; label = w.busy ? "working" : "idle";
        for (const u of w.units || []) {
          lines.push([[u.label, u.name, u.project].filter(Boolean).join(" · "),
            [u.started ? "running " + dur(now - u.started) : "", u.memory_limit ? "limit " + u.memory_limit : "", u.deadline_seconds ? "deadline " + u.deadline_seconds + "s" : ""].filter(Boolean).join(" · ")]);
        }
        if (!(w.units || []).length) for (const j of w.running_jobs || []) lines.push([[j.operation, j.name, j.project].filter(Boolean).join(" · "), (j.started ? "running " + dur(now - j.started) + " · " : "") + "preparing: copying project files, then launching"]);
        facts.push("free RAM " + gb(w.free_ram_bytes));
      }
      facts.push("checked " + ago(w.checked, now));
    } else {
      state = w.online ? (w.busy ? "working" : "idle") : "offline";
      label = w.online ? (w.busy ? "job pending" : "idle") : "quiet";
      for (const j of w.waiting_or_running || []) lines.push([[j.operation, j.name, j.project].filter(Boolean).join(" · "), "waiting or running · submitted " + ago(j.started, now)]);
      if (!w.online) lines.push(["No contact from the rig", "its transfer account has not logged in recently"]);
      facts.push("last contact " + ago(w.last_contact, now));
    }
    card.classList.add(state);
    top.append(h("span", "state chip " + (state === "working" ? "accent" : state === "idle" ? "good" : state === "offline" ? "bad" : ""), label));
    card.append(top);
    const now_ = h("div", "now");
    if (!lines.length) now_.append(h("div", "none", state === "idle" ? "Nothing running." : ""));
    for (const [a, b] of lines) { now_.append(h("div", "", a)); if (b) now_.append(h("div", "sub", b)); }
    card.append(now_, h("div", "facts"));
    for (const f of facts) card.lastChild.append(h("span", "", f));
    if (kind === "rig" && w.note) card.append(h("div", "facts", w.note));
    return card;
  }


  // Produced outputs of a job: image thumbnails (open the viewable copy), 3D models (open the viewer), videos, other files by name.
  const MEDIA_NAME = /^[A-Za-z0-9._-]{1,64}\/[A-Za-z0-9._-]{1,64}$/;
  const mediaUrl = (rel) => (MEDIA_NAME.test(rel || "") ? "/cc/workers/media/" + rel : null);
  const kib = (b) => (b == null ? "" : b >= 1048576 ? (b / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(b / 1024)) + " KB");
  // Preview visibility: a global default plus per-job flips, remembered in this browser only.
  const wkStore = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* private mode: keep in memory */ } },
  };
  let wkHideAll = wkStore.get("cc.wk.hidePreviews") === "1";
  let wkFlip = new Set();
  try { const v = JSON.parse(wkStore.get("cc.wk.flip") || "[]"); if (Array.isArray(v)) wkFlip = new Set(v.filter((x) => typeof x === "string").slice(-200)); } catch (e) { /* ignore */ }
  const wkSave = () => { wkStore.set("cc.wk.hidePreviews", wkHideAll ? "1" : "0"); wkStore.set("cc.wk.flip", JSON.stringify([...wkFlip].slice(-200))); };
  const wkHidden = (key) => wkHideAll !== wkFlip.has(key);
  const wkToggleRow = (key) => { if (wkFlip.has(key)) wkFlip.delete(key); else wkFlip.add(key); wkSave(); workers(wkLast); };
  function outputsBlock(outputs, key) {
    const hidden = wkHidden(key);
    const kinds = [...new Set(outputs.map((o) => (o.kind === "model" ? "3D model" : o.kind || "file")))].join(", ");
    const wrap = h("div", "outwrap");
    const btn = h("button", "outtoggle", (hidden ? "▸ " : "▾ ") + outputs.length + (outputs.length === 1 ? " preview" : " previews") + " (" + kinds + ")" + (hidden ? " hidden" : ""));
    btn.type = "button"; btn.setAttribute("aria-expanded", String(!hidden));
    btn.title = hidden ? "Show previews for this job" : "Hide previews for this job";
    btn.addEventListener("click", () => wkToggleRow(key));
    wrap.append(btn);
    if (!hidden) wrap.append(outputsStrip(outputs));  // hidden previews are not rendered, so their images are never fetched
    return wrap;
  }
  function outputsStrip(outputs) {
    const box = h("div", "outs");
    for (const o of outputs) {
      let a = null;
      if (o.kind === "image" && mediaUrl(o.view) && mediaUrl(o.thumb)) {
        a = h("a", "out img"); a.href = mediaUrl(o.view); a.target = "_blank"; a.rel = "noopener";
        const im = document.createElement("img"); im.loading = "lazy"; im.src = mediaUrl(o.thumb); im.alt = o.name || "image";
        im.title = (o.name || "") + (o.width ? " (" + o.width + "×" + o.height + ", original " + kib(o.bytes) + ")" : "");
        a.append(im, h("span", "cap", o.name || "image"));
      } else if (o.kind === "model" && MEDIA_NAME.test(o.model || "")) {
        a = h("a", "out mdl"); a.target = "_blank"; a.rel = "noopener";
        a.href = "/command-center/viewer.html?m=" + encodeURIComponent(o.model).replace("%2F", "/") + "&n=" + encodeURIComponent(o.name || "model.glb");
        a.append(h("span", "cube", "3D"), h("span", "cap", "View " + (o.name || "model")), h("span", "sz", kib(o.bytes)));
      } else if (o.kind === "video" && mediaUrl(o.video)) {
        a = h("a", "out vid", "▶ " + (o.name || "video")); a.href = mediaUrl(o.video); a.target = "_blank"; a.rel = "noopener";
      } else {
        a = h("span", "out file", (o.name || "file") + (o.bytes != null ? " · " + kib(o.bytes) : ""));
      }
      box.append(a);
    }
    return box;
  }

  function workers(d) {
    const ts = $("wk-ts"), cards = $("wk-cards"), table = $("wk-table"), filter = $("wk-filter");
    if (!d || !d.present) {
      ts.textContent = "no data";
      cards.replaceChildren(h("div", "cc-wk", "The worker status collector is not reporting (no snapshot file)."));
      table.replaceChildren(); filter.replaceChildren(); return;
    }
    wkLast = d;
    const now = d.now || Date.now() / 1000;
    ts.textContent = d.stale ? "snapshot " + dur(d.age_s) + " old - collector may be stopped" : "updated " + dur(d.age_s) + " ago";
    ts.style.color = d.stale ? "var(--warn)" : "";
    cards.replaceChildren(wkCard("bazzite", d.bazzite || {}, now), wkCard("rig", d.rig || {}, now));
    const kinds = ["all", "bazzite", "rig", "server", "moss", "meshy"];
    filter.replaceChildren(...kinds.map((k) => {
      const b = h("button", "", k === "all" ? "All" : WK_LABEL[k]);
      b.type = "button"; b.setAttribute("aria-pressed", String(wkFilter === k));
      b.addEventListener("click", () => { wkFilter = k; wkRows = 16; workers(wkLast); });
      return b;
    }));
    const pv = h("button", "pv", wkHideAll ? "Previews: hidden" : "Previews: shown");
    pv.type = "button"; pv.setAttribute("aria-pressed", String(!wkHideAll));
    pv.title = wkHideAll ? "Show all previews" : "Hide all previews (images are not loaded)";
    pv.addEventListener("click", () => { wkHideAll = !wkHideAll; wkFlip = new Set(); wkSave(); workers(wkLast); });
    filter.append(pv);
    const all = (d.jobs || []).filter((j) => wkFilter === "all" || j.worker === wkFilter);
    const jobs = all.slice(0, wkRows);
    const rows = [];
    const head = h("div", "r head");
    for (const t of ["When", "Worker", "Operation", "Job", "Project", "Outcome", "Took"]) head.append(h("span", "", t));
    rows.push(head);
    if (!jobs.length) rows.push(h("div", "empty", "No jobs recorded for this worker."));
    for (const j of jobs) {
      const r = h("div", "r " + (j.state === "failed" ? "bad" : ""));
      r.append(h("span", "mono", clock(j.finished || j.started)), h("span", "", WK_LABEL[j.worker] || j.worker || "—"), h("span", "mono", j.operation || "—"),
        h("span", "mono", j.name || j.id || "—"), h("span", "mono", j.project || "—"), chip(j.state), h("span", "mono", j.seconds != null ? dur(j.seconds) : (j.started && !j.finished ? dur(now - j.started) : "")));
      if (j.detail && j.state !== "queued_or_running") r.append(h("span", "why", j.detail));
      if (j.outputs && j.outputs.length) r.append(outputsBlock(j.outputs, (j.worker || "") + ":" + (j.id || j.name || "")));
      rows.push(r);
    }
    if (all.length > jobs.length) {
      const more = h("button", "more", "Show " + Math.min(16, all.length - jobs.length) + " more of " + (all.length - jobs.length) + " older jobs");
      more.type = "button"; more.addEventListener("click", () => { wkRows += 16; workers(wkLast); });
      rows.push(more);
    }
    table.replaceChildren(...rows);
  }

  function llmPerformance(d) {
    const table = $("llm-performance"), stamp = $("llm-perf-ts");
    if (!d || !d.present) {
      stamp.textContent = "24 h rolling window · no data source";
      table.replaceChildren(h("div", "empty", "Router performance observations are unavailable."));
      return;
    }
    stamp.textContent = "24 h rolling window · latency ms · rates tokens/s";
    const rows = ["low", "medium", "high", "xhigh", "unset", "other"];
    const head = h("div", "r head");
    for (const label of ["Reasoning", "Requests", "Gen tok/s", "Prompt tok/s", "TTFT p50", "Latency p50 / p95", "Errors / 503"]) head.append(h("span", "", label));
    const out = [head];
    const ms = (v) => v == null ? "no data" : Math.round(v) + " ms";
    for (const level of rows) {
      const m = d.levels?.[level] || {};
      const errors = m.requests ? `${m.errors} (${(100 * m.errors / m.requests).toFixed(1)}%) / ${m.http_503} (${(100 * m.http_503 / m.requests).toFixed(1)}%)` : "no data";
      const row = h("div", "r");
      for (const value of [level, String(m.requests || 0), m.generation_tokens_per_second == null ? "no data" : m.generation_tokens_per_second.toFixed(1),
        m.prompt_tokens_per_second == null ? "no data" : m.prompt_tokens_per_second.toFixed(1), ms(m.ttft_p50_ms),
        m.latency_p50_ms == null ? "no data" : `${ms(m.latency_p50_ms)} / ${ms(m.latency_p95_ms)}`, errors]) row.append(h("span", "mono", value));
      out.push(row);
    }
    table.replaceChildren(...out);
  }

  async function poll(path, render, period) {
    try { render(await getJSON(path)); markLive(true); }
    catch (e) { markLive(false); $("foot").innerHTML = `<span class="cc-err">feed error: ${e.message}</span>`; }
    setTimeout(() => poll(path, render, period), period);
  }
  function foot() {
    const age = lastOK ? Math.round((Date.now() - lastOK) / 1000) : "—";
    $("foot").textContent = `WatooM homelab · command center · last good ${age}s ago`;
    setTimeout(foot, 2000);
  }

  poll("/cc/metrics", (m) => { strip(m); tiles(m); llm(m); }, 15000);
  poll("/cc/llm-performance", llmPerformance, 15000);
  poll("/cc/topology", topology, 20000);
  poll("/cc/attacks", attacks, 60000);
  poll("/cc/workers", workers, 10000);
  foot();
})();
