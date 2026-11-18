(() => {
  "use strict";
  // Everything from a request (id, reason, file, diff) is model-written: it is only ever shown with textContent.
  const $ = (id) => document.getElementById(id);
  const h = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  const say = (text, kind) => { const m = $("msg"); m.textContent = text; m.className = kind || ""; };
  let busy = false, last = "";

  function diffBlock(text) {
    const pre = h("pre", "cr-diff");
    for (const line of String(text || "").split("\n")) {
      if (line === "" ) continue;
      const kind = line.startsWith("+++") || line.startsWith("---") ? "hunk" : line.startsWith("@@") ? "hunk" : line[0] === "+" ? "add" : line[0] === "-" ? "del" : "";
      pre.append(h("span", kind, line));
    }
    return pre;
  }

  async function decide(r, action, buttons) {
    const pin = $("pin").value;
    if (pin.length < 8) { say("Enter the operator PIN first.", "err"); $("pin").focus(); return; }
    const verb = action === "approve" ? "APPROVE and apply" : "REJECT";
    if (!confirm(verb + " " + r.id + "?\n\nFile: " + r.file + "\nRequest hash: " + r.request_sha256.slice(0, 12) + "\n\nThis is the exact diff shown on this page.")) return;
    busy = true; buttons.forEach((b) => (b.disabled = true));
    try {
      const res = await fetch("/cc/change-requests/decision", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, id: r.id, project: r.project, request_sha256: r.request_sha256, pin }) });
      const j = await res.json().catch(() => ({}));
      say(j.message || j.error || "HTTP " + res.status, res.status === 202 ? "ok" : "err");
      if (res.status === 202) $("pin").value = "";
    } catch (e) { say("Could not reach the helper: " + e.message, "err"); }
    busy = false; buttons.forEach((b) => (b.disabled = false)); load();
  }

  function card(r) {
    const c = h("div", "cr-card");
    const top = h("div", "cr-top");
    top.append(h("span", "id", r.id), h("span", "meta", "project " + r.project), h("span", "meta", r.file), h("span", "meta", "hash " + String(r.request_sha256 || "").slice(0, 12)));
    c.append(top, h("div", "cr-reason", "Reason: " + r.reason), diffBlock(r.diff));
    const act = h("div", "cr-actions");
    const ok = h("button", "approve", "Approve and apply"), no = h("button", "reject", "Reject");
    ok.type = no.type = "button";
    ok.addEventListener("click", () => decide(r, "approve", [ok, no]));
    no.addEventListener("click", () => decide(r, "reject", [ok, no]));
    act.append(ok, no); c.append(act);
    return c;
  }

  function render(d) {
    if (!d || !d.present) { $("stamp").textContent = "no data"; $("pending").replaceChildren(h("div", "cr-empty", "The change-request scanner has not published a feed yet (it runs every minute or so).")); return; }
    const sig = JSON.stringify([d.requests, d.errors, d.approval_enabled]);
    $("stamp").textContent = "updated " + d.age_s + " s ago" + (d.age_s > 300 ? " (scanner may be stopped)" : "");
    if (!d.approval_enabled) say("Approving here is disabled: no operator PIN is configured. Use the host command instead.", "err");
    if (sig === last) return;
    last = sig;
    const pend = d.requests.filter((r) => r.status === "PENDING_APPROVAL");
    $("pending-count").textContent = pend.length ? pend.length + " pending" : "";
    $("pending").replaceChildren(...(pend.length ? pend.map(card) : [h("div", "cr-empty", "Nothing is waiting.")]));
    const rest = d.requests.filter((r) => r.status !== "PENDING_APPROVAL");
    $("history").replaceChildren(...(rest.length ? rest.map((r) => {
      const row = h("div", "cr-row");
      row.append(h("span", "", new Date(r.time * 1000).toLocaleString()), h("span", r.status, r.status), h("span", "", r.project + " / " + r.id),
        h("span", "", r.commit ? "commit " + r.commit.slice(0, 10) + (r.pushed ? " (pushed)" : " (not pushed)") : (r.detail || r.file || "")));
      return row;
    }) : [h("div", "cr-empty", "No decisions yet.")]));
    for (const e of (d.errors || []).filter((x) => Date.now() / 1000 - x.time < 180)) say("Last decision failed for " + e.id + ": " + e.error, "err");
  }

  async function load() {
    if (busy) return;
    try { const r = await fetch("/cc/change-requests", { cache: "no-store" }); render(await r.json()); }
    catch (e) { $("stamp").textContent = "feed error"; }
  }
  load(); setInterval(load, 5000);
})();
