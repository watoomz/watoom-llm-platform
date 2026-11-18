const BASE=location.pathname.replace(/\/$/,"");const $=id=>document.getElementById(id);
let csrf="",skills=[],current=null,original="";
async function api(path,value){
 const response=await fetch(BASE+path,{method:value?"POST":"GET",headers:value?{"Content-Type":"application/json","X-CSRF-Token":csrf}:{},body:value?JSON.stringify(value):undefined});
 const result=await response.json().catch(()=>({error:"Unexpected response ("+response.status+")"}));
 if(!response.ok)throw new Error(result.error||("Request failed ("+response.status+")"));return result}
function message(text){$("message").textContent=text}
function dirty(){return current&&$("content").value!==original}
function liveNote(live){return live==="differs"?"Live copy differs from the repository (a playbook run or direct edit). Saving overwrites the live copy with what you save.":live==="absent"?"Not installed in WatooM-Code; saving commits to the repository only.":""}
function renderList(){
 const term=$("filter").value.toLowerCase();$("skills").replaceChildren();
 for(const s of skills){if(term&&!s.name.toLowerCase().includes(term))continue;
  const li=document.createElement("li"),b=document.createElement("button");b.textContent=s.name+" ";
  const note=document.createElement("small");note.textContent=s.live==="differs"?"· live differs":s.live==="absent"?"· not live":"";b.append(note);
  if(current&&current.name===s.name)b.setAttribute("aria-current","true");b.onclick=()=>open(s.name);li.append(b);$("skills").append(li)}}
async function loadList(){
 const data=await api("/api/skills");skills=data.skills;
 $("repo").textContent=data.skills.length+" skills · branch "+(data.branch||"detached")+(data.unpushed===null?"":" · "+data.unpushed+" commit(s) not pushed to GitHub");renderList()}
async function open(name){
 if(dirty()&&!confirm("Discard unsaved changes to "+current.name+"?"))return;
 message("Loading "+name+"…");const s=await api("/api/skill?name="+encodeURIComponent(name));current=s;original=s.content;
 $("empty").hidden=true;$("editor").hidden=false;$("title").textContent=s.name;$("content").value=s.content;$("note").value="";
 $("meta").textContent=s.path+(s.last_commit?" · last commit "+s.last_commit.commit+" "+s.last_commit.date.slice(0,16).replace("T"," ")+" — "+s.last_commit.subject:"");
 const warn=s.dirty?"The repository copy has uncommitted changes; saving is blocked until they are resolved.":liveNote(s.live);
 $("warning").hidden=!warn;$("warning").textContent=warn;$("save").disabled=s.dirty;renderList();message("");loadHistory(name)}
async function loadHistory(name){
 const h=await api("/api/history?name="+encodeURIComponent(name));$("history").replaceChildren();
 for(const c of h.commits){const li=document.createElement("li");li.textContent=c.commit+" · "+c.date.slice(0,16).replace("T"," ")+" · "+c.subject;$("history").append(li)}}
$("filter").oninput=renderList;
$("discard").onclick=()=>{if(current){$("content").value=original;message("Changes discarded")}};
$("save").onclick=async()=>{
 if(!current)return;if(!dirty()){message("No changes to save");return}
 $("save").disabled=true;message("Saving and committing…");
 try{const r=await api("/api/save",{name:current.name,content:$("content").value,blob:current.blob,message:$("note").value});
  message(r.changed?"Committed "+r.commit+(r.live==="matches"?" and updated the live skill.":" (skill is not installed live)."):"No change.");
  const name=current.name;current=null;await loadList();await open(name)}
 catch(e){message("Not saved: "+e.message);$("save").disabled=false}};
addEventListener("beforeunload",e=>{if(dirty()){e.preventDefault();e.returnValue=""}});
api("/api/session").then(s=>{csrf=s.csrf;return loadList()}).catch(e=>message(e.message));
