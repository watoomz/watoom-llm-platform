"use strict";
// Shared by every guide page; each feature checks its elements exist before wiring up.
const $=(s,r=document)=>r.querySelector(s), $$=(s,r=document)=>[...r.querySelectorAll(s)];

// Links into the retired single-page guide (/guide/#anchor) forward to the page that now covers them.
const LEGACY={
  "document-purpose-and-operating-model":"/guide/","current-platform-snapshot":"/guide/#system-at-a-glance",
  "architecture-overview":"/guide/#architecture","physical-and-logical-network-architecture":"/guide/network.html",
  "edge-routing-firewall-and-nat-policy":"/guide/network.html#public-exposure","operational-tooling-and-important-scripts":"/guide/operations.html",
  "k3s-platform-architecture":"/guide/platform.html","docker-compose-workloads":"/guide/platform.html#docker-compose",
  "application-and-service-catalogue":"/guide/services.html","media-automation-and-streaming-flows":"/guide/media.html",
  "game-server-exposure":"/guide/games.html","llm-build-and-test-notes":"/guide/ai.html","llm-model-lab":"/guide/ai.html",
  "model-manager":"/guide/ai.html#model-manager","llama-mesh-production-workflow":"/guide/ai.html#llama-mesh",
  "monitoring-dashboards-and-observability":"/guide/monitoring.html","security-baseline-and-hardening-review":"/guide/security.html",
  "opencode-kali-security":"/guide/security.html#agent-isolation","kali-integration-evidence":"/guide/security.html#agent-isolation",
  "secrets-management":"/guide/security.html#secrets","reboot-and-recovery-procedure":"/guide/recovery.html",
  "protected-production-baseline":"/guide/recovery.html#restoring-watoom-code-state","routine-operations-runbook":"/guide/operations.html",
  "detailed-troubleshooting-guide":"/guide/troubleshooting.html","validation-and-change-control":"/guide/operations.html#validation-tiers",
  "documentation-maintenance":"/guide/operations.html#documentation","legacy-and-retired-components":"/guide/operations.html#retired-do-not-restore",
  "host-tuning-and-capacity":"/guide/platform.html#host-tuning","ai-directory-layout":"/guide/platform.html#persistent-storage",
  "opencode-production":"/guide/watoom-code.html","unreal-dungeon-pipelines":"/guide/watoom-code.html#toolkit-and-engines",
  "blender-production-status":"/guide/watoom-code.html#toolkit-and-engines","pipeline-prompt-templates":"/guide/pipeline-prompts.html"
};
(()=>{const id=decodeURIComponent(location.hash.slice(1));
  if(/\/guide\/(index\.html)?$/.test(location.pathname)&&id&&LEGACY[id]&&!document.getElementById(id))location.replace(LEGACY[id]);})();

// Mobile menu
const sidebar=$(".sidebar"), toggle=$(".menu-toggle");
if(sidebar&&toggle)toggle.addEventListener("click",()=>{const open=sidebar.classList.toggle("open");toggle.setAttribute("aria-expanded",String(open));});

// Copy buttons on code blocks
$$(".copy-btn").forEach(btn=>btn.addEventListener("click",async()=>{
  const text=btn.nextElementSibling?btn.nextElementSibling.innerText:"";
  try{await navigator.clipboard.writeText(text);btn.textContent="Copied";}catch{btn.textContent="Select";}
  setTimeout(()=>btn.textContent="Copy",1400);}));

// Search across all guide pages (index built by the renderer)
const search=$("#site-search"), results=$("#search-results");
if(search&&results){
  let index=null;
  const load=()=>index||(index=fetch("/guide/assets/search-index.json",{cache:"no-cache"}).then(r=>r.ok?r.json():[]).catch(()=>[]));
  const esc=s=>s.replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
  async function run(){
    const words=search.value.toLowerCase().trim().split(/\s+/).filter(w=>w.length>1);
    if(!words.length){results.hidden=true;results.innerHTML="";return;}
    const data=await load();
    const scored=data.map(e=>{const title=e.title.toLowerCase(),hay=(e.page+" "+e.title+" "+e.text).toLowerCase();
      if(!words.every(w=>hay.includes(w)))return null;
      return [words.reduce((n,w)=>n+(title.includes(w)?3:1),0),e];}).filter(Boolean).sort((a,b)=>b[0]-a[0]).slice(0,12);
    results.innerHTML=scored.length?scored.map(([,e])=>{
      const t=e.text, at=Math.max(0,t.toLowerCase().indexOf(words[0])-60), snip=(at?"…":"")+t.slice(at,at+150)+(t.length>at+150?"…":"");
      return `<a href="${esc(e.url)}"><small>${esc(e.page)}</small><b>${esc(e.title)}</b><span>${esc(snip)}</span></a>`;}).join("")
      :'<div class="empty">No matches.</div>';
    results.hidden=false;}
  search.addEventListener("input",run);
  search.addEventListener("focus",load,{once:true});
  document.addEventListener("keydown",e=>{
    if(e.key==="/"&&document.activeElement!==search&&!/input|textarea|select/i.test(document.activeElement.tagName)){e.preventDefault();sidebar&&sidebar.classList.add("open");search.focus();}
    if(e.key==="Escape"&&document.activeElement===search){search.value="";run();search.blur();}});
}

// Highlight the current section in the page table of contents
const toc=$$(".toc-link");
if(toc.length&&"IntersectionObserver" in window){
  const obs=new IntersectionObserver(es=>es.forEach(e=>{if(e.isIntersecting)toc.forEach(a=>a.classList.toggle("active",a.getAttribute("href")==="#"+e.target.id));}),{rootMargin:"-10% 0px -80% 0px"});
  $$(".content h2[id]").forEach(h=>obs.observe(h));
}

// Request flow diagram (overview page)
const svg=$("#flow-svg"), explain=$("#flow-explain");
if(svg){
  const flows={
    local:{nodes:[["Client","LAN / VPN"],["Pi-hole","10.99.20.225:53"],["Traefik",":443 wildcard TLS"],["Service","10.243.0.0/16"],["Pod","10.242.0.0/24"]],
      explain:"A client resolves <name>.internal.homelab.example through Pi-hole, connects to Traefik, which matches the IngressRoute and proxies to the Service and pod."},
    media:{nodes:[["Seerr","request"],["Radarr / Sonarr","automation"],["Prowlarr","indexers"],["SAB / qBit","download"],["/data","library"],["Jellyfin","playback"]],
      explain:"A request in Seerr drives the Arr apps, which search through Prowlarr, hand the grab to a downloader and import the result into the /data library that Jellyfin serves."},
    stream:{nodes:[["Dispatcharr","M3U :9191"],["stream-app","FFmpeg → HLS"],["stream-nginx",":8888"],["cloudflared","tunnel"],["Cloudflare","stream.homelab.example"]],
      explain:"stream-app reads the Dispatcharr M3U, transcodes to HLS, nginx serves the segments and the outbound tunnel publishes them behind Cloudflare Access."},
    llm:{nodes:[["WatooM Code","agents"],["llm-router",":8000/v1"],["GPU controller","sole writer"],["llama.cpp","Swift Qwen3.8"],["GPU","20 GiB"]],
      explain:"Agents call the OpenAI-compatible router. The router asks the exclusive GPU controller for admission; the controller owns every model switch and restores the primary afterwards."},
    public:{nodes:[["Internet","browser"],["Cloudflare","Access"],["cloudflared","outbound QUIC"],["Origin","nginx / AzuraCast"]],
      explain:"Public web origins are reached only through outbound Cloudflare Tunnel connectors. No inbound web port is open on the router."}
  };
  let timers=[];
  const reduce=matchMedia("(prefers-reduced-motion: reduce)").matches;
  function render(key){
    timers.forEach(clearInterval);timers=[];
    const f=flows[key],n=f.nodes.length,w=n>5?138:150,gap=(1000-60-n*w)/(n-1),y=90,h=104,centres=[];
    let out="";
    f.nodes.forEach(([title,sub],i)=>{const x=30+i*(w+gap);centres.push(x);
      out+=`<rect class="node" x="${x}" y="${y}" width="${w}" height="${h}" rx="10"/><text class="node-title" x="${x+w/2}" y="${y+44}" text-anchor="middle">${title}</text><text class="node-sub" x="${x+w/2}" y="${y+70}" text-anchor="middle">${sub}</text>`;});
    for(let i=0;i<n-1;i++){const x1=centres[i]+w+4,x2=centres[i+1]-4;out+=`<line class="edge" x1="${x1}" y1="${y+h/2}" x2="${x2}" y2="${y+h/2}"/><circle class="pulse" data-x1="${x1}" data-x2="${x2}" cx="${x1}" cy="${y+h/2}" r="4"/>`;}
    svg.innerHTML=out;if(explain)explain.textContent=f.explain;
    if(!reduce)$$(".pulse",svg).forEach((p,i)=>{let t=i*.2;const a=+p.dataset.x1,b=+p.dataset.x2;timers.push(setInterval(()=>{t=(t+.02)%1;p.setAttribute("cx",a+(b-a)*t);},30));});
  }
  $$(".flow-tab").forEach(b=>b.addEventListener("click",()=>{$$(".flow-tab").forEach(x=>x.classList.toggle("active",x===b));render(b.dataset.flow);}));
  render("local");
}

// Live status (overview page), from the Glance helper
if($("#live-apps")){
  const set=(id,v)=>{const el=document.getElementById(id);if(el)el.textContent=v;};
  async function live(){
    const box=$("#live-problems");
    try{
      const r=await fetch("/guide-api/status",{cache:"no-store"});if(!r.ok)throw new Error(r.status);
      const d=await r.json();
      set("live-apps",`${d.apps.ok}/${d.apps.total}`);set("live-apps-sub",d.apps.errors?`${d.apps.errors} need attention`:"all healthy");
      set("live-pods",String(d.cluster.pods_running));set("live-pods-sub",`${d.cluster.pods_pending} pending · ${d.cluster.pods_failed} failed`);
      set("live-mem",`${d.cluster.memory_used_pct}%`);set("live-disk",`${d.cluster.disk_used_pct}%`);
      const rows=d.problem_namespaces||[];
      box.innerHTML=rows.length?rows.map(x=>`<div class="live-problem"><b>${x.namespace}</b> · ${x.failed||0} failed · ${x.pending||0} pending · ${x.unavailable||0} unavailable</div>`).join("")
        :'<div class="live-ok">● no namespace needs attention</div>';
    }catch{if(box)box.innerHTML='<div class="small-note">Live status unavailable. The documentation below is unaffected.</div>';}
  }
  live();setInterval(live,60000);
}
