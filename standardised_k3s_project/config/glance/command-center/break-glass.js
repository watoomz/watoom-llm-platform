(() => {
  "use strict";
  // Everything shown comes from the host recovery service: it is only ever written with textContent.
  const $ = (id) => document.getElementById(id);
  const h = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  const say = (text, kind) => { const m = $("msg"); m.textContent = text; m.className = kind || ""; };
  let busy = false, last = "";

  function renderLast(run) {
    if (!run) { $("last").replaceChildren(h("div", "cr-empty", "No recovery run has happened yet.")); return; }
    const cls = run.verdict === "healthy" ? "bg-ok" : run.verdict === "live_work_remaining" ? "bg-warn" : "bg-bad";
    const head = h("div", "", "");
    head.append(h("b", cls, run.verdict.replace(/_/g, " ")), h("span", "hint", " · " + run.mode + " · " + new Date(run.finished * 1000).toLocaleString() + " · evidence " + run.evidence));
    const rows = (run.steps || []).map((s) => {
      const row = h("div", "bg-step");
      row.append(h("span", s.ok ? "bg-ok" : "bg-bad", s.ok ? "✓" : "✗"), h("span", "", s.step), h("span", "", String(s.detail)), h("span", "hint", s.seconds + " s"));
      return row;
    });
    const out = [head, ...rows];
    if (run.remaining && run.remaining.length) {
      const ul = h("ul", "bg-list");
      run.remaining.forEach((p) => ul.append(h("li", "", p)));
      out.push(h("div", "hint", "Still reported after the run:"), ul);
    }
    $("last").replaceChildren(...out);
  }

  function render(d) {
    if (!d || !d.present) {
      $("stamp").textContent = "no data";
      $("problems").replaceChildren(h("div", "cr-empty", "The break-glass service has not published a status yet (it refreshes every minute). Is watoom-break-glass.timer installed?"));
      return;
    }
    const sig = JSON.stringify([d.diagnosis, d.last_run, d.running, d.queued, d.approval_enabled]);
    $("stamp").textContent = "updated " + d.age_s + " s ago" + (d.age_s > 300 ? " (service may be stopped)" : "");
    const running = Boolean(d.running) || d.queued > 0;
    $("stale").disabled = running || !d.approval_enabled;
    $("force").disabled = running || !d.approval_enabled || $("confirm").value !== "RESET";
    if (!d.approval_enabled) say("Disabled: no operator PIN is configured for Glance.", "err");
    else if (running) say(d.running ? "A " + d.running + " run is in progress…" : "Request queued…", "ok");
    if (sig === last) return;
    last = sig;
    const dg = d.diagnosis || {};
    $("verdict").textContent = dg.healthy ? "healthy" : (dg.problems || []).length + " issue(s)";
    $("verdict").className = "hint " + (dg.healthy ? "bg-ok" : "bg-bad");
    const liveN = (dg.live_claims || []).length;
    if (dg.healthy) $("problems").replaceChildren(h("div", "bg-ok", "Nothing stuck: no orphaned claims, holds, stale workers or GPU ownership problems, and inference is ready." + (liveN ? " " + liveN + " job(s) running normally." : "")));
    else {
      const ul = h("ul", "bg-list");
      (dg.problems || []).forEach((p) => ul.append(h("li", "", p)));
      $("problems").replaceChildren(ul);
    }
    renderLast(d.last_run);
  }

  async function request(mode) {
    const pin = $("pin").value;
    if (pin.length < 8) { say("Enter the operator PIN first.", "err"); $("pin").focus(); return; }
    const text = mode === "force"
      ? "FORCE RESET\n\nThis stops the app and all workers and interrupts running work. History is kept and a database snapshot is taken first.\n\nContinue?"
      : "Clear stale claims, workers and GPU ownership? Running work is not touched.";
    if (!confirm(text)) return;
    busy = true; $("stale").disabled = $("force").disabled = true;
    try {
      const res = await fetch("/cc/break-glass", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode, pin, confirm: mode === "force" ? $("confirm").value : undefined }) });
      const j = await res.json().catch(() => ({}));
      say(j.message || j.error || "HTTP " + res.status, res.status === 202 ? "ok" : "err");
      if (res.status === 202) { $("pin").value = ""; $("confirm").value = ""; }
    } catch (e) { say("Could not reach the helper: " + e.message, "err"); }
    busy = false; load();
  }

  async function load() {
    if (busy) return;
    try { const r = await fetch("/cc/break-glass", { cache: "no-store" }); render(await r.json()); }
    catch (e) { $("stamp").textContent = "status error"; }
  }
  $("stale").addEventListener("click", () => request("stale"));
  $("force").addEventListener("click", () => request("force"));
  $("confirm").addEventListener("input", () => { $("force").disabled = $("confirm").value !== "RESET" || $("stale").disabled; });
  load(); setInterval(load, 4000);
})();
