"use strict";
const BASE=location.pathname.replace(/\/$/,"");let csrf="",current=null,removal=null,managed=[],system={available:false,models:[]},filter="all";
const $=id=>document.getElementById(id);
// Polling must not reset the page: redraw only when the data changed, and keep open Details panels.
const openDetails=new Set();let modelSignature="",jobSignature="";
function el(tag,attrs,...children){const node=document.createElement(tag);for(const[k,v]of Object.entries(attrs||{})){if(v===null||v===undefined||v===false)continue;if(k==="class")node.className=v;else if(k==="text")node.textContent=v;else if(k.startsWith("on"))node[k]=v;else node.setAttribute(k,v===true?"":v)}for(const c of children.flat()){if(c===null||c===undefined||c===false)continue;node.append(c instanceof Node?c:document.createTextNode(String(c)))}return node}
async function api(path,value){const response=await fetch(BASE+path,{method:value?"POST":"GET",headers:value?{"Content-Type":"application/json","X-CSRF-Token":csrf}:{},body:value?JSON.stringify(value):undefined});const result=await response.json().catch(()=>({error:"HTTP "+response.status}));if(!response.ok)throw Error(result.error||response.status);return result}
let toastTimer=null;
function message(text,tone){const box=$("message");box.textContent=text;box.className="toast"+(tone?" "+tone:"");box.hidden=!text;clearTimeout(toastTimer);if(text&&tone!=="err")toastTimer=setTimeout(()=>{box.hidden=true},8000)}
const fail=e=>message(e.message||String(e),"err");

/* ---------- formatting ---------- */
const GB=n=>n===null||n===undefined?"—":(n/1e9).toFixed(n>=1e10?1:2)+" GB";
const KIND={"gguf":"Language · GGUF","gguf-lora":"LoRA adapter · GGUF","lora":"SDXL LoRA","diffusion-pipeline":"SDXL pipeline","diffusion-checkpoint":"SDXL checkpoint","unsupported":"Unsupported"};
const IMAGE_KINDS=["lora","diffusion-pipeline","diffusion-checkpoint"];
const base=p=>p?String(p).split("/").pop():"—";
function duration(s){if(!isFinite(s)||s<0)return"";if(s<90)return Math.round(s)+" s";if(s<5400)return Math.round(s/60)+" min";return(s/3600).toFixed(1)+" h"}
function ctx(n){n=Number(n);return n?(n>=1024?Math.round(n/1024)+"K":n)+" tokens":"—"}

/* ---------- GPU header ---------- */
function renderGpu(){
  const box=$("gpu");box.replaceChildren();
  if(!system.available){box.append(el("span",{class:"dot"}),"GPU status unavailable"+(system.reason?" ("+system.reason+")":""));return}
  const c=system.controller||{};const loaded=items().find(i=>i.row&&i.row.deployment===c.selected);
  const tone=c.uncertain?"bad":c.owner?"busy":"ok";
  box.append(el("span",{class:"dot "+tone}),el("span",{text:c.uncertain?"Controller uncertain":c.owner?"GPU busy ("+c.owner+")":"GPU ready"}),el("span",{text:"·"}),el("span",{text:loaded?"Loaded: "+loaded.name:"No chat model loaded"}));
}

/* ---------- models ---------- */
function items(){
  const byId=new Map(managed.map(r=>[r.id,r]));const used=new Set();const out=[];
  for(const row of system.models){
    const record=row.model_id?byId.get(row.model_id):null;if(record)used.add(record.id);
    // Until the router carries real names, a managed model's router name is just its id: show the repository instead.
    const name=row.name&&row.name!==row.id?row.name:record?record.repository:row.name;
    out.push({key:row.deployment,name,alias:row.id,record,row,kind:record?record.kind:"gguf",managed:!!record||row.managed});
  }
  for(const record of managed)if(!used.has(record.id))out.push({key:record.id,name:record.repository,alias:record.alias||null,record,row:null,kind:record.kind,managed:true});
  return out;
}
function settingsOf(item){
  const s=item.row&&item.row.settings;if(s)return s;
  const r=(item.record&&item.record.settings)||{};
  return{context:r.context,cache_k:r.cache_k,cache_v:r.cache_v,reasoning:r.reasoning,speculation:r.speculation,draft_count:r.draft_count,temperature:r.temperature,top_p:r.top_p,top_k:r.top_k,min_p:r.min_p};
}
function card(item){
  const row=item.row||{},record=item.record,s=settingsOf(item);
  const isImage=IMAGE_KINDS.includes(item.kind);
  const badges=el("div",{class:"badges"},
    row.loaded?el("span",{class:"badge ok",text:"Loaded"}):row.exists?el("span",{class:"badge",text:"Stopped"}):null,
    row.primary?el("span",{class:"badge accent",text:"Primary"}):null,
    row.mesh?el("span",{class:"badge info",text:"3D mesh"}):null,
    el("span",{class:"badge",text:KIND[item.kind]||item.kind}),
    item.managed?el("span",{class:"badge accent",text:"Managed here"}):el("span",{class:"badge",text:"System (read-only)"}),
    s.speculation==="draft-mtp"?el("span",{class:"badge info",text:"MTP ×"+(s.draft_count||"?")}):null,
    s.lora||item.kind==="gguf-lora"?el("span",{class:"badge info",text:"LoRA"}):null,
    s.mmproj?el("span",{class:"badge info",text:"Vision"}):null,
    record&&record.registration_error?el("span",{class:"badge bad",text:"Not registered"}):null);
  const facts=el("dl",{class:"facts"});
  const add=(k,v)=>{if(v!==null&&v!==undefined&&v!=="")facts.append(el("dt",{text:k}),el("dd",{text:v}))};
  const file=row.file||null;
  add("File",file?base(file.path):record&&record.repository?"":null);
  add("Size",file&&file.bytes?GB(file.bytes)+(row.lora_file&&row.lora_file.bytes?" + "+GB(row.lora_file.bytes)+" adapter":""):null);
  if(!isImage){
    add("Context",s.context?ctx(s.context):null);
    add("KV cache",s.cache_k?(s.cache_k===s.cache_v?s.cache_k:s.cache_k+" / "+s.cache_v):null);
    add("Thinking",s.reasoning||null);
    const sampling=[s.temperature!=null&&s.temperature!==undefined?"temp "+s.temperature:null,s.top_p!=null?"top-p "+s.top_p:null,s.top_k!=null?"top-k "+s.top_k:null,s.min_p!=null?"min-p "+s.min_p:null].filter(Boolean).join(" · ");
    add("Sampling",sampling||null);
  }
  const more=el("dl",{class:"facts"});const addMore=(k,v)=>{if(v)more.append(el("dt",{text:k}),el("dd",{text:v}))};
  addMore("Router id",item.alias);addMore("Deployment",row.deployment);addMore("Model path",file&&file.path);
  addMore("LoRA",row.lora_file&&row.lora_file.path);addMore("Projector",row.mmproj_file&&row.mmproj_file.path);
  addMore("Repository",record&&record.repository);addMore("Revision",record&&record.revision&&record.revision.slice(0,12));
  addMore("Image",row.image&&row.image.split("@")[0]);addMore("Error",record&&record.registration_error);
  const steps=record?el("div",{class:"steps"},...[["downloaded","Downloaded"],["configured","Configured"],["registered","Registered"],["tested","Tested"]].map(([k,t])=>el("span",{class:"step"+(record[k]?" done":""),text:(record[k]?"✓ ":"")+t}))):null;
  const panel=el("details",{open:openDetails.has(item.key)},el("summary",{text:"Details"}),more);
  panel.addEventListener("toggle",()=>{panel.open?openDetails.add(item.key):openDetails.delete(item.key)});
  const actions=el("div",{class:"card-foot"},panel,
    record?el("button",{class:"small",text:"Remove…",onclick:()=>planRemoval(record,item.name)}):null);
  return el("article",{class:"card"+(row.loaded?" loaded":"")},
    el("div",{class:"card-head"},el("div",{},el("h3",{text:item.name||item.alias}),item.alias&&item.alias!==item.name?el("div",{class:"id mono",text:item.alias}):null)),
    badges,record&&record.description?el("p",{class:"desc",text:record.description,title:record.description}):null,facts.childElementCount?facts:null,steps,actions);
}
function renderModels(force){
  const signature=JSON.stringify([managed,system,filter,$("search").value]);
  if(!force&&signature===modelSignature)return;modelSignature=signature;
  const grid=$("modelGrid");const q=$("search").value.trim().toLowerCase();
  let list=items().filter(i=>{
    if(filter==="language"&&IMAGE_KINDS.includes(i.kind))return false;
    if(filter==="image"&&!IMAGE_KINDS.includes(i.kind))return false;
    if(filter==="loaded"&&!(i.row&&i.row.loaded))return false;
    if(filter==="managed"&&!i.managed)return false;
    if(!q)return true;
    return[i.name,i.alias,i.row&&i.row.deployment,i.row&&i.row.file&&i.row.file.path,i.record&&i.record.repository].some(v=>v&&String(v).toLowerCase().includes(q));
  });
  list.sort((a,b)=>(b.row&&b.row.loaded?1:0)-(a.row&&a.row.loaded?1:0)||(b.row&&b.row.primary?1:0)-(a.row&&a.row.primary?1:0)||String(a.name).localeCompare(String(b.name)));
  grid.replaceChildren(...(list.length?list.map(card):[el("p",{class:"empty",text:"No models match."})]));
  const note=$("systemNote");note.hidden=system.available;note.textContent=system.available?"":"Only models installed here are shown: "+(system.reason||"the GPU inventory is unavailable")+".";
  // Base choices for adapters: installed SDXL pipelines for SDXL LoRAs/checkpoints, installed GGUFs for GGUF LoRAs.
  if(current)fillBases();
}
for(const chip of document.querySelectorAll(".chip"))chip.onclick=()=>{filter=chip.dataset.filter;for(const c of document.querySelectorAll(".chip"))c.classList.toggle("on",c===chip);renderModels()};
$("search").oninput=renderModels;

/* ---------- add a model ---------- */
const GROUPS=[
  ["Context and memory",["context","output_tokens","cache_k","cache_v","flash_attention","gpu_layers","cpu_ffn"]],
  ["Sampling",["temperature","top_p","top_k","min_p","presence_penalty","repeat_penalty","repeat_last_n"]],
  ["Thinking and speculation",["reasoning","speculation","draft_count"]],
  ["Throughput",["parallel","batch","ubatch","continuous_batching","threads","jinja"]],
  ["Vision",["projector","projector_gpu"]],
  ["Image",["base_model","width","height","steps","guidance","scheduler","precision","seed","strength"]],
];
const LABEL={context:"Context window",context_auto:"Raise context to fit the GPU (18 GB)",output_tokens:"Output tokens (app budget)",cache_k:"KV cache K",cache_v:"KV cache V",flash_attention:"Flash attention",gpu_layers:"GPU layers (-1 = all)",cpu_ffn:"CPU FFN layers",temperature:"Temperature",top_p:"Top-p",top_k:"Top-k",min_p:"Min-p",presence_penalty:"Presence penalty",repeat_penalty:"Repeat penalty",repeat_last_n:"Repeat window",reasoning:"Thinking",speculation:"Speculation",draft_count:"MTP draft tokens",parallel:"Parallel slots",batch:"Batch",ubatch:"Micro-batch",continuous_batching:"Continuous batching",threads:"CPU threads",jinja:"Jinja chat template",projector:"Vision projector",projector_gpu:"Projector on GPU",base_model:"Base model",width:"Width",height:"Height",steps:"Steps",guidance:"Guidance",scheduler:"Scheduler",precision:"Precision",seed:"Seed",strength:"Strength"};
const HELP={speculation:"draft-mtp needs an MTP head; the downloaded file's header must prove it",draft_count:"1-32 when MTP is on",reasoning:"on = the model thinks before answering",output_tokens:"WatooM Code's answer budget; the server itself has no cap"};
function field(key,value,profile){
  const choices=profile.options&&profile.options[key];const type=typeof value;
  let input;
  if(type==="boolean"||(choices&&type!=="number")){
    // null is "none" (e.g. no vision projector): an empty value, read back as null.
    const show=item=>item===null?"":String(item);
    input=el("select",{});for(const item of(choices||[true,false]))input.append(el("option",{value:show(item),text:item===null?"none":String(item)}));
    if(choices&&!choices.map(show).includes(show(value)))input.append(el("option",{value:show(value),text:String(value)+" (custom)"}));
  }else if(type==="number"){
    const list="dl-"+key;input=el("input",{type:"number",step:"any",list});
    if(choices){const dl=el("datalist",{id:list});for(const item of choices)dl.append(el("option",{value:String(item)}));input._list=dl}
  }else input=el("input",{type:"text",placeholder:"none"});
  input.dataset.key=key;input.dataset.type=value===null||(choices&&choices.includes(null))?"nullable":type;input.value=value===null?"":String(value);
  const source=profile.sources[key]||{type:"Safe baseline"};const tone=source.type.startsWith("Published")?"published":source.type.startsWith("Your")?"override":"";
  const src=el("span",{class:"src "+tone,text:source.type.replace("Safe baseline","Safe").replace("Published recommendation","Published").replace("Your override","Override"),title:source.evidence||source.excerpt||source.type});
  return el("label",{class:"field"},LABEL[key]||key,input,input._list||null,src,HELP[key]?el("span",{class:"help",text:HELP[key]}):null);
}
function settings(profile){
  const root=$("settings");root.replaceChildren();const keys=Object.keys(profile.values);const placed=new Set();
  for(const[title,group]of GROUPS){
    const present=group.filter(k=>keys.includes(k));if(!present.length)continue;
    if(title==="Vision"&&profile.values.projector===null&&!(current&&current.metadata.files.some(f=>/mmproj/i.test(f.path))))continue;
    present.forEach(k=>placed.add(k));
    root.append(el("fieldset",{class:"group"},el("legend",{text:title}),el("div",{class:"fields"},...present.map(k=>field(k,profile.values[k],profile)))));
  }
  const rest=keys.filter(k=>!placed.has(k)&&!(k==="projector"||k==="projector_gpu"));
  if(rest.length)root.append(el("fieldset",{class:"group"},el("legend",{text:"Other"}),el("div",{class:"fields"},...rest.map(k=>field(k,profile.values[k],profile)))));
}
function values(){
  const result={};
  for(const input of $("settings").querySelectorAll("input[data-key],select[data-key]")){
    const t=input.dataset.type,v=input.value;
    result[input.dataset.key]=t==="number"?Number(v):t==="boolean"?v==="true":t==="nullable"?(v===""?null:v):v||null;
  }
  // Settings hidden because they do not apply (e.g. no projector file) keep their proposed value.
  for(const[k,v]of Object.entries(current.settings.values))if(!(k in result))result[k]=v;
  return result;
}
function selectedVariant(){return current&&current.metadata.variants.find(v=>v.id===(document.querySelector("input[name=variant]:checked")||{}).value)}
function renderVariants(){
  const box=$("variants");box.replaceChildren();const variants=current.metadata.variants;
  if(!variants.length){box.append(el("p",{class:"warn",text:"No supported files in this repository for Model Manager."}));$("install").disabled=true;return}
  variants.forEach((v,i)=>{
    const input=el("input",{type:"radio",name:"variant",value:v.id,checked:i===0});
    const label=el("label",{class:"variant"+(i===0?" on":"")},input,el("div",{},el("div",{class:"mono",text:v.id}),el("div",{class:"meta",text:[GB(v.bytes),v.precision,v.files.length>1?v.files.length+" files":null].filter(Boolean).join(" · ")}),v.mtp_published?el("span",{class:"badge info",text:"MTP"}):null));
    input.onchange=()=>{for(const n of box.querySelectorAll(".variant"))n.classList.toggle("on",n.contains(input));size()};
    box.append(label);
  });
  size();
}
function size(){
  const v=selectedVariant();$("files").replaceChildren(...(v?v.files.map(f=>el("li",{text:f.path+" — "+(f.size===null?"size unknown":f.size.toLocaleString("en-US")+" bytes ("+GB(f.size)+")")})):[]));
  $("install").disabled=!v||v.bytes===null;
}
function fillBases(){
  const kind=current.metadata.kind;const box=$("baseBox");const needs=["lora","diffusion-checkpoint","gguf-lora"].includes(kind);box.hidden=!needs;
  $("settingsTitle").textContent=(needs?"3":"2")+" · Settings";
  if(!needs)return;
  const want=kind==="gguf-lora"?"gguf":"diffusion-pipeline";const select=$("base");const keep=select.value;select.replaceChildren();
  const options=managed.filter(m=>m.kind===want);
  $("baseHelp").textContent=kind==="gguf-lora"?"The adapter is applied (llama-server --lora) on an installed GGUF base. It must be the same architecture; the card says: "+(current.metadata.base_model||"no base declared")+". Install the base GGUF first if it is not listed.":"Choose the installed SDXL pipeline this adapter was trained against ("+(current.metadata.base_model||"not declared")+").";
  if(!options.length)select.append(el("option",{value:"",text:"No installed "+(want==="gguf"?"GGUF model":"SDXL pipeline")+" yet"}));
  for(const m of options)select.append(el("option",{value:m.id,text:m.repository+" · "+(m.alias||m.revision.slice(0,10))}));
  if(keep)select.value=keep;
}
async function inspect(url){
  $("inspectButton").disabled=true;message("Reading the repository's metadata…");
  try{current=await api("/api/inspect",{url})}finally{$("inspectButton").disabled=false}
  const m=current.metadata;$("name").textContent=m.repository;
  $("repoBadges").replaceChildren(...[el("span",{class:"badge accent",text:KIND[m.kind]||m.kind}),m.license?el("span",{class:"badge",text:"Licence: "+m.license}):null,m.gated?el("span",{class:"badge warn",text:"Gated"}):null,m.base_model?el("span",{class:"badge",text:"Base: "+m.base_model}):null,el("span",{class:"badge mono",text:m.revision.slice(0,12)})].filter(Boolean));
  $("revision").replaceChildren();
  const refs=[{name:"Inspected commit "+m.revision.slice(0,12),ref:m.revision}];
  for(const group of["branches","tags"])for(const ref of m.refs[group]||[])refs.push({name:group.slice(0,-1)+": "+ref.name,ref:ref.ref||ref.name});
  for(const ref of refs)$("revision").append(el("option",{value:ref.ref.replace("refs/heads/","").replace("refs/tags/",""),text:ref.name}));
  $("preset").replaceChildren(el("option",{value:"",text:"Recommendations / saved overrides"}));
  current.settings.presets.forEach((p,i)=>$("preset").append(el("option",{value:i,text:p.name})));
  const u=$("uncertainty");u.hidden=!current.settings.uncertainty;u.textContent=current.settings.uncertainty||"";
  renderVariants();fillBases();settings(current.settings);$("details").hidden=false;
  message("Metadata read. Nothing has been downloaded.","ok");$("details").scrollIntoView({block:"start"});
}
$("inspect").onsubmit=e=>{e.preventDefault();inspect($("url").value).catch(fail)};
$("revision").onchange=()=>inspect("https://huggingface.co/"+current.metadata.repository+"/tree/"+encodeURIComponent($("revision").value)).catch(fail);
$("preset").onchange=()=>{
  if($("preset").value==="")return settings(current.settings);
  const p=current.settings.presets[Number($("preset").value)];const profile=structuredClone(current.settings);
  for(const[k,e]of Object.entries(p.fields)){profile.values[k]=e.value;profile.sources[k]={type:"Published recommendation",evidence:p.name+" · README line "+e.line}}
  settings(profile);message("Published mode applied. Save it to keep it as your override.");
};
$("save").onclick=async()=>{try{current.settings=await api("/api/overrides",{url:current.metadata.source,values:values()});settings(current.settings);message("Saved as your overrides for this revision.","ok")}catch(e){fail(e)}};
$("reset").onclick=async()=>{try{current.settings=await api("/api/overrides",{url:current.metadata.source,values:{}});settings(current.settings);message("Published recommendations restored.","ok")}catch(e){fail(e)}};
$("safe").onclick=async()=>{try{current.settings=await api("/api/overrides",{url:current.metadata.source,values:{},safe_only:true});settings(current.settings);message("Safe baseline restored.","ok")}catch(e){fail(e)}};
$("install").onclick=async()=>{
  const v=selectedVariant();if(!v)return;
  if(!$("baseBox").hidden&&!$("base").value){message("Choose an installed base model first.","err");return}
  $("install").disabled=true;
  try{const r=await api("/api/install",{url:current.metadata.source,revision:current.metadata.revision,variant:v.id,settings:values(),base_install:$("baseBox").hidden?null:$("base").value});message("Queued: "+v.id+". Follow it under Jobs.","ok");await refresh();location.hash="#jobs"}
  catch(e){fail(e)}finally{size()}
};

/* ---------- jobs ---------- */
const STATE={QUEUED:["Queued",""],DOWNLOADING:["Downloading","info"],WAITING_NATIVE_IDLE:["Waiting for idle GPU","warn"],REGISTERED_NOT_TESTED:["Installed","ok"],DOWNLOADED_REGISTRATION_FAILED:["Downloaded, not registered","bad"],FAILED:["Failed","bad"],CANCEL_REQUESTED:["Cancelling","warn"],CANCELLED:["Cancelled",""],REMOVING:["Removing","warn"],REMOVED_FILES_RETAINED:["Removed (files kept)","ok"],REMOVED_FILES_QUARANTINED:["Removed (files quarantined)","ok"],GENERATING:["Generating","info"],GENERATION_VERIFIED:["Generated","ok"]};
const ACTIVE=["QUEUED","DOWNLOADING","WAITING_NATIVE_IDLE","REMOVING","CANCEL_REQUESTED"];
function renderJobs(jobs){
  const all=$("showAllJobs").checked;
  const signature=JSON.stringify([jobs,all,managed.map(m=>m.id)]);if(signature===jobSignature)return;jobSignature=signature;const active=jobs.filter(j=>ACTIVE.includes(j.state));
  const count=$("jobCount");count.hidden=!active.length;count.textContent=active.length;
  const shown=(all?jobs:jobs.filter(j=>ACTIVE.includes(j.state)||["FAILED","DOWNLOADED_REGISTRATION_FAILED"].includes(j.state)&&Date.now()/1000-j.updated<86400)).slice(0,40);
  const list=$("jobList");
  if(!shown.length){list.replaceChildren(el("p",{class:"empty",text:all?"No jobs yet.":"Nothing running. Tick “Show finished jobs” for history."}));return}
  list.replaceChildren(...shown.map(j=>{
    let sel;try{sel=JSON.parse(j.selection)}catch{sel={}}
    const total=(sel.files||[]).reduce((a,f)=>a+(f.size||0),0);const[label,tone]=STATE[j.state]||[j.state,""];
    const title=sel.operation==="remove"?"Remove "+(managed.find(m=>m.id===sel.id)||{}).repository:(sel.repository||sel.operation||"Job")+(sel.files&&sel.files[0]?" · "+base(sel.files[0].path):"");
    const rate=j.average_bytes_per_second||0;const left=total&&rate?(total-j.progress)/rate:NaN;
    const detail=[total?GB(j.progress)+" of "+GB(total)+" ("+Math.floor(100*j.progress/total)+"%)":null,j.state==="DOWNLOADING"&&rate?(rate/1e6).toFixed(1)+" MB/s":null,j.state==="DOWNLOADING"&&isFinite(left)&&left>0?duration(left)+" left":null,j.state==="DOWNLOADING"&&total&&j.progress>=total?"verifying and registering…":null,new Date(1000*(j.updated||j.created)).toLocaleString()].filter(Boolean).join(" · ");
    const action=["QUEUED","DOWNLOADING"].includes(j.state)?"cancel":["FAILED","CANCELLED","DOWNLOADED_REGISTRATION_FAILED"].includes(j.state)?"retry":null;
    const button=action?el("button",{class:"small",text:action==="cancel"?"Cancel (keeps partial file)":"Retry",onclick:async()=>{try{await api("/api/"+action,{id:j.id});await refresh()}catch(e){fail(e)}}}):null;
    return el("div",{class:"job"},el("div",{},el("div",{class:"title",text:title}),el("div",{class:"detail",text:detail})),el("div",{class:"right"},el("span",{class:"badge "+tone,text:label}),button),
      j.state==="DOWNLOADING"&&total?el("progress",{max:total,value:Math.min(j.progress,total)}):null,j.error?el("div",{class:"err",text:j.error}):null);
  }));
}
$("showAllJobs").onchange=()=>refresh().catch(fail);

/* ---------- removal ---------- */
async function planRemoval(record,name){
  try{
    removal=await api("/api/remove-plan",{id:record.id,revision:record.revision});
    $("removeName").textContent=name||record.repository;
    const facts=$("removeFacts");facts.replaceChildren();
    const add=(k,v)=>facts.append(el("dt",{text:k}),el("dd",{text:v}));
    add("Revision",record.revision.slice(0,12));add("Files only this model uses",removal.paths.length+" · "+GB(removal.bytes));add("Kubernetes resources",(removal.resources||[]).map(r=>r.kind+" "+r.name).join(", ")||"none");
    $("removeFiles").replaceChildren(...removal.paths.map(p=>el("li",{class:"mono",text:p})));
    $("delete-files").checked=false;$("removal").showModal();
  }catch(e){fail(e)}
}
$("removal").addEventListener("close",async()=>{
  if($("removal").returnValue!=="confirm"||!removal){removal=null;return}
  try{const r=await api("/api/remove",{id:removal.id,revision:removal.revision,delete:$("delete-files").checked,confirmation:removal.confirmation});message("Removal queued. Files stay protected until the model is retired.","ok");refresh()}
  catch(e){fail(e)}finally{removal=null}
});

/* ---------- refresh ---------- */
async function refresh(){
  const[jobs,models]=await Promise.all([api("/api/jobs"),api("/api/models")]);
  // Generation jobs live in Creation Studio (same /api/generate backend); this page lists install/remove work only.
  renderJobs(jobs.filter(j=>{try{return JSON.parse(j.selection).operation!=="generate"}catch{return true}}));
  managed=models;renderModels();
}
async function refreshSystem(){try{system=await api("/api/system")}catch(e){system={available:false,reason:e.message,models:[]}}renderGpu();renderModels()}
function markTab(){for(const t of document.querySelectorAll(".tab"))t.classList.toggle("on",t.getAttribute("href")===(location.hash||"#models"))}
window.addEventListener("hashchange",markTab);markTab();
api("/api/session").then(async s=>{csrf=s.csrf;await Promise.all([refresh(),refreshSystem()])}).catch(fail);
setInterval(()=>refresh().catch(fail),3000);setInterval(refreshSystem,10000);
