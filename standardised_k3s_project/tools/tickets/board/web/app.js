"use strict";
// Tickets board (kanban-design.md 6). Plain JS, no build step, no library. All model-written text goes in with textContent.
const BASE = location.pathname.replace(/\/[^/]*$/, "");  // the path prefix, e.g. /tickets
const PRIO = { high: 0, normal: 1, low: 2 };
const OWNER_ONLY = ["cancelled", "obsolete"];
const COLLAPSIBLE = ["cancelled", "obsolete"];
const COMPLETED_SHOWN = 20;
let me = null, board = null, etag = null, dragging = null, current = null, showAll = false;
const expanded = {};
const $ = (id) => document.getElementById(id);

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined && text !== null) e.textContent = String(text);
  return e;
}

function store(key, value) {  // per-viewer convenience only; the page works without it
  try { if (value === undefined) return localStorage.getItem("tickets-board:" + key); localStorage.setItem("tickets-board:" + key, value); } catch (e) { return null; }
  return null;
}

function message(text, ok) {
  const m = $("message");
  m.textContent = text || "";
  m.className = ok ? "ok" : "";
  m.hidden = !text;
  if (text) { clearTimeout(message.t); message.t = setTimeout(() => { m.hidden = true; }, ok ? 4000 : 9000); }
}

async function api(method, path, body) {
  const opts = { method, credentials: "same-origin", headers: {} };
  if (body !== undefined) { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
  if (method !== "GET" && me && me.csrf) opts.headers["X-CSRF-Token"] = me.csrf;
  const r = await fetch(BASE + path, opts);
  if (r.status === 401) { location.href = BASE + "/login"; throw new Error("signed out"); }
  let data = null;
  try { data = await r.json(); } catch (e) { data = null; }
  if (!r.ok) { const err = new Error((data && data.error) || ("HTTP " + r.status)); err.status = r.status; throw err; }
  return data;
}

// ---- board -------------------------------------------------------------------------------------------------------
async function refresh(force) {
  if (dragging) return;
  const headers = {};
  if (etag && !force) headers["If-None-Match"] = '"' + etag + '"';
  let r;
  try { r = await fetch(BASE + "/api/board", { credentials: "same-origin", headers }); } catch (e) { message("Board unreachable; retrying"); return; }
  if (r.status === 401) { location.href = BASE + "/login"; return; }
  if (r.status === 304) return;
  if (!r.ok) { message("Board unavailable (" + r.status + ")"); return; }
  board = await r.json();
  etag = board.etag;
  fillFilters();
  render();
}

function fillFilters() {
  const sel = $("f-project"), keep = sel.value || store("project") || "";
  sel.replaceChildren(new Option("All projects", ""));
  const dl = $("projects");
  dl.replaceChildren();
  for (const p of board.projects) { sel.add(new Option(p, p)); dl.appendChild(new Option(p)); }
  sel.value = board.projects.includes(keep) ? keep : "";
}

function labelOf(id) {
  if (!id) return "";
  const a = board && board.agents.find((x) => x.id === id);
  return a ? a.label : id.replace(/^model:/, "").replace(/-/g, " ");
}

function visible(c) {
  const p = $("f-project").value, q = $("f-text").value.trim().toLowerCase();
  if (p && c.project !== p) return false;
  if (q && !(c.id.toLowerCase().includes(q) || c.title.toLowerCase().includes(q))) return false;
  if ($("f-mine").checked && !(c.owner === me.actor || c.lane === me.actor || c.by === me.actor)) return false;
  return true;
}

function byPriority(a, b) { return (PRIO[a.priority] - PRIO[b.priority]) || (b.updated < a.updated ? -1 : b.updated > a.updated ? 1 : 0); }
function byNewest(a, b) { return b.updated < a.updated ? -1 : b.updated > a.updated ? 1 : 0; }

// May the signed-in actor drop this card here? Mirrors the broker rule (6.2); the broker enforces it regardless.
function allowed(c, queue, lane) {
  if (c.queue === queue && (queue !== "wip" || (c.lane || "") === lane)) return false;
  if (me.role === "owner") return true;
  if (OWNER_ONLY.includes(queue) || !c.can.move) return false;
  return queue !== "wip" || lane === me.actor;
}

function cardEl(c) {
  const d = el("div", "card p-" + c.priority);
  d.tabIndex = 0;
  d.dataset.id = c.id;
  d.draggable = true;
  const head = el("div", "chips");
  head.appendChild(el("span", "tid", c.id));
  d.appendChild(head);
  d.appendChild(el("div", "ttl", c.title));
  const chips = el("div", "chips");
  if (c.project) chips.appendChild(el("span", "chip", c.project));
  if (c.owner_label && c.queue !== "wip") chips.appendChild(el("span", "chip", c.owner_label));
  if (c.status === "blocked") chips.appendChild(el("span", "chip blocked", "blocked"));
  if (c.shared) chips.appendChild(el("span", "chip shared", "shared"));
  if (c.note_count) chips.appendChild(el("span", "chip", c.note_count + (c.note_count === 1 ? " note" : " notes")));
  if (c.pending_requests) chips.appendChild(el("span", "chip cr", c.pending_requests + " change req."));
  d.appendChild(chips);
  d.addEventListener("click", () => { location.hash = c.id; });
  d.addEventListener("keydown", (e) => { if (e.key === "Enter") location.hash = c.id; });
  d.addEventListener("dragstart", (e) => {
    dragging = c;
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", c.id);
    document.body.classList.add("dragging");
    for (const z of document.querySelectorAll("[data-queue]")) z.classList.toggle("denied", !allowed(c, z.dataset.queue, z.dataset.lane || ""));
    d.classList.add("moving");
  });
  d.addEventListener("dragend", () => {
    dragging = null;
    document.body.classList.remove("dragging");
    d.classList.remove("moving");
    for (const z of document.querySelectorAll(".over,.denied")) z.classList.remove("over", "denied");
  });
  return d;
}

function zone(queue, lane, cards, limit) {
  const z = el("div", "zone");
  z.dataset.queue = queue;
  if (lane !== undefined) z.dataset.lane = lane;
  const shown = limit ? cards.slice(0, limit) : cards;
  for (const c of shown) z.appendChild(cardEl(c));
  if (!cards.length) z.appendChild(el("div", "empty", queue === "wip" ? "drop here" : "empty"));
  dropTarget(z, queue, lane || "");
  return z;
}

function dropTarget(node, queue, lane) {
  node.addEventListener("dragover", (e) => {
    if (dragging && allowed(dragging, queue, lane)) { e.preventDefault(); node.classList.add("over"); }
  });
  node.addEventListener("dragleave", () => node.classList.remove("over"));
  node.addEventListener("drop", (e) => {
    e.preventDefault();
    node.classList.remove("over");
    const c = dragging;
    if (c && allowed(c, queue, lane)) doMove(c, queue, lane, node.classList.contains("zone") ? node : null);
  });
}

function render() {
  if (!board) return;
  const root = $("board");
  root.replaceChildren();
  const cards = board.tickets.filter(visible);
  const inQueue = (q) => cards.filter((c) => c.queue === q);
  for (const q of board.queues) {
    const list = inQueue(q.id);
    if (COLLAPSIBLE.includes(q.id) && !expanded[q.id]) {
      const col = el("section", "col collapsed");
      col.dataset.queue = q.id;
      col.title = "Show " + q.label;
      const h = el("h2");
      h.appendChild(el("span", "", q.label));
      col.appendChild(h);
      col.appendChild(el("div", "big", list.length));
      col.addEventListener("click", () => { expanded[q.id] = true; render(); });
      dropTarget(col, q.id, "");
      root.appendChild(col);
      continue;
    }
    const col = el("section", "col" + (q.id === "wip" ? " wip" : ""));
    const h = el("h2");
    h.appendChild(el("span", "", q.label));
    h.appendChild(el("span", "count", list.length));
    col.appendChild(h);
    if (COLLAPSIBLE.includes(q.id)) {
      h.title = "Collapse";
      h.addEventListener("click", () => { expanded[q.id] = false; render(); });
    }
    if (q.id === "wip") {
      const lanes = el("div", "lanes");
      for (const l of board.lanes) {
        const mine = list.filter((c) => (c.lane || "") === l.id).sort(byPriority);
        const box = el("div", "lane");
        const lh = el("h3");
        lh.appendChild(el("span", "", l.label));
        lh.appendChild(el("span", "count", mine.length));
        box.appendChild(lh);
        box.appendChild(zone("wip", l.id, mine));
        lanes.appendChild(box);
      }
      col.appendChild(lanes);
    } else if (q.id === "completed") {
      list.sort(byNewest);
      col.appendChild(zone(q.id, undefined, list, showAll ? 0 : COMPLETED_SHOWN));
      if (list.length > COMPLETED_SHOWN) {
        const b = el("button", "more", showAll ? "show newest " + COMPLETED_SHOWN : "show all " + list.length);
        b.type = "button";
        b.addEventListener("click", () => { showAll = !showAll; render(); });
        col.appendChild(b);
      }
    } else {
      col.appendChild(zone(q.id, undefined, list.sort(byPriority)));
    }
    root.appendChild(col);
  }
}

// ---- writes ------------------------------------------------------------------------------------------------------
function askMove(title, noteLabel, required, showPr) {
  return new Promise((resolve) => {
    const d = $("move-dlg"), f = $("move-form");
    f.reset();
    $("move-title").textContent = title;
    $("move-note-label").firstChild.textContent = noteLabel + " ";
    f.elements.note.required = required;
    $("move-pr-label").hidden = !showPr;
    d.returnValue = "";
    d.onclose = () => resolve(d.returnValue === "ok" ? { note: f.elements.note.value, pr: f.elements.pr.value } : null);
    d.showModal();
  });
}

async function doMove(c, queue, lane, zoneNode) {
  let extra = { note: "", pr: "" };
  if (queue === "completed") extra = await askMove("Complete " + c.id, "How was it verified?", false, true);
  else if (OWNER_ONLY.includes(queue)) extra = await askMove((queue === "cancelled" ? "Cancel " : "Mark obsolete ") + c.id, "Reason", true, false);
  if (!extra) { if (current && current.id === c.id) showTicket(current); return render(); }
  const node = document.querySelector('.card[data-id="' + c.id + '"]');
  if (node && zoneNode) { const empty = zoneNode.querySelector(".empty"); if (empty) empty.remove(); zoneNode.prepend(node); }  // optimistic
  const body = { queue, note: extra.note, pr: extra.pr, if_updated: c.updated };
  if (queue === "wip") body.lane = lane;
  try {
    const r = await api("POST", "/api/tickets/" + c.id + "/move", body);
    message(c.id + " moved to " + queue + (queue === "wip" ? " (" + (labelOf(lane) || "Unassigned") + ")" : ""), true);
    afterWrite(r);
  } catch (e) {
    message(c.id + ": " + e.message + (e.status === 409 ? " (reloaded)" : ""));
    etag = null;
    await refresh(true);
    if (current && current.id === c.id) openTicket(c.id);
  }
}

function afterWrite(r) {
  if (r && r.card && board) {
    const i = board.tickets.findIndex((x) => x.id === r.card.id);
    if (i >= 0) board.tickets[i] = r.card;
    render();
  }
  if (r && r.ticket && current && current.id === r.ticket.id) showTicket(r.ticket);
  etag = null;
  refresh(true);
}

async function write(path, body, okText) {
  try {
    const r = await api("POST", path, body);
    if (okText) message(okText, true);
    afterWrite(r);
    return r;
  } catch (e) {
    message(e.message);
    if (e.status === 409 && current) openTicket(current.id);
    return null;
  }
}

// ---- detail panel ------------------------------------------------------------------------------------------------
async function openTicket(id) {
  try { showTicket(await api("GET", "/api/tickets/" + id)); } catch (e) { message(id + ": " + e.message); closePanel(); }
}

function closePanel() {
  current = null;
  $("panel").hidden = true;
  if (location.hash) history.replaceState(null, "", location.pathname + location.search);
}

function option(value, label, selected, disabled) {
  const o = new Option(label, value, false, selected);
  o.disabled = !!disabled;
  return o;
}

function showTicket(t) {
  current = t;
  const can = t.can;
  $("panel").hidden = false;
  $("d-id").textContent = t.id;
  const st = $("d-status");
  st.textContent = t.status;
  st.className = "badge " + t.status;
  const qlabel = (board ? board.queues.find((q) => q.id === t.queue) : null);
  $("d-queue").textContent = (qlabel ? qlabel.label : t.queue) + (t.queue === "wip" ? " / " + (t.owner_label || "Unassigned") : "");
  $("d-title").value = t.title;
  // Move to (the phone fallback for drag and drop)
  const mv = $("d-move");
  mv.replaceChildren();
  const like = { queue: t.queue, lane: t.lane, can };
  for (const q of board.queues) {
    if (q.id === "wip") {
      for (const l of board.lanes) {
        const here = t.queue === "wip" && (t.lane || "") === l.id;
        mv.add(option("wip|" + l.id, q.label + ": " + l.label, here, !here && !allowed(like, "wip", l.id)));
      }
    } else {
      const here = t.queue === q.id;
      mv.add(option(q.id + "|", q.label, here, !here && !allowed(like, q.id, "")));
    }
  }
  mv.disabled = ![...mv.options].some((o) => !o.disabled && !o.selected);
  $("d-priority").value = t.priority;
  $("d-project").value = t.project || "";
  $("d-pr").value = t.pr || "";
  const ow = $("d-owner");
  ow.replaceChildren(option("", "(none)", !t.owner));
  const ids = new Set();
  for (const a of board.agents) { ids.add(a.id); ow.add(option(a.id, a.label, a.id === t.owner)); }
  if (t.owner && !ids.has(t.owner)) ow.add(option(t.owner, t.owner_label || t.owner, true));
  for (const [id, on] of [["d-title", can.edit], ["d-priority", can.edit], ["d-project", can.edit], ["d-pr", can.edit], ["d-body", can.edit], ["d-owner", can.assign], ["d-shared", can.share]]) $(id).disabled = !on;
  $("d-save").disabled = !(can.edit || can.assign);
  const link = $("d-prlink");
  link.replaceChildren();
  if (/^https?:\/\//i.test(t.pr || "")) { const a = el("a", "", t.pr); a.href = t.pr; a.target = "_blank"; a.rel = "noopener noreferrer"; link.appendChild(a); }
  $("d-meta").textContent = "Created by " + (t.by_label || t.by || "-") + " " + t.created + " - updated " + t.updated + (t.source ? " - source " + t.source : "");
  $("d-shared").checked = !!t.shared;
  $("d-blocked-wrap").hidden = t.queue !== "wip";
  $("d-blocked").checked = t.status === "blocked";
  $("d-blocked").disabled = !can.move;
  $("d-body").value = t.body || "";
  $("d-can").textContent = can.edit ? "" : (t.owner ? "Owned by " + (t.owner_label || t.owner) + "; use Request a change." : "Unowned: move it to your lane to claim it, or request a change.");
  // change requests
  const crs = $("d-crs");
  crs.replaceChildren();
  t.change_requests.forEach((c, i) => {
    const li = el("li");
    li.appendChild(el("div", "meta", c.time + " - " + (c.by_label || c.by || "-") + " - " + c.state));
    li.appendChild(el("div", "txt", c.text));
    if (c.state === "pending" && can.decide) {
      const row = el("div", "actions");
      const give = el("button", "", "Give ticket to " + (c.by_label || c.by));
      const share = el("button", "", "Share ticket");
      const reject = el("button", "secondary", "Reject");
      give.type = share.type = reject.type = "button";
      give.addEventListener("click", () => write("/api/tickets/" + t.id + "/change-request/" + i, { decision: "assign" }, "Ticket given to " + (c.by_label || c.by)));
      share.addEventListener("click", () => write("/api/tickets/" + t.id + "/change-request/" + i, { decision: "share" }, "Ticket shared"));
      reject.addEventListener("click", () => {
        const why = window.prompt("Reason (optional)", "");
        if (why !== null) write("/api/tickets/" + t.id + "/change-request/" + i, { decision: "reject", note: why }, "Change request rejected");
      });
      row.append(give, share, reject);
      li.appendChild(row);
    }
    crs.appendChild(li);
  });
  if (!t.change_requests.length) crs.appendChild(el("li", "hint", "None."));
  $("d-cr-new").hidden = !can.change_request;
  // notes, newest first
  const notes = $("d-notes");
  notes.replaceChildren();
  for (const n of [...(t.notes || [])].reverse()) {
    const li = el("li");
    li.appendChild(el("div", "meta", n.time + (n.by ? " - " + (n.by_label || n.by) : "")));
    li.appendChild(el("div", "txt", n.text));
    notes.appendChild(li);
  }
  if (!(t.notes || []).length) notes.appendChild(el("li", "hint", "No updates yet."));
  $("d-note-new").hidden = !can.note;
}

function wireDetail() {
  $("d-close").addEventListener("click", closePanel);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("panel").hidden && !document.querySelector("dialog[open]")) closePanel(); });
  $("d-move").addEventListener("change", (e) => {
    const [queue, lane] = e.target.value.split("|");
    doMove(current, queue, lane, null);
  });
  $("d-save").addEventListener("click", () => {
    const t = current, body = { if_updated: t.updated };
    const fields = { title: "d-title", body: "d-body", priority: "d-priority", project: "d-project", pr: "d-pr" };
    if (t.can.edit) for (const [k, id] of Object.entries(fields)) if ($(id).value !== (t[k] || "")) body[k] = $(id).value;
    if (t.can.assign && $("d-owner").value !== (t.owner || "")) body.owner = $("d-owner").value;
    if (Object.keys(body).length === 1) return message("Nothing changed", true);
    write("/api/tickets/" + t.id + "/edit", body, t.id + " saved");
  });
  $("d-shared").addEventListener("change", (e) => write("/api/tickets/" + current.id + "/edit", { shared: e.target.checked, if_updated: current.updated }, "Sharing " + (e.target.checked ? "on" : "off")));
  $("d-blocked").addEventListener("change", (e) => {
    const body = { queue: "wip", blocked: e.target.checked, if_updated: current.updated };
    if (me.role === "owner") body.lane = current.lane || "";
    write("/api/tickets/" + current.id + "/move", body, current.id + (e.target.checked ? " blocked" : " unblocked"));
  });
  $("d-note-send").addEventListener("click", async () => {
    const box = $("d-note-text");
    if (!box.value.trim()) return;
    if (await write("/api/tickets/" + current.id + "/note", { text: box.value }, "Update added")) box.value = "";
  });
  $("d-cr-send").addEventListener("click", async () => {
    const box = $("d-cr-text");
    if (!box.value.trim()) return;
    if (await write("/api/tickets/" + current.id + "/change-request", { text: box.value }, "Change request filed")) box.value = "";
  });
}

function wireNew() {
  const d = $("new-dlg"), f = $("new-form");
  $("new-btn").addEventListener("click", () => { f.reset(); d.returnValue = ""; d.showModal(); });
  d.addEventListener("close", async () => {
    if (d.returnValue !== "ok") return;
    const v = f.elements;
    try {
      const r = await api("POST", "/api/tickets", { title: v.title.value, body: v.body.value, project: v.project.value, priority: v.priority.value, queue: v.queue.value, shared: v.shared.checked });
      message(r.duplicate ? "Already tracked: your text was added to " + r.ticket : r.ticket + " created", true);
      etag = null;
      await refresh(true);
      location.hash = r.ticket;
    } catch (e) { message(e.message); }
  });
}

function wireFilters() {
  for (const id of ["f-project", "f-text", "f-mine"]) $(id).addEventListener("input", () => { store("project", $("f-project").value); store("mine", $("f-mine").checked ? "1" : ""); render(); });
  $("f-mine").checked = store("mine") === "1";
}

function route() {
  const m = /^#(T-\d{1,6})$/.exec(location.hash);
  if (m) openTicket(m[1]); else if (!$("panel").hidden) closePanel();
}

async function start() {
  me = await api("GET", "/api/session");
  $("who").textContent = "Signed in as " + me.actor;
  const lo = $("logout");
  lo.hidden = me.auth !== "cookie";
  lo.addEventListener("submit", async (e) => {
    e.preventDefault();
    try { await api("POST", "/logout"); } catch (err) { /* signed out either way */ }
    location.href = BASE + "/login";
  });
  wireFilters();
  wireDetail();
  wireNew();
  await refresh(true);
  $("who").textContent = "Signed in as " + labelOf(me.actor);
  route();
  window.addEventListener("hashchange", route);
  setInterval(() => { if (!document.hidden) refresh(); }, 10000);
  window.addEventListener("focus", () => refresh());
  document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
}

start().catch((e) => message(e.message));
