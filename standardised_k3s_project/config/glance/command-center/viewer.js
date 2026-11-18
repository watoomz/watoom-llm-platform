/* WatooM 3D viewer: shows one GLB produced by a worker job (served by helper-api from the worker snapshot). Orbit with the mouse, zoom with the wheel,
 * pan with right-drag. The model path comes from ?m=<job>/<file>.glb and is validated before use; every string shown is set with textContent. */
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const params = new URLSearchParams(location.search);
  const m = params.get("m") || "";
  const name = (params.get("n") || m.split("/").pop() || "model").slice(0, 120);
  const msg = $("vw-msg");
  const fail = (text) => { msg.textContent = text; msg.className = "vw-msg err"; msg.hidden = false; };
  $("vw-title").textContent = name;
  document.title = name + " · WatooM 3D viewer";
  if (!/^[A-Za-z0-9._-]{1,64}\/[A-Za-z0-9._-]{1,64}\.glb$/.test(m)) { fail("This link does not point to a model produced by a worker job."); return; }
  const url = "/cc/workers/media/" + m;
  const mv = $("mv");
  $("vw-dl").href = url;
  $("vw-dl").setAttribute("download", name);
  let done = false;
  mv.addEventListener("progress", (e) => { if (!done) $("vw-prog").style.width = Math.round((e.detail.totalProgress || 0) * 100) + "%"; });
  mv.addEventListener("error", () => fail("The model could not be displayed (the file may be damaged or use compression the viewer does not support). You can still download it."));
  mv.addEventListener("load", () => {
    done = true;
    msg.hidden = true;
    $("vw-prog").hidden = true;
    const d = mv.getDimensions();
    $("vw-meta").textContent = [d.x, d.y, d.z].map((v) => v.toFixed(2)).join(" × ") + " m (width × height × depth)";
    const anims = mv.availableAnimations || [];
    if (anims.length) {
      const sel = $("vw-anim");
      sel.replaceChildren(...anims.map((a) => { const o = document.createElement("option"); o.value = a; o.textContent = a; return o; }));
      $("vw-anim-wrap").hidden = false;
      mv.animationName = anims[0];
      mv.play();
      sel.addEventListener("change", () => { mv.animationName = sel.value; mv.play(); });
    }
  });
  $("vw-rot").addEventListener("change", (e) => { if (e.target.checked) mv.setAttribute("auto-rotate", ""); else mv.removeAttribute("auto-rotate"); });
  $("vw-light").addEventListener("change", (e) => document.body.classList.toggle("light", e.target.checked));
  $("vw-reset").addEventListener("click", () => { mv.cameraOrbit = "auto auto auto"; mv.cameraTarget = "auto auto auto"; mv.fieldOfView = "auto"; mv.jumpCameraToGoal(); });
  mv.src = url;
})();
