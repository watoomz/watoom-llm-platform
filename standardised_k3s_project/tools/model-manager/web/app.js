const BASE=location.pathname.replace(/\/$/,"");let csrf="",current=null;const $=id=>document.getElementById(id);
async function api(path,value){const response=await fetch(BASE+path,{method:value?"POST":"GET",headers:value?{"Content-Type":"application/json","X-CSRF-Token":csrf}:{},body:value?JSON.stringify(value):undefined});const result=await response.json();if(!response.ok)throw Error(result.error||response.status);return result}
function message(text){$("message").textContent=text}
function settings(profile){$("settings").replaceChildren();for(const [key,value]of Object.entries(profile.values)){const label=document.createElement("label");label.textContent=key;const choices=profile.options&&profile.options[key];const input=document.createElement(choices?"select":"input");if(choices){for(const item of choices){const option=document.createElement("option");option.value=String(item);option.textContent=String(item);input.append(option)}if(!choices.map(String).includes(String(value))){const option=document.createElement("option");option.value=String(value);option.textContent=String(value)+" (custom)";input.append(option)}}input.dataset.key=key;input.dataset.type=typeof value;input.value=value===null?"":String(value);label.append(input);if(choices&&typeof value==="number"){const custom=document.createElement("option");custom.value="__custom__";custom.textContent="Custom value…";input.append(custom);input.onchange=()=>{const previous=label.querySelector("input[data-custom]");if(previous)previous.remove();if(input.value==="__custom__"){const numeric=document.createElement("input");numeric.dataset.custom="true";numeric.dataset.key=key;numeric.dataset.type="number";numeric.type="number";numeric.placeholder="Enter validated numeric value";label.append(numeric)}}}const source=document.createElement("small");source.textContent=profile.sources[key].type+" · "+(profile.sources[key].evidence||"Saved override");label.append(source);$("settings").append(label)}}
function values(){const result={};for(const input of $("settings").querySelectorAll("input,select"))if(input.value==="__custom__")continue;else result[input.dataset.key]=input.dataset.type==="number"?Number(input.value):input.dataset.type==="boolean"?input.value==="true":input.value||null;return result}
function bytes(n){return n===null?"Unknown":n.toLocaleString()+" bytes · "+(n/1e9).toFixed(3)+" GB · "+(n/1073741824).toFixed(3)+" GiB"}
function size(){const v=current.metadata.variants.find(v=>v.id===$("variant").value);$("size").textContent=v?bytes(v.bytes)+" · "+(v.precision||"precision not published")+" · "+v.files.length+" file(s)":"No supported variants";$("files").replaceChildren();for(const f of v?.files||[]){const row=document.createElement("li");row.textContent=f.path+" — "+bytes(f.size);$("files").append(row)}$("install").disabled=!v||v.bytes===null}
async function inspect(url){
 message("Inspecting metadata…");current=await api("/api/inspect",{url});
 $("name").textContent=current.metadata.repository;
 $("metadata").textContent=current.metadata.kind+" · "+current.metadata.revision+" · Base: "+(current.metadata.base_model||"none declared");
 $("revision").replaceChildren();
 const refs=[{name:current.metadata.revision,ref:current.metadata.revision}];
 for(const group of ["branches","tags"])for(const ref of current.metadata.refs[group]||[])refs.push({name:group+": "+ref.name,ref:ref.ref||ref.name});
 for(const ref of refs){const o=document.createElement("option");o.value=ref.ref.replace("refs/heads/","").replace("refs/tags/","");o.textContent=ref.name;$("revision").append(o)}
 $("variant").replaceChildren();for(const v of current.metadata.variants){const o=document.createElement("option");o.value=v.id;o.textContent=v.id;$("variant").append(o)}
 $("preset").replaceChildren();const neutral=document.createElement("option");neutral.value="";neutral.textContent="Recommendations / saved overrides";$("preset").append(neutral);
 for(const [i,p]of current.settings.presets.entries()){const o=document.createElement("option");o.value=i;o.textContent=p.name;$("preset").append(o)}
 $("uncertainty").textContent=current.settings.uncertainty||"";
 settings(current.settings);size();$("details").hidden=false;message("Metadata inspected. No weights downloaded.");
}
$("inspect").onsubmit=e=>{e.preventDefault();inspect($("url").value).catch(e=>message(e.message))};
$("revision").onchange=()=>inspect("https://huggingface.co/"+current.metadata.repository+"/tree/"+encodeURIComponent($("revision").value)).catch(e=>message(e.message));
$("preset").onchange=()=>{const p=current.settings.presets[Number($("preset").value)];if($("preset").value==="")return settings(current.settings);const profile=structuredClone(current.settings);for(const[k,e]of Object.entries(p.fields)){profile.values[k]=e.value;profile.sources[k]={type:"Published recommendation",evidence:p.name+" · README line "+e.line}}settings(profile);message("Published mode selected; save to persist this override.")};
$("variant").onchange=size;
$("save").onclick=async()=>{try{settings(await api("/api/overrides",{url:current.metadata.source,values:values()}));message("Overrides saved")}catch(e){message(e.message)}};
$("reset").onclick=async()=>{try{settings(await api("/api/overrides",{url:current.metadata.source,values:{}}));message("Published recommendations restored")}catch(e){message(e.message)}};
api("/api/session").then(async s=>{csrf=s.csrf;await refresh()}).catch(e=>message(e.message));

let removal=null;
async function refresh(){
 const jobs=await api("/api/jobs");$("jobs").replaceChildren();
 for(const j of jobs){const row=document.createElement("p");let selection;try{selection=JSON.parse(j.selection)}catch{selection={}}
 const detail=selection.operation==="generate"?(j.stage?" · "+j.stage:""):" · "+bytes(j.progress)+" · "+Math.round(j.average_bytes_per_second||0).toLocaleString()+" B/s";
 row.textContent=(selection.repository||selection.operation||"Job")+" · "+j.state+detail+(j.error?" · "+j.error:"");
 const action=["QUEUED","DOWNLOADING"].includes(j.state)?"cancel":["FAILED","CANCELLED","DOWNLOADED_REGISTRATION_FAILED"].includes(j.state)?"retry":null;
 if(j.state==="GENERATION_VERIFIED"){const show=document.createElement("button");show.textContent="View actual result";show.onclick=async()=>{try{const result=await api("/api/result?id="+encodeURIComponent(j.id));const box=document.createElement("div");if(result.png_base64){const image=document.createElement("img");image.alt="Generated validation output";image.src="data:image/png;base64,"+result.png_base64;box.append(image)}else box.textContent=result.text;row.append(box);show.disabled=true}catch(e){message(e.message)}};row.append(show)}
 if(action){const b=document.createElement("button");b.textContent=action==="cancel"?"Cancel (retain partials)":"Retry";b.onclick=async()=>{try{await api("/api/"+action,{id:j.id});await refresh()}catch(e){message(e.message)}};row.append(b)}$("jobs").append(row)}
 const models=await api("/api/models");$("models").replaceChildren();$("base").replaceChildren();
 for(const m of models){
  if(m.kind==="diffusion-pipeline"){const o=document.createElement("option");o.value=m.id;o.textContent=m.repository+" @ "+m.revision.slice(0,12);$("base").append(o)}
  const row=document.createElement("p");row.textContent=m.repository+" · downloaded="+m.downloaded+" · configured="+m.configured+" · registered="+m.registered+" · tested="+m.tested;
  const button=document.createElement("button");button.textContent="Remove model";button.onclick=async()=>{try{removal=await api("/api/remove-plan",{id:m.id,revision:m.revision});$("remove-details").textContent=JSON.stringify(removal,null,2);$("delete-files").checked=false;$("removal").hidden=false}catch(e){message(e.message)}};row.append(button);
  if(m.registered){const generate=document.createElement("button");generate.textContent="Generate / validate";generate.onclick=async()=>{const prompt=window.prompt("Generation uses exclusive GPU admission; active work will block it. Enter a prompt:","A blue cube on a plain background");if(!prompt)return;try{const r=await api("/api/generate",{id:m.id,revision:m.revision,prompt});message("Generation queued "+r.job);refresh()}catch(e){message(e.message)}};row.append(generate)}
  $("models").append(row);
 }
}
$("cancel-remove").onclick=()=>{removal=null;$("removal").hidden=true};
$("confirm-remove").onclick=async()=>{try{const r=await api("/api/remove",{id:removal.id,revision:removal.revision,delete:$("delete-files").checked,confirmation:removal.confirmation});message("Removal queued: "+r.job+"; files remain protected until retirement completes");$("removal").hidden=true;refresh()}catch(e){message(e.message)}};
$("install").onclick=async()=>{try{const r=await api("/api/install",{url:current.metadata.source,revision:current.metadata.revision,variant:$("variant").value,settings:values(),base_install:$("base").value||null});message("Queued "+r.job);refresh()}catch(e){message(e.message)}};
$("safe").onclick=async()=>{try{settings(await api("/api/overrides",{url:current.metadata.source,values:{},safe_only:true}));message("Safe baseline restored")}catch(e){message(e.message)}};
setInterval(()=>refresh().catch(e=>message(e.message)),3000);
