// Conservative shell-read subset; classify the complete invocation, never just a command prefix.
export function shellReadOnly(command) {
 if(typeof command!=="string" || !command.trim() || command.length>16000)return false;
 // No expansion, substitution, command chaining, redirection or multiline programs.
 if(/[\n\r$`\\;&<>(){}]/.test(command))return false;
 const pipeline=command.split("|");if(pipeline.length>6)return false;
 const allowed=new Set(["cat","ls","head","tail","stat","wc","grep","rg","pwd","readlink","realpath","md5sum","sha1sum","sha224sum","sha256sum","sha384sum","sha512sum","b2sum","cksum","du","df","uname","id","whoami"]);
 for(const part of pipeline){
  const tokens=[];let rest=part.trim();
  while(rest){
   const match=/^(?:'([^']*)'|"([^"]*)"|([^\s'"|]+))(?:\s+|$)/.exec(rest);
   if(!match)return false;tokens.push(match[1]??match[2]??match[3]);rest=rest.slice(match[0].length);
  }
  if(!tokens.length)return false;
  let executable=tokens.shift();
  if(executable.startsWith("/usr/bin/"))executable=executable.slice(9);
  else if(executable.startsWith("/bin/"))executable=executable.slice(5);
  if(!allowed.has(executable))return false;
  // These rg options execute external preprocessors/decompressors or hostname programs.
  if(executable==="rg" && tokens.some(x=>/^--(?:pre|hostname-bin)(?:=|$)/.test(x) || /^--(?:search-zip|pre-glob)(?:=|$)/.test(x) || /^-[^-]*z/.test(x)))return false;
  // Avoid indefinite followers and user-controlled printf formats.
  if(executable==="tail" && tokens.some(x=>/^--follow(?:=|$)/.test(x) || /^-[^-]*[fF]/.test(x)))return false;
  if(tokens.some(x=>/[\x00-\x1f]/.test(x)))return false;
 }
 return true;
}
export function readShellPermission(event,bindings){
 if(event.action!=="shell" || event.source?.type!=="tool")return;
 const key=JSON.stringify([event.sessionID,event.source.messageID,event.source.id]);
 const binding=bindings.get(key);
 if(binding && binding.agent===event.agent && shellReadOnly(binding.command))event.effect="allow";
}

import {createHash} from "node:crypto";
import {posix} from "node:path";
import {mkdir,lstat,writeFile,readFile,readdir,realpath,stat} from "node:fs/promises";
import {readFileSync,statSync} from "node:fs";
import {fileURLToPath} from "node:url";
export async function archiveViewedImage(result,input,context,root="/data/ai/projects/images/review") {
 const parts=(Array.isArray(result?.content) ? result.content : []).filter(p=>p.type==="file" && /^data:image\/(png|jpeg|webp);base64,/.test(p.uri || ""));
 if(!parts.length)return [];
 if(!/^[A-Za-z0-9_-]+$/.test(context.sessionID))throw Error("Invalid capture session");
 for(const dir of [root,posix.join(root,"viewed"),posix.join(root,"viewed",context.sessionID)]) {
  await mkdir(dir,{recursive:true});if(!(await lstat(dir)).isDirectory() || (await lstat(dir)).isSymbolicLink())throw Error("Image review directory must not be a symlink");
 }
 const copies=[];
 for(const part of parts) {
  const mime=part.uri.slice(5,part.uri.indexOf(";")),bytes=Buffer.from(part.uri.slice(part.uri.indexOf(",")+1),"base64");
  if(bytes.length>33554432)throw Error("Review image exceeds32MiB");
  const sha=createHash("sha256").update(bytes).digest("hex"),ext=mime==="image/jpeg"?"jpg":mime.split("/")[1];
  const path=posix.join(root,"viewed",context.sessionID,sha+"."+ext);
  try{await writeFile(path,bytes,{flag:"wx",mode:0o644});}catch(e){if(e.code!=="EEXIST")throw e;if((await lstat(path)).isSymbolicLink() || createHash("sha256").update(await readFile(path)).digest("hex")!==sha)throw Error("Existing review copy does not match");}
  const metadata={source_path:input.path || input.filePath || null,session_id:context.sessionID,agent:context.agent,sha256:sha,bytes:bytes.length,copied_at:new Date().toISOString(),capture_kind:"pixels_presented_to_agent"};
  try{await writeFile(path+".json",JSON.stringify(metadata,null,2)+"\n",{flag:"wx",mode:0o644});}catch(e){if(e.code!=="EEXIST")throw e;}
  copies.push(path);
 }
 return copies;
}


export const BUDGET = 6;
// Read-only discovery lets the coordinator finish small tasks itself instead of delegating after a few reads.
export const READ_BUDGET = 18;
const DISCOVERY = new Set(["read","glob","grep","list","websearch","webfetch","watoom_specialist_list"]);
const spent = state => state.direct >= BUDGET || (state.reads || 0) >= READ_BUDGET;
// Bounded recovery: rejected guard calls must not endlessly increment recovery
// counters. guardRejections caps the child-rejection feedback into `errors`;
// CRITIC_ESCALATION_CAP stops repeated critic subagent handoffs after N attempts.
export const GUARD_REJECTION_CAP = 3;
export const CRITIC_ESCALATION_CAP = 3;
export const SEARCH_DEDUP_CAP = 64;
// Agent prompt sections by exact heading. Engine/asset procedures apply only to games/images
// projects (work, writing, homelab and llm groups omit them); read-only roles never run worker, download or authoring procedures.
const ENGINE_SECTIONS = new Set(["Engine and asset worker routes"]);
const EXECUTION_SECTIONS = new Set(["Making changes","Engine and asset worker routes"]);
const NON_ENGINE_AGENTS = new Set(["watoom-kali","watoom-creative-writer"]);
export const developmentProject = directory => typeof directory==="string" && /^\/data\/ai\/projects\/(work|writing|homelab|llm)\/[^/]/.test(directory);
export function promptDrop(agent,directory) {
  const drop=new Set();
  if(NON_ENGINE_AGENTS.has(agent) || developmentProject(directory))for(const name of ENGINE_SECTIONS)drop.add(name);
  if(readOnlyRoles.has(agent))for(const name of EXECUTION_SECTIONS)drop.add(name);
  return drop;
}
export function trimSections(text,drop) {
  if(!drop.size || typeof text!=="string")return text;
  const parts=text.split(/^(?=## )/m);
  return parts[0]+parts.slice(1).filter(part=>!drop.has(part.slice(3,part.indexOf("\n")===-1 ? undefined : part.indexOf("\n")).trim())).join("");
}
const protectedAgents = new Set(["watoom-workflow","watoom-builder","watoom-investigator","watoom-reviewer","watoom-critic","watoom-creative-writer","watoom-developer","watoom-automation-expert","watoom-3d-modeller","watoom-integration-expert","watoom-qa-tester","watoom-adversarial-tester","watoom-blind-tester","watoom-researcher","watoom-game-designer","watoom-systems-designer"]);
const criticCallers = new Set(["watoom-builder","watoom-investigator","watoom-reviewer","watoom-developer","watoom-automation-expert","watoom-3d-modeller","watoom-integration-expert","watoom-qa-tester","watoom-adversarial-tester","watoom-blind-tester","watoom-researcher","watoom-game-designer","watoom-systems-designer"]);
// Every role the coordinator may start as a child. Keep in step with the routing table in
// watoom-code/files/native/_src/shared/03_agent_selection_and_handoff_boundaries.md.
export const COORDINATOR_CHILDREN = ["watoom-investigator","watoom-researcher","watoom-game-designer","watoom-systems-designer","watoom-critic","watoom-developer","watoom-builder","watoom-3d-modeller","watoom-automation-expert","watoom-integration-expert","watoom-qa-tester","watoom-adversarial-tester","watoom-blind-tester","watoom-reviewer","watoom-kali"];
const readOnlyRoles = new Set(["watoom-investigator","watoom-reviewer","watoom-critic","watoom-qa-tester","watoom-adversarial-tester","watoom-blind-tester","watoom-researcher","watoom-game-designer","watoom-systems-designer"]);
const exempt = new Set(["skill","question","watoom_memory_recall"]);
const unpack = value => value?.data ?? value;
const initial = seed => ({version:1,direct:seed?.direct || 0,reads:seed?.reads || 0,errors:seed?.requireCritic ? 2 : 0,child:null,pendingVisual:null,reviews:[],calls:[],guardRejections:seed?.guardRejections || 0,criticEscalations:seed?.criticEscalations || 0,searchDedup:seed?.searchDedup || {}});
const imagePart = result => Array.isArray(result?.content) ? result.content.find(p => p.type === "file" && /^data:image\//.test(p.uri || "")) : undefined;
function imagePresent(value) {
  if (!value || typeof value !== "object") return false;
  if ((value.type === "media") || /^image\//.test(value.mime || value.mimeType || "") || /^data:image\//.test(value.uri || "")) return true;
  return Object.values(value).some(x => Array.isArray(x) ? x.some(imagePresent) : imagePresent(x));
}
const checkpoint = input => typeof input?.path === "string" && /(?:^|\/)\.opencode\/work\/[^.][^/]*\//.test(input.path) && !input.path.split("/").includes("..") && typeof input.content === "string" && input.content.length <= 32768;

export function finalReceipt(content) {
  if(typeof content!=="string" || content.length>32768)return null;
  const text=content.trim();
  try {const value=JSON.parse(text);return value && typeof value==="object" && !Array.isArray(value) ? value : null;}catch{}
  // Tolerate a short prose/fence wrapper, never ambiguous multiple JSON values.
  const start=text.indexOf("{"),end=text.lastIndexOf("}");
  if(start<0 || end<start || /[{}]/.test(text.slice(0,start)+text.slice(end+1)))return null;
  try {const value=JSON.parse(text.slice(start,end+1));return value && typeof value==="object" && !Array.isArray(value) ? value : null;}catch{return null;}
}

export function receiptPath(path, state) {
  if(typeof path!=="string" || path.split("/").includes(".."))return false;
  if(/(?:^|\/)\.opencode\/(?:work|validation)\/[^.][^/]*\/(?:[^/]+\/)*visual-review[^/]*\.json$/.test(path))return true;
  // A pipeline render's sibling reports directory is its established receipt location.
  // Bind it to the exact pending image revision; no arbitrary report writes.
  const image=state.pendingVisual?.path;
  if(typeof image!=="string" || !image.startsWith("/data/ai/projects/") || posix.basename(posix.dirname(image))!=="renders")return false;
  return posix.dirname(path)===posix.join(posix.dirname(posix.dirname(image)),"reports") && /^visual-review[^/]*\.json$/.test(posix.basename(path));
}
// Captures live in <project>/.opencode/captures/<job>/; a receipt beside the image nested a
// second .opencode tree inside it. Anchor such receipts at the project's own validation folder.
export function suggestedReceiptPath(image,sessionID) {
  const marker=image.indexOf("/.opencode/");
  if(marker>0)return posix.join(image.slice(0,marker),".opencode/validation",sessionID,"visual-review.json");
  if(image.startsWith("/data/ai/projects/") && posix.basename(posix.dirname(image))==="renders")return posix.join(posix.dirname(posix.dirname(image)),"reports","visual-review.json");
  return posix.join(posix.dirname(image),".opencode/validation",sessionID,"visual-review.json");
}
export function constrainReceipt(event,state) {
  if(!state.pendingVisual || !event.tools.write)return;
  const tool=event.tools.write,input=structuredClone(tool.input || {type:"object",properties:{}});
  input.properties ??={};
  input.properties.path={type:"string",enum:[suggestedReceiptPath(state.pendingVisual.path,event.sessionID)],description:"Accepted visual receipt path; content must match the pending image/hash/model and contain pixel observations."};
  event.tools.write={...tool,input,description:"Save the pending pixel-review JSON receipt to the exact path in the schema. Do not write a checkpoint or image file."};
}

export function semanticReceipt(value) {
 if(!value || Object.keys(value).some(k=>!["review_version","review_scope","image_path","image_sha256","model","basis","verdict","observations","framing","defects","uncertainties","inferences"].includes(k)))return false;
 if(value?.review_version!==2 || value.review_scope!=="single_frame_pixels")return false;
 if(typeof value.framing?.usable!=="boolean" || !Array.isArray(value.framing.issues) || !Array.isArray(value.defects) || !Array.isArray(value.uncertainties) || !Array.isArray(value.inferences))return false;
 if(value.inferences.length!==0 || value.framing.issues.length>6 || value.defects.length>6 || value.uncertainties.length>6 || (!value.framing.usable && value.framing.issues.length===0))return false;
 if(![...value.framing.issues,...value.defects,...value.uncertainties,...value.inferences].every(x=>typeof x==="string" && x.length<=600))return false;
 // PASS needs a usable frame AND no visible quality defect: a readable but
 // untextured, smeared or empty scene is a FAIL, not "usable for inspection".
 return value.verdict!=="PASS" || (value.framing.usable && value.framing.issues.length===0 && value.defects.length===0);
}
export function reviewSchema(v) {
 const base={type:"object",additionalProperties:false,required:["review_version","review_scope","image_path","image_sha256","model","basis","verdict","observations","framing","defects","uncertainties","inferences"],properties:{review_version:{const:2},review_scope:{const:"single_frame_pixels"},image_path:{const:v.path},image_sha256:{const:v.sha256},model:{const:v.presentedBy},basis:{const:"pixels"},verdict:{enum:["PASS","FAIL","BLOCKED"]},observations:{type:"array",minItems:2,maxItems:6,items:{type:"string",minLength:12,maxLength:400}},framing:{type:"object",additionalProperties:false,required:["usable","issues"],properties:{usable:{type:"boolean"},issues:{type:"array",maxItems:6,items:{type:"string",maxLength:600}}}},defects:{type:"array",maxItems:6,items:{type:"string",minLength:12,maxLength:600}},uncertainties:{type:"array",maxItems:6,items:{type:"string",maxLength:600}},inferences:{const:[]}}};
 const branch=(verdicts,usable,minIssues,maxIssues,maxDefects=6)=>{
  const schema=structuredClone(base);
  schema.properties.verdict={enum:verdicts};
  schema.properties.framing.properties.usable={const:usable};
  Object.assign(schema.properties.framing.properties.issues,{minItems:minIssues,maxItems:maxIssues});
  schema.properties.defects.maxItems=maxDefects;
  return schema;
 };
 // Constrain generation as well as post-validation. Never silently rewrite a
 // model's verdict or discard framing issues to turn a rejection into a PASS.
 return {...base,anyOf:[branch(["PASS"],true,0,0,0),branch(["FAIL","BLOCKED"],true,0,6),branch(["FAIL","BLOCKED"],false,1,6)]};
}

// The coordinator hands its pixel review back through this guard tool, not as a final
// text message: a final message ends the turn (finish=stop) and the session idles after
// every vision review. A tool result lets the same turn continue. Arguments are
// grammar-constrained by the forced tool schema and still pass reviewReceipt.
export const VISUAL_RECEIPT_TOOL="watoom_visual_receipt";

// Learned lessons. The memory curator exports engine API facts (the engine's own rejections from worker receipts)
// and the owner's "+" chat lessons to learned-lessons.json beside the guard package. Agents see them as a short
// standing note, and a script write/edit that uses a rejected name gets a warning in the tool result.
export const LEARNED_LESSONS_FILE=fileURLToPath(new URL("../learned-lessons.json",import.meta.url));
let learnedCache={file:null,mtime:0,data:null};
export function loadLearnedLessons(file=LEARNED_LESSONS_FILE) {
 try {
  const st=statSync(file);
  if(st.size>1048576)return null;
  if(learnedCache.file===file && learnedCache.mtime===st.mtimeMs)return learnedCache.data;
  const data=JSON.parse(readFileSync(file,"utf8"));
  const ok=data?.version===1 && Array.isArray(data.engine) && Array.isArray(data.owner);
  learnedCache={file,mtime:st.mtimeMs,data:ok?data:null};
  return learnedCache.data;
 } catch {return null;}
}
const learnedName=x=>typeof x==="string" && /^[A-Za-z_][A-Za-z0-9_]*$/.test(x);
const learnedEngine=data=>(data?.engine || []).filter(e=>learnedName(e?.class) && learnedName(e?.member) && typeof e.version==="string" && typeof e.engine==="string");
const learnedUse={call:"()",get:"",set:" (assignment)"};
export function learnedLessonsNote(data) {
 const engine=learnedEngine(data);
 const owner=(data?.owner || []).filter(o=>typeof o?.rule==="string");
 if(!engine.length && !owner.length)return null;
 let note="";
 if(engine.length) {
  const version=engine[0].engine+" "+engine[0].version;
  let list="";
  for(const e of engine){const item=e.class+"."+e.member+(learnedUse[e.kind] ?? "");if((list+item).length>1500)break;list+=(list?", ":"")+item;}
  note+="LEARNED ENGINE FACTS ("+version+"): the engine itself rejected these on earlier runs, so they do not work as used: "+list+". Check the real name in the class reference for this exact version (or ClassDB headlessly) before replacing one; never move the same name to another class.";
 }
 if(owner.length) {
  let rules="";
  for(const o of owner.slice(0,8)){const item="- "+o.rule.replace(/\s+/g," ").slice(0,300);if((rules+item).length>1500)break;rules+="\n"+item;}
  note+=(note?"\n":"")+"OWNER LESSONS (submitted by the owner with +):"+rules;
 }
 return note;
}
const escapeRe=x=>x.replace(/[.*+?^${}()|[\]\\]/g,"\\$&");
export function learnedApiWarnings(text,data) {
 if(typeof text!=="string" || !text)return [];
 const out=[];
 for(const e of learnedEngine(data)) {
  const m=escapeRe(e.member);
  const rx=e.kind==="call" ? new RegExp("\\."+m+"\\s*\\(") : e.kind==="set" ? new RegExp("\\."+m+"\\s*=(?!=)") : new RegExp("\\."+m+"\\b");
  // A short plain word (e.g. material) is too common to flag unless its class is named in the same text.
  if(!e.member.includes("_") && e.kind!=="call" && !new RegExp("\\b"+escapeRe(e.class)+"\\b").test(text))continue;
  if(rx.test(text))out.push(e.class+"."+e.member+(learnedUse[e.kind] ?? "")+" ("+e.engine+" "+e.version+")");
  if(out.length>=5)break;
 }
 return out;
}
export function withLearnedWarning(result,warnings) {
 if(!warnings.length || !result || typeof result!=="object")return result;
 const text="\nLEARNED_API_WARNING: the engine rejected "+warnings.join("; ")+" on an earlier run. Verify the real name against the class reference for this exact version before keeping it.";
 try {
  if(typeof result.content==="string")result.content+=text;
  else if(typeof result.output==="string")result.output+=text;
  result.metadata={...result.metadata,learned_api_warning:warnings};
 } catch {}
 return result;
}
// llama.cpp does not constrain forced tool-call arguments when the schema uses anyOf
// (verified live: arguments came back as {}), but a flat object schema is enforced. The
// verdict/framing/defects consistency rules stay in reviewReceipt/semanticReceipt.
export function flatReviewSchema(v) {
 const {anyOf,...flat}=structuredClone(reviewSchema(v));
 flat.properties.inferences={type:"array",maxItems:0};
 return flat;
}
export function receiptAsWrite(input,state) {
 const p=state.pendingVisual;
 if(!p)return {path:"",content:""};
 return {path:posix.join(posix.dirname(p.path),".opencode/validation/completed/visual-review.json"),content:JSON.stringify(input ?? {})};
}
export function isolatedReviewBody(body,pending,model,sessionID,agent) {
 let image;
 const visit=x=>{if(!x || typeof x!=="object")return;if(x.type==="image_url" && requestContainsImage(x,pending.sha256))image=x;for(const v of Object.values(x))if(Array.isArray(v))v.forEach(visit);else if(v && typeof v==="object")visit(v);};visit(body.messages);
 if(!image)return body;
 const schema=reviewSchema({...pending,presentedBy:model});
 const path=posix.join(posix.dirname(pending.path),".opencode/validation",sessionID,"visual-review.json");
 // The coordinator (watoom-workflow) hands its review back as a final text message,
 // consumed by reconcileCompletedVisualReview. Its free-form write-tool arguments are
 // NOT grammar-constrained, so this reasoning model emits incomplete receipts (missing
 // verdict/observations) and the receipt is rejected. Force the strict response_format
 // (text) path for the coordinator so generation is grammar-constrained and reconcile
 // receives a valid receipt. Child reviewers keep the write path (lines ~782/812/919).
 const write=agent==="watoom-workflow" ? undefined : (body.tools || []).find(x=>x.type==="function" && x.function?.name==="write");
 const instruction="Review ONLY the attached pixels, independently of filenames, prior scene descriptions and desired results. Give 2-6 short visible facts with location, approximate count, colours and framing. Use 'bright patch' instead of inferring a sun/light; uncertain objects must remain uncertain. Never infer renderer/API, source pack/GLB IDs, dimensions, normals, hidden meshes, animation, correctness or technical cause from a static view. Do not invent hypotheses in a pixel-only inspection: inferences must be []. Put missing evidence in uncertainties; causal investigation happens separately using source/runtime evidence. Use broad positions, not unmeasured numerical percentages or physical dimensions. Describe featureless fields as background, not an assumed sky/ground type unless clearly identifiable. Check whether the main subject/ground is actually visible, readable and framed, or mostly background/clipped/occluded. If framing prevents assessment, framing.usable=false and verdict=FAIL or BLOCKED, never PASS. Then judge visible quality as a demanding art director, from these pixels alone. List each visible quality defect in defects (short, located), for example: large surfaces in a flat single colour with no visible texture or surface detail; smeared, blurry, stretched or low-resolution textures; a visible tiling grid or seams; a featureless grey or washed-out background where an outdoor sky would be; a hard flat horizon line or visible world edge; a mostly empty or sparse scene; untextured placeholder primitives; objects floating, clipping or missing parts; relief with no light/shadow variation; over- or under-exposure. A dry trough or channel with no visible water surface is a defect if it reads as a creek/river bed. Do not excuse a defect because the style is low-poly or stylised. PASS requires a usable frame AND defects=[]; any defect means FAIL. PASS is still a single-frame judgement, NOT complete task acceptance, rig/engine validation or proof of correct art. Empty/unhelpful views fail. Do not fill missing content from expectations. Produce DATA, never a JSON schema. Copy only these fixed metadata fields: "+JSON.stringify({review_version:2,review_scope:"single_frame_pixels",image_path:pending.path,image_sha256:pending.sha256,model,basis:"pixels"})+". Add verdict (FAIL, BLOCKED, or PASS), observations (2-6 short strings), framing {usable:boolean,issues:string[]}, defects:string[] (0-6), uncertainties:string[], and inferences:[]. If issues or defects is nonempty or usable is false, verdict MUST NOT be PASS. Framing issues are obstacles to assessing the visible scene; harmless interface labels/logos can be recorded as observations instead. If you do list any framing issue, choose FAIL or BLOCKED even if the scene looks attractive. Never remove a real obstruction just to obtain PASS. Do not add type/properties/required/const schema keywords. "+(agent==="watoom-workflow" ? "Call only "+VISUAL_RECEIPT_TOOL+" once with the complete receipt as its arguments." : write ? "Call only native write once, path "+JSON.stringify(path)+", content the complete JSON receipt. Do not read other files, explain plans or print XML." : "Return ONLY the complete JSON receipt.");
 const next={...body,messages:[{role:"system",content:"Independent pixel-only visual inspection. Task history and author claims are intentionally excluded."},{role:"user",content:[{type:"text",text:instruction},image]}],temperature:0,parallel_tool_calls:false};
 if(agent==="watoom-workflow"){next.tools=[{type:"function",function:{name:VISUAL_RECEIPT_TOOL,description:"Record the independent pixel review receipt for the attached image. Call once with the complete receipt as arguments.",parameters:flatReviewSchema({...pending,presentedBy:model})}}];next.tool_choice={type:"function",function:{name:VISUAL_RECEIPT_TOOL}};delete next.response_format;}
 else if(write){next.tools=[write];next.tool_choice={type:"function",function:{name:write.function.name}};delete next.response_format;}
 else {delete next.tools;delete next.tool_choice;next.response_format={type:"json_schema",json_schema:{name:"isolated_pixel_review",strict:true,schema}};}
 return next;
}

// The isolated review step's own reasoning/write stays in native history. Without
// an explicit hand-back the next step imitates it, replies with the review JSON and
// ends the task turn. Note once, in the leading system message (template-safe).
export function resumeAfterReview(body,review) {
 const note="Guard note: the independent pixel review of "+review.path+" is recorded (verdict "+review.verdict+(Array.isArray(review.defects) && review.defects.length ? "; visible defects: "+review.defects.join("; ") : "")+"). A FAIL with defects means the work is not acceptable yet: fix those defects before claiming progress. It was a side check, not the task result or a final reply. Continue the task from where it was before the image was read; do not reply with review JSON.";
 const messages=Array.isArray(body.messages)?[...body.messages]:[];
 const first=messages[0];
 if(first?.role==="system" && typeof first.content==="string")messages[0]={...first,content:first.content+"\n\n"+note};
 else if(first?.role==="system" && Array.isArray(first.content))messages[0]={...first,content:[...first.content,{type:"text",text:note}]};
 else messages.unshift({role:"system",content:note});
 return {...body,messages};
}
// Multi-image review queue. Pixel review stays strictly one image at a time
// (each receipt is bound to one exact image hash), but an agent that reads a
// second capture view while one review is pending must not be punished or give
// up on it: the extra image is queued and offered next, so every captured view
// gets its own review instead of being reported "NOT TESTED".
export const REVIEW_QUEUE_CAP=12;
export const REVIEW_QUEUE_TTL_MS=4*3600*1000;
export function enqueueReview(state,path,now=Date.now()) {
 const q=(state.reviewQueue || []).filter(x=>now-x.time<REVIEW_QUEUE_TTL_MS);
 state.reviewQueue=q;
 if(typeof path!=="string" || !path || path===state.pendingVisual?.path || q.some(x=>x.path===path))return false;
 state.reviewQueue=[...q,{path,time:now}].slice(-REVIEW_QUEUE_CAP);
 return true;
}
export function dequeueReview(state,path) {
 if(state.reviewQueue?.length)state.reviewQueue=state.reviewQueue.filter(x=>x.path!==path);
}
export function reviewQueueNote(state,now=Date.now()) {
 const q=(state.reviewQueue || []).filter(x=>now-x.time<REVIEW_QUEUE_TTL_MS);
 if(state.pendingVisual || !q.length)return null;
 return "VISION QUEUE: "+q.length+" more image(s) still need their own pixel review: "+q.map(x=>x.path).join(", ")+". Read the next one now ("+q[0].path+"), review its pixels and save its matching receipt exactly as for the previous image, one image at a time, until the queue is empty. Do not report queued images as NOT TESTED or finish the review task while any remain; if one no longer exists, say so.";
}
export function reviewReceipt(input, state) {
  const pending = state.pendingVisual;
  if (!pending || !pending.presentedBy || pending.reviewMode!=="isolated-image-v2" || typeof input?.content !== "string" || input.content.length > 32768) return false;
  if (!receiptPath(input.path,state)) return false;
  let value;try {value=JSON.parse(input.content);} catch {return false;}
  if (!value || typeof value!=="object" || Array.isArray(value)) return false;
  return value.image_sha256 === pending.sha256 && value.image_path === pending.path &&
    value.model === pending.presentedBy && value.basis === "pixels" &&
    ["PASS","FAIL","BLOCKED"].includes(value.verdict) && Array.isArray(value.observations) &&
    value.observations.length >= 2 && value.observations.length<=6 && value.observations.every(x => typeof x === "string" && x.trim().length >= 12 && x.length<=400) && semanticReceipt(value);
}
export function reconcileCompletedVisualReview(state,event) {
 if(event.agent!=="watoom-workflow" || !state.pendingVisual || state.pendingVisual.presentationEvidence!=="exact-image-request-successful-response")return false;
 const messages=Array.isArray(event.messages)?event.messages:[];
 for(const message of [...messages].reverse()) {
  if(message.role!=="assistant")continue;
  if(message.tool_calls?.length || (Array.isArray(message.content) && message.content.some(p=>p.type==="tool-call" || p.type==="tool")))return false;
  const text=typeof message.content==="string" ? message.content : (Array.isArray(message.content)?message.content.filter(p=>p.type==="text").map(p=>p.text || "").join("\n"):"");
  const value=finalReceipt(text);
  if(!value || !reviewReceipt({path:"/review/.opencode/validation/completed/visual-review.json",content:JSON.stringify(value)},state))return false;
  const pending=state.pendingVisual;
  state.reviews=[...(state.reviews || []),{reviewVersion:2,semanticStatus:"MODEL_REPORTED_SINGLE_FRAME_ONLY",sha256:pending.sha256,model:pending.presentedBy,sessionID:event.sessionID,receipt:value,completion:"validated-final-response"}].slice(-16);
  state.visualResume={path:pending.path,verdict:value.verdict,defects:value.defects};
  state.pendingVisual=null;state.receiptFailures=0;state.presentationInFlight=null;
  return true;
 }
 return false;
}

export function receiptMismatch(input,state) {
 const p=state.pendingVisual;
 if(!receiptPath(input?.path,state))
  return "this is not a visual-review JSON receipt path; a checkpoint cannot finish the pending image review";
 let v;try{v=JSON.parse(input?.content || "");}catch{return "receipt content must be one JSON object, without Markdown, shell commands or commentary";}
 if(!v || typeof v!=="object" || Array.isArray(v))return "receipt must be a JSON object";
 if(!p?.presentedBy)return "verified image presentation missing; reread the same image with the verified model";
 if(p.reviewMode!=="isolated-image-v2")return "independent pixel-only review missing; reread the exact image so scene history is excluded";
 for(const [field,expected] of Object.entries({image_path:p.path,image_sha256:p.sha256,model:p.presentedBy,basis:"pixels"}))
  if(v[field]!==expected)return field+" mismatch; expected "+JSON.stringify(expected);
 if(!["PASS","FAIL","BLOCKED"].includes(v.verdict))return "verdict must be PASS, FAIL or BLOCKED";
 if(!Array.isArray(v.observations))return "observations must be an array of at least two pixel observations; observed is not the schema field";
 if(v.observations.length<2)return "observations requires at least two entries";
 const invalid=v.observations.findIndex(x=>typeof x!=="string" || x.trim().length<12);
 if(invalid>=0)return "observations["+invalid+"] must be a string of at least12 non-whitespace characters";
 if(!semanticReceipt(v))return "review_version2 requires single_frame_pixels scope, framing usable/issues, uncertainties and inferences; an unusable frame cannot PASS";
 return "receipt path contains a forbidden parent traversal or exceeds the32768-character budget";
}
export function recoveryGrant(state,sessionID,options,childState) {
 const v=childState?.pendingVisual;
 if(!state.childReviewBlocked || !v?.presentedBy)return;
 return (Array.isArray(options?.visualRecoveryGrants) ? options.visualRecoveryGrants : []).find(g=>g.parentSessionID===sessionID && g.childSessionID===state.child &&
   g.image_sha256===v.sha256 && /^[a-f0-9]{64}$/.test(g.nonce || "") && !(state.consumedRecoveryGrants || []).includes(g.nonce));
}
function acceptedReceipt(input,state) {
 let v;try{v=JSON.parse(input.content);}catch{return false;}
 if(!semanticReceipt(v))return false;
 return (state.reviews || []).some(r=>r.reviewVersion===2 && r.receipt && ["review_version","review_scope","image_path","image_sha256","model","basis","verdict","observations","framing","defects","uncertainties","inferences"].every(k=>JSON.stringify(r.receipt[k])===JSON.stringify(v?.[k])));
}
export const DELEGATION_ROLE_GUIDE="Investigator answers a missing fact about this project; researcher answers an external library/API/tool question; game-designer/systems-designer settle what to build before building; critic challenges a diagnosis/plan and is mandatory after two execution failures; implement with ONE of developer (app/game feature code), builder (IaC/infra, engine/worker pipeline jobs, anything else), 3d-modeller (3D assets), automation-expert (CI/CD, test harnesses), integration-expert (wiring existing systems); verify by risk tier with qa-tester (spec), adversarial-tester (input/security/network/money/shared services), blind-tester (user-facing, per milestone); reviewer gives final acceptance after the testers; watoom-kali runs Kali/Nmap work; coordinator owns scope/checkpoints. Reuse known evidence instead of repeating discovery. Critic first when required; investigator cannot satisfy that gate. No automatic chain through every role.";
export function constrainDelegation(event,state,childState) {
 const tool=event.tools.subagent;
 if(!tool)return;
 const coordinator=event.agent==="watoom-workflow";
 if(!coordinator && (!criticCallers.has(event.agent) || state.criticConsulted)){delete event.tools.subagent;return;}
 let allowed=coordinator ? COORDINATOR_CHILDREN : ["watoom-critic"];
 // 2026-11-09: errors>=2 is checked FIRST, not as an else-if after the resume lock -- state.errors can reach 2
 // purely from guard-level rejections (a typo, a stale sessionID; see the catch below), with no child ever
 // having actually executed and failed. The old order then force-locked agent to the existing non-critic
 // child's agent (the only schema-valid call) while the execution gate separately demanded agent==="critic"
 // for that exact call: neither request could ever succeed. Critic being mandatory now always wins the lock.
 const criticMandatory=coordinator && state.errors>=2;
 if(criticMandatory)allowed=["watoom-critic"];
 else if(coordinator && state.child && childState?.callingAgent)allowed=[childState.callingAgent];
 const input=structuredClone(tool.input || {type:"object",properties:{}});
 input.properties ??={};
 input.properties.agent={type:"string",enum:allowed,description:(criticMandatory && !state.child ? "Mandatory critic review now; investigator is forbidden until that review completes. " : "")+DELEGATION_ROLE_GUIDE};
 input.properties.background={type:"boolean",enum:[false],description:"Serial foreground execution only."};
 if(!coordinator)delete input.properties.model;
 // A mandatory critic cannot resume a non-critic child: CHILD_AGENT_MISMATCH would reject that exact call,
 // and resuming would mean continuing the OLD agent's work anyway, not a critic review of it. Only offer the
 // resume lock when the existing child is itself already the critic session being continued.
 const resumable=state.child && childState?.callingAgent && (!criticMandatory || childState.callingAgent==="watoom-critic");
 if(resumable) {
  input.properties.sessionID={type:"string",enum:[state.child],description:"Resume this existing child; never use the parent sessionID."};
  input.required=[...new Set([...(input.required || []),"sessionID"])];
 } else {
  // A new child has no resume identity. Do not expose an unconstrained string
  // that invites the model to copy its own session ID into this field. A COMPLETED child is
  // deliberately not offered for resume either: resuming replays its whole history into the model
  // on every later call, so context grows and every package drags in stale detail. Only a
  // running or failed child (state.child above) is resumed; finished work starts a fresh child.
  delete input.properties.sessionID;
  input.required=(input.required || []).filter(name=>name!=="sessionID");
 }
 input.additionalProperties=false;
 event.tools.subagent={...tool,input,description:"Serial bounded native delegation. Allowed agent: "+allowed.join(", ")+". "+
  (resumable ? "Continue existing child "+state.child+" only." : criticMandatory && state.child ? "Mandatory critic review: start a FRESH critic child (omit sessionID); the prior non-critic child "+state.child+" cannot be resumed under a different agent." : "Omit sessionID for new work; resume only a real child ID with its recorded agent.")+
  " Never use parent "+event.sessionID+" as sessionID. Children may consult one foreground critic only; critic cannot delegate. "+DELEGATION_ROLE_GUIDE};
}
export function criticOnlyRequest(body,state,agent) {
 if(agent!=="watoom-workflow" || gate(state,true)!=="critic")return body;
 const tool=body.tools?.find(t=>t.type==="function" && t.function?.name==="subagent");
 if(!tool)return body; // Never restore a tool disabled by native lifecycle/loop controls.
 const original=tool.function.parameters?.properties || {};
 const parameters={type:"object",additionalProperties:false,properties:{agent:{type:"string",const:"watoom-critic",enum:["watoom-critic"]},description:original.description || {type:"string"},prompt:original.prompt || {type:"string"},background:{type:"boolean",const:false,enum:[false]}},required:["agent","description","prompt","background"]};
 const next={...body,tools:[{...tool,function:{...tool.function,parameters,strict:true}}],tool_choice:{type:"function",function:{name:"subagent"}},parallel_tool_calls:false};
 delete next.response_format;
 return next;
}

export function gate(state, coordinator) {
  if (coordinator && state.child) return "waiting-child";
  if (state.pendingVisual) return "vision";
  if (coordinator && state.errors >= 2) return "critic";
  if (coordinator && spent(state)) return "handoff";
  if (state.pendingVisual) return "vision";
  if(!coordinator && state.errors>=2)return "child-critic";
}
// Reject direct Blender startup in the application cgroup; even inventory opens
// can decode large textures/geometry. This is routing protection, not a shell sandbox.
export function appBlenderLaunch(command) {
  const value=String(command || "").replace(/\\\r?\n/g, "");
  const executable=String.raw`(?:"[^"\n]*\/blender(?:[0-9.-]+)?"|'[^'\n]*\/blender(?:[0-9.-]+)?'|(?:[^\s;&|]*\/)?blender(?:[0-9.-]+)?)`;
  const prefix=String.raw`(?:(?:exec|command)\s+|(?:timeout|nice|env)\s+[^;&|\n]*?\s+|[A-Za-z_][A-Za-z0-9_]*=(?:"[^"]*"|'[^']*'|[^\s;&|]+)\s+)*`;
  if(new RegExp(String.raw`(?:^|[;&|\n]\s*|\$\()\s*`+prefix+executable+String.raw`(?:\s|$)`,"i").test(value))return true;
  // Common explicit shell wrappers; inspect their static -c command, never execute it.
  const nested=/(?:^|[;&|]\s*)\s*(?:bash|sh)\s+-(?:l?c|cl)\s+(['"])([\s\S]*)\1\s*$/.exec(value);
  return Boolean(nested && nested[2]!==value && appBlenderLaunch(nested[2]));
}
export function workerProtocolPath(value) {
 return /(?:^|[/\\])(?:worker-requests|rig-worker-requests|asset-capture-requests|esp32-requests)(?:[/\\]|$)/.test(String(value || ""));
}
// 2026-11-09: a builder tried to directly Edit tools/esp32/contract.py under this mount, failed (wrong
// indentation guess from a path-prefix display quirk), then escalated to touch/remount probing before
// discovering -- only from the OS's own "Read-only file system" error -- that /data/github is a readOnly
// hostPath mount (resources.json.j2: every repo under it, not just esp32). The mount already makes any
// write impossible; this just says so up front so an agent never burns calls (or attempts a remount) to
// learn it the hard way. A real bug found here is a finding to report, not something to self-patch.
export function sourceRepoPath(value) {
 return /(?:^|[/\\])data[/\\]github(?:[/\\]|$)/.test(String(value || ""));
}
// 2026-11-04: a builder compacted mid-package, made no further tool calls, then reported an invented
// request_id as QUEUED; the coordinator relayed it and waited for a job that did not exist. The native
// worker tools write <id>.json before they answer, so every request ID a child reports must exist on disk.
export async function unverifiedRequestClaims(text,directory) {
 if(typeof directory!=="string" || !directory.startsWith("/"))return [];
 const ids=new Set([...String(text || "").matchAll(/request(?:[_ -]?id)?[^a-f0-9\n]{0,24}([a-f0-9]{64})(?![a-f0-9])/gi)].map(m=>m[1]));
 const missing=[];
 for(const id of ids) {
  let found=false;
  for(const folder of ["worker-requests","rig-worker-requests","asset-capture-requests","esp32-requests"])
   try{if((await lstat(posix.join(directory,".opencode",folder,id+".json"))).isFile()){found=true;break;}}catch{}
  if(!found)missing.push(id);
 }
 return missing;
}
export function assertWorkerProtocolAccess(name,input) {
 const path=input?.path || input?.filePath || input?.file_path || "";
 if((["write","edit","apply_patch","patch"].includes(name) && (workerProtocolPath(posix.normalize(path)) || workerProtocolPath(input?.patch || input?.patchText))) ||
    (name==="shell" && workerProtocolPath(input?.command) && !shellReadOnly(input?.command)))
  throw Error("WORKER_PROTOCOL_READ_ONLY: native worker request/status files are runtime-owned. Never create, edit, replace or delete them through write/edit/shell. Use the native worker request/status tool; declarative capture-jobs inputs remain writable. Read existing protocol evidence with native read or a permitted read-only shell command. Corruption requires operator reconciliation, never invented IDs or another job.");
 if((["write","edit","apply_patch","patch"].includes(name) && (sourceRepoPath(posix.normalize(path)) || sourceRepoPath(input?.patch || input?.patchText))) ||
    (name==="shell" && sourceRepoPath(input?.command) && !shellReadOnly(input?.command)))
  throw Error("SOURCE_REPO_READ_ONLY: /data/github is mounted read-only for every repo under it; this is a hard mount property, not a permission to work around with another tool, a remount, or a privilege escalation attempt. It is here for reference/context only, and that stays true no matter what the owner answers below -- their reply can never grant a write here; only they, from outside this container, can actually apply anything. If something under it looks wrong (a real bug, a stale value), build the owner a COMPLETE runnable procedure, not just a description of the problem: every full absolute path under /data/github involved (never relative, never a bare filename), the exact current text and exactly what it becomes (a real diff, not a paraphrase), and every follow-up command needed to make it live -- the test to run and its exact invocation, the git add/commit/push, and if this project's own IaC applies it (an ansible-playbook command, a kubectl rollout/restart, a redeploy) the exact command line for that too, in order, so someone who does not already know this codebase could run it top to bottom. Do not stop at a prose report they might not see: call the native question tool with that complete procedure as its text so the owner sees it immediately in their own chat, the same way other questions already reach them there.");
}
export function validateWorkerRequestIdentity(request,filename) {
 const fields=request.operation ? [request.project,request.operation,request.source_fingerprint,request.session_id,request.message_id,request.call_id,...(request.worker_target==="rig-stage" ? ["rig-stage"] : [])] : [request.project,request.job,request.manifest_sha256,request.session_id,request.message_id,request.call_id];
 const expected=createHash("sha256").update(JSON.stringify(fields)).digest("hex");
 if(request.schema!==1 || fields.some(x=>typeof x!=="string" || !x) || request.request_id!==expected || (filename && filename!==expected+".json"))
  throw Error("WORKER_REQUEST_CORRUPTED: native request identity no longer matches its recorded tool call. This job is BLOCKED, not QUEUED. Do not wait, rewrite IDs or submit a duplicate; preserve evidence and request operator reconciliation.");
}

export function appGodotLaunch(command) {
 const s=String(command || "").replace(/\\\r?\n/g,"");
 const executable=String.raw`(?:"[^"\n]*\/godot(?:[0-9.-]+)?"|'[^'\n]*\/godot(?:[0-9.-]+)?'|(?:[^\s;&|]*\/)?godot(?:[0-9.-]+)?)`;
 const prefix=String.raw`(?:(?:exec|command)\s+|(?:timeout|nice|env|xvfb-run)\s+[^;&|\n]*?\s+|[A-Za-z_][A-Za-z0-9_]*=(?:"[^"]*"|'[^']*'|[^\s;&|]+)\s+)*`;
 if(new RegExp(String.raw`(?:^|[;&|\n]\s*|\$\()\s*`+prefix+executable+String.raw`(?:\s|$)`,"i").test(s))return true;
 if(/(?:^|[;&|\n]\s*)\s*flatpak\s+run\s+[^;&|\n]*org\.godotengine\.Godot(?:\s|$)/i.test(s))return true;
 const nested=/(?:^|[;&|]\s*)\s*(?:bash|sh)\s+-(?:l?c|cl)\s+(['"])([\s\S]*)\1\s*$/.exec(s);
 return Boolean(nested && nested[2]!==s && appGodotLaunch(nested[2]));
}

export function godotInspectOnly(command) {
 // Agents habitually write "cd <project> && godot ... 2>&1 | head -30". Those wrappers do not
 // change what Godot executes, so peel them before applying the strict single-command check.
 const s=String(command || "").trim()
  .replace(/^cd\s+(?:"[^"$`]*"|'[^']*'|[^\s;&|`$()<>]+)\s*&&\s*/,"")
  .replace(/\s*\|\s*(?:head|tail)(?:\s+-n)?\s+-?\d+\s*$/,"")
  .replace(/\s+2>&1\s*$/,"");
 if(/[;&|`\n\r]|\$\(/.test(s))return false;
 const simple=/^(?:timeout\s+\d+\s+)?(?:[^\s]+\/)?godot(?:[0-9.-]*)?\s+(.*)$/i.exec(s);
 if(!simple)return false;
 const args=simple[1];
 if(/^(?:--version|--help|-h)$/.test(args.trim()))return true;
 return /(?:^|\s)--check-only(?:\s|$)/.test(args) && /(?:^|\s)(?:--script|-s)\s+[^\s]+\.gd(?:\s|$)/.test(args) && !/\.tscn(?:\s|$)|--(?:editor|import|write-movie|scene|main-loop)(?:\s|=|$)/.test(args);
}

export function assertAllowed(name, input, state, coordinator, existingChildAgent) {
  assertWorkerProtocolAccess(name,input);
  if(name==="shell" && state.pendingExternal && /(?:^|[;&|\s])sleep\s+\d/.test(input?.command || ""))throw Error("EXTERNAL_JOB_PENDING: do independent work or return a concise pending-job handoff. Never occupy the session with sleep/status loops; completion is delivered automatically.");
  if(name==="question" && state.simsConversationalIntake)
    throw new Error("SIMS_CONVERSATIONAL_INTAKE: ask missing questions in ordinary chat and end the turn; the next user chat reply continues the same job. Do not call a blocking question tool.");

  if(name==="shell" && appBlenderLaunch(input?.command))
    throw new Error("EXTERNAL_BLENDER_WORKER_REQUIRED: Blender scene loading, inventory, posing, preparation and rendering must run in the verified external worker (server 4GiB CPU or RIG 8GiB Windows Job Object), never the application shell. Read installed runtime/worker descriptors and submit the supported bounded request; do not retry directly, increase the app memory limit or invent a worker operation.");
  if(name==="shell" && /(?:^|[;&|]\s*|\$\()\s*(?:(?:exec|command)\s+|(?:timeout|nice|env)\s+[^;&|]*?\s+)?(?:[^\s;&|]*\/)?(?:UnrealEditor(?:-Cmd)?|ShaderCompileWorker|UnrealTraceServer)(?:\s|$)/i.test(input?.command || ""))
    throw new Error("EXTERNAL_UNREAL_WORKER_REQUIRED: engine launches, including -version/--help, must use the bounded external engine worker. Read Engine/Build/Build.version for version; investigators inspect files only. Do not retry in the app shell or increase the timeout.");
  if(name==="shell" && /(?:godot|\.tools\/bin\/godot)/i.test(input?.command || "") && /(?:^|\s)--(?:editor|import)(?:\s|$)/.test(input?.command || "") && !/--check-only(?:\s|$)/.test(input?.command || ""))
    throw new Error("EXTERNAL_GODOT_IMPORT_REQUIRED: full project import belongs to native watoom_game_worker operation import, never the2GiB app shell; do not delete caches or repeat an OOM.");
  if(name==="shell" && !/--check-only(?:\s|$)/.test(input?.command || "") && /(?:godot|\.tools\/bin\/godot)/i.test(input?.command || "") && /test_runner\.gd/.test(input?.command || "") && /(?:--headless|--script|\s-s\s)/.test(input?.command || ""))
    throw new Error("EXTERNAL_GODOT_REGRESSION_REQUIRED: full test_runner.gd must run through the bounded external operator game_validation.py worker, never the 2GiB app shell. Save a checkpoint and request the operator receipt; do not repeat an OOM or claim partial tests as PASS.");
  if(name==="shell" && appGodotLaunch(input?.command) && !godotInspectOnly(input?.command))
    throw Error("EXTERNAL_GODOT_WORKER_REQUIRED: every Godot scene, capture and executable script launch must use the bounded external worker. --headless, xvfb-run, timeout and calling it a syntax/load check do not make a scene launch safe in the2GiB app. Only standalone --version/--help or --check-only with --script/-s and no scene/import/project execution are allowed, as ONE command (optional leading cd <dir> &&, trailing 2>&1 or | head/tail -n N; no other chains, pipes or redirects), e.g. godot --headless --check-only -s scripts/main.gd with the shell workdir set to the project. Use the installed native worker operation; unsupported captures require operator worker enrollment, never local rendering.");
  if (name === "subagent") {
    if(!coordinator && input.model!==undefined)throw new Error("CRITIC_MODEL_INHERIT: child critics must inherit the selected model; omit model.");
    if(!coordinator && (!criticCallers.has(state.callingAgent) || input.agent!=="watoom-critic"))
      throw new Error("CRITIC_ONLY_DELEGATION: child agents may call only watoom-critic; critic cannot delegate.");
    if(coordinator && !COORDINATOR_CHILDREN.includes(input.agent))throw new Error("UNKNOWN_CHILD_AGENT: coordinator may start only "+COORDINATOR_CHILDREN.join(", ")+".");
    if(!coordinator && state.criticConsulted)throw new Error("RETURN_TO_COORDINATOR: critic already consulted; do not create another retry chain.");
    if(input.background===true)throw new Error("COORDINATOR_SERIAL: use foreground subagent.");
    if(state.childCall)throw new Error("COORDINATOR_SERIAL: a child is already in flight.");
    const receiptContinuation=coordinator && state.child && input.sessionID===state.child &&
      state.childReceiptRecovery?.sessionID===state.child && state.childReceiptRecovery?.agent===input.agent;
    if (coordinator && input.background === true) throw new Error("COORDINATOR_SERIAL: use foreground subagent with background:false.");
    if(coordinator && state.child && state.simulatedCallBlocked===state.child)throw new Error("NATIVE_CHILD_BLOCKED: repeated simulated tool calls from existing child; report BLOCKED with its ID, no replacement or automatic retry.");
    if(coordinator && state.childReviewBlocked)throw new Error("VISION_CHILD_BLOCKED: two evidence-recovery returns failed; stop delegation and report BLOCKED with the existing child sessionID. Do not restart or replace it.");
    // A mandatory critic (errors>=2) reviewing a non-critic existing child cannot continue that child's
    // sessionID -- CHILD_AGENT_MISMATCH would reject it, and continuing would mean the OLD agent's work
    // anyway, not a review of it. constrainDelegation already drops the resume lock for exactly this case;
    // this gate must recognize the same exception or the only schema-valid call (no sessionID) would be
    // rejected right here, right back into the same deadlock under a different error name.
    const criticMandatory=coordinator && state.errors>=2;
    const childNotResumableForCritic=criticMandatory && existingChildAgent && existingChildAgent!=="watoom-critic";
    if (state.child && input.sessionID !== state.child && !childNotResumableForCritic) throw new Error("COORDINATOR_CHILD_PENDING: continue existing sessionID "+state.child+"; never duplicate it.");
    if (coordinator && state.errors >= 2 && input.agent !== "watoom-critic" && !receiptContinuation) throw new Error("COORDINATOR_CRITIC_REQUIRED: call watoom-critic before another repair attempt.");
    if (coordinator && input.agent === "watoom-critic" && (state.criticEscalations || 0) >= CRITIC_ESCALATION_CAP && !receiptContinuation)
      throw new Error("CRITIC_ESCALATION_BOUND: critic consulted "+state.criticEscalations+" times; stop calling tools, report BLOCKED with exact evidence to the owner and end the turn. The next prompt re-enables one critic review.");
    return;
  }
  if(state.callingAgent==="watoom-critic" && !["read","glob","grep","skill","websearch","question","shell","watoom_skill_search","watoom_memory_recall"].includes(name))
    throw new Error("CRITIC_READ_ONLY: inspect evidence using read/search or owner-approved diagnostic shell; do not modify files or execute repairs.");
  if(readOnlyRoles.has(state.callingAgent) && name==="watoom_specialist_run" && input?.capability!=="asset.search")
    throw new Error("READ_ONLY_PIPELINE: inspect existing receipts or use asset.search; generation, indexing, optimization and publication belong to an execution-authorized coordinator/builder.");
  if(readOnlyRoles.has(state.callingAgent) && ["write","edit"].includes(name))
    throw new Error("READ_ONLY_HANDOFF: return findings or matching visual JSON as FINAL; this role cannot write or edit.");
  if(coordinator && name==="write" && !state.pendingVisual && /visual-review[^/]*\.json$/.test(input?.path || "") && !acceptedReceipt(input,state))
    throw new Error("CHILD_RECEIPT_PROVENANCE_REQUIRED: coordinator has not reviewed this image. Continue the existing child with its exact sessionID and request FINAL JSON; never manufacture a parent receipt.");
  if(state.isChild && ["write","edit"].includes(name) && /(?:^|\/)\.opencode\/work\//.test(input?.path || "") &&
     (!(input.path || "").includes("/children/"+state.sessionID+"/") || (input.path || "").split("/").includes("..")))
    throw new Error("COORDINATOR_CHECKPOINT_OWNER: return child findings or write only your children/<sessionID>/ area; coordinator owns canonical work state.");
  if (exempt.has(name) && !gate(state,coordinator)) return;
  if (state.pendingVisual && name === "write" && reviewReceipt(input,state)) return;
  if (state.pendingVisual) {
    if(name==="write" && (state.receiptFailures||0)>=2 && !state.criticConsulted)
      throw new Error("CHILD_ESCALATION_REQUIRED: two invalid visual receipts; consult ONLY watoom-critic once before correcting. "+receiptMismatch(input,state));
    if(name==="write" && (state.receiptFailures||0)>=3 && state.criticConsulted)
      throw new Error("RETURN_TO_COORDINATOR: visual receipt still invalid after critic; return matching JSON as FINAL, no further tool retries. "+receiptMismatch(input,state));
    if(name==="write")throw new Error("VISION_REVIEW_REQUIRED: "+receiptMismatch(input,state)+". Do not delete files, retry unchanged or bypass with OCR.");
    if (name === "read" && state.pendingVisual.additionalReads < 2) {
      if(typeof input?.path==="string" && /\.(?:png|jpe?g|webp|gif|bmp|tiff?)$/i.test(input.path) && input.path!==state.pendingVisual.path) {
        const queued=enqueueReview(state,input.path);
        throw new Error((queued ? "VISION_REVIEW_QUEUED: " : "VISION_REVIEW_REQUIRED: ")+input.path+" is queued for review after the current image. Finish and save the receipt for "+state.pendingVisual.path+" first; the guard then offers the next queued image. One image at a time; every image gets its own review.");
      }
      return;
    }
    throw new Error("VISION_REVIEW_REQUIRED: inspect the actual image with a verified vision model, then write the matching visual-review JSON receipt before further execution. Metadata and cropping are not review.");
  }
  if(!coordinator && state.errors>=2)
    throw new Error(state.criticConsulted ? "RETURN_TO_COORDINATOR: repair failed after critic; return BLOCKED and exact evidence, no more work calls." : "CHILD_ESCALATION_REQUIRED: two failed executions; consult ONLY watoom-critic before another work call.");
  if (coordinator && (state.child || state.errors >= 2 || spent(state))) {
    if (name === "write" && checkpoint(input) && !state.gateCheckpointWritten) return;
    throw new Error("COORDINATOR_HANDOFF_REQUIRED: write at most one checkpoint then call the native subagent tool; use write with verified complete checkpoint content, not an exact-string edit of stale text. Passive-tool retries do not bypass this boundary.");
  }
}
// Persistent, bounded SearXNG query deduplication. Repeated identical searches
// within the same session are flagged after the first occurrence so the model
// can use a different approach instead of looping. The dedup map is stored in
// session state (persisted via opencode.state.updated) and capped to avoid
// unbounded growth.
export function assertSearchDedup(name, input, state) {
  if(name!=="websearch" && name!=="webfetch")return;
  const query=name==="websearch" ? (input?.query || "") : (input?.url || "");
  if(!query)return;
  const key=query.trim().toLowerCase();
  if(!state.searchDedup)state.searchDedup={};
  // Evict oldest entries when cap is reached to keep the map bounded.
  const entries=Object.entries(state.searchDedup);
  if(entries.length>=SEARCH_DEDUP_CAP){
    // Remove the oldest 25% by insertion order (JS objects preserve string-key
    // insertion order). This is a heuristic eviction, not strict LRU.
    const cutoff=Math.floor(SEARCH_DEDUP_CAP*0.25);
    for(const[k]of entries.slice(0,cutoff))delete state.searchDedup[k];
  }
  if(state.searchDedup[key])
    throw new Error("SEARCH_DEDUP: query already executed in this session; use a different query or proceed with existing results. Repeating the same search does not produce new information.");
  state.searchDedup[key]=Date.now();
}
export function requestContainsImage(value,sha256) {
 if(!value || typeof value!=="object")return false;
 if(value.type==="image_url") {
  const url=typeof value.image_url==="string" ? value.image_url : value.image_url?.url;
  if(typeof url==="string" && /^data:image\/[^;]+;base64,/.test(url))return createHash("sha256").update(Buffer.from(url.slice(url.indexOf(",")+1),"base64")).digest("hex")===sha256;
 }
 return Object.values(value).some(x=>Array.isArray(x)?x.some(v=>requestContainsImage(v,sha256)):requestContainsImage(x,sha256));
}

// Extract the byte length of the exact image matching sha256 from a request body.
// Returns 0 if not found. Used as evidence that real image bytes were sent.
export function extractImageBytes(value,sha256) {
  if(!value || typeof value!="object")return 0;
  if(value.type==="image_url") {
   const url=typeof value.image_url==="string" ? value.image_url : value.image_url?.url;
   if(typeof url==="string" && /^data:image\/[^;]+;base64,/.test(url)) {
    const b64=url.slice(url.indexOf(",")+1);
    if(createHash("sha256").update(Buffer.from(b64,"base64")).digest("hex")===sha256)return Buffer.from(b64,"base64").length;
   }
  }
  for(const x of Object.values(value)){const n=Array.isArray(x)?x.reduce((acc,v)=>{const b=extractImageBytes(v,sha256);return b?b:acc;},0):extractImageBytes(x,sha256);if(n)return n;}
  return 0;
}

export function typedToolkitInput(name,input) {
 if(name!=="watoom_specialist_run" || input?.specialistID!=="local-toolkit" || input?.capability!=="asset.search" || !input.payload || typeof input.payload!=="object" || Array.isArray(input.payload) || input.payload.task!==undefined)return input;
 // Canonical local typed discriminator, verified against the installed backend contract.
 return {...input,payload:{...input.payload,task:"asset-search"}};
}
// Only an unambiguous single grep/rg invocation with empty output has exit 1
// as its documented no-match result. Never exempt compound shells or stderr.
export function expectedSearchMiss(name,input,result) {
 if(name!=="shell" || result?.isError===true || result?.metadata?.exit!==1)return false;
 const command=input?.command;
 if(!shellReadOnly(command) || command.includes("|") || !/^(?:(?:\/usr)?\/bin\/)?(?:rg|grep)\s/.test(command.trim()))return false;
 const text=(Array.isArray(result.content)?result.content:[]).map(x=>x.type==="text" ? x.text || "" : "nontext").join("\n").trim();
 return /^(?:Exited with code 1)?$/.test(text);
}
// A top-level worker (builder-style) session whose tools were stripped after two failures is otherwise stuck for good:
// every later step is forced to the BLOCKED report, even after the owner replies or the worker finishes a job. A new
// prompt (owner message or job-completion notice) is the reconciliation point, so it clears the failure state.
// Coordinators keep their own critic-before-repair re-arm (criticEscalations); children are reset by their parent.
export function rearmAfterPrompt(state) {
 if(!state || state.isChild===true || state.callingAgent==="watoom-workflow" || state.callingAgent==="watoom-critic")return false;
 if(!((state.errors||0)>=2 || (state.guardRejections||0)>=2 || state.terminalReport===true || state.lastExecutionError))return false;
 state.errors=0;state.guardRejections=0;state.terminalReport=false;state.criticConsulted=false;state.lastExecutionError=null;state.lastGuardError=null;state.lastChildReviewError=null;
 return true;
}
export function recordToolFailure(state,agent,name,input,message) {
 const discovery=readOnlyRoles.has(agent) && (["read","glob","grep","list","websearch","webfetch"].includes(name) || (name==="shell" && shellReadOnly(input?.command)));
 state.lastExecutionError={tool:name,message,kind:discovery ? "discovery" : "execution"};
 state.errors=Math.min((state.errors || 0)+1,GUARD_REJECTION_CAP);
 if(agent!=="watoom-workflow" && state.criticConsulted)state.errors=Math.min(Math.max(2,state.errors),GUARD_REJECTION_CAP);
}
export function findingsHandoff(state) {
 // Reporting evidence grants no execution authority and never satisfies visual
 // or permission/provenance gates. Repairs retain their existing BLOCKED schema.
 return readOnlyRoles.has(state.callingAgent) && state.readEvidence?.length>0
   && !state.pendingVisual && !state.guardRejections && !state.lastGuardError && !state.lastChildReviewError;
}
export function terminalSchema(state,sessionID) {
 const v=state.pendingVisual;
 if(v?.presentedBy)return reviewSchema(v);
 if(findingsHandoff(state))return {
  type:"object",additionalProperties:false,
  required:["result","session_id","findings","evidence","limitations","blocker","next_action"],
  properties:{
   result:{type:"string",enum:["PARTIAL","BLOCKED"]},
   session_id:{const:sessionID},
   findings:{type:"string"},
   evidence:{type:"array",items:{type:"string",enum:state.readEvidence},minItems:1},
   limitations:{type:"array",items:{type:"string"},minItems:1},
   blocker:{const:state.lastExecutionError?.message || "Tool discovery stopped; report only verified evidence."},
   next_action:{type:"string"}
  }
 };

 return {type:"object",additionalProperties:false,required:["result","session_id","blocker"],properties:{result:{const:"BLOCKED"},session_id:{const:sessionID},blocker:{const:state.lastChildReviewError || (v && !v.presentedBy ? "VISION_MODEL_REQUIRED: exact image presentation is not verified; use a configured verified vision model before pixel review. No model=null receipt or invented observations." : null) || state.lastExecutionError?.message || state.lastGuardError || "Native execution is unavailable at the current guarded boundary; return to the existing coordinator."}}};
}

// One-use operator-authorized recovery for an existing blocked native critic.
// Never treats failed XML as completion; native subagent must return a verdict.
// Grants are data (options.criticRecoveryGrants): the grant names its sessions, and an
// optional expiresAt bounds it. After a consumed grant, only a follow-up grant whose
// afterNativeErrorOf names that single nonce, recorded as a native subagent error, applies.
export function criticRecovery(state,parentID,options,childState,now=Date.now()) {
 const child=state.child;
 if(state.simulatedCallBlocked!==child ||
    (state.simulatedCallAttempts?.[child] || 0)<2 ||
    state.childCall || childState?.callingAgent!=="watoom-critic" ||
    childState?.pendingVisual || state.criticRecoveryInFlight)return;
 const nonce=/^[a-f0-9]{64}$/;
 const consumed=state.consumedCriticRecoveryGrants||[];
 const history=Array.isArray(state.criticRecoveryHistory) ? state.criticRecoveryHistory : [];
 const followsNativeError=g=>nonce.test(g.afterNativeErrorOf||"") && consumed.includes(g.afterNativeErrorOf) &&
   history.length===1 && history[0]?.child===child && history[0]?.nonce===g.afterNativeErrorOf &&
   history[0]?.status==="native-error" && history[0]?.accepted===false && history[0]?.error==="NATIVE_SUBAGENT_ERROR";
 return (Array.isArray(options?.criticRecoveryGrants) ? options.criticRecoveryGrants : [])
   .find(g=>g.parentSessionID===parentID && g.childSessionID===child &&
     g.agent==="watoom-critic" && nonce.test(g.nonce||"") && !consumed.includes(g.nonce) &&
     (g.expiresAt===undefined || Date.parse(g.expiresAt)>now) &&
     (!state.criticRecoveryConsumed || followsNativeError(g)));
}
export function validRecoveredCriticVerdict(text) {
 // Whole-response JSON, not prose, quoted instructions, Markdown or tool-call XML.
 if(typeof text!=="string" || text.length<60 || text.length>16384 ||
    /<tool_call|<function[=>]/i.test(text))return false;
 let v;
 try { v=JSON.parse(text.trim()); } catch { return false; }
 if(!v || typeof v!=="object" || Array.isArray(v))return false;
 if(Object.keys(v).sort().join(",")!=="decision,evidence,findings")return false;
 // BLOCKED is a report of failure, not a completed critic review.
 if(v.decision!=="PROCEED" && v.decision!=="REVISE")return false;
 if(!Array.isArray(v.findings) || v.findings.length<1 || v.findings.length>12 ||
    v.findings.some(x=>typeof x!=="string" || x.trim().length<15 || x.length>1000))return false;
 if(!Array.isArray(v.evidence) || v.evidence.length<1 || v.evidence.length>12 ||
    v.evidence.some(x=>typeof x!=="string" || x.trim().length<15 || x.length>1000))return false;
 // A schema check is not an independent verification of the factual claims.
 return true;
}

export function toolRecovery(state,sessionID,options,childState) {
 if(state.simulatedCallBlocked!==state.child || childState?.pendingVisual || childState?.errors || !String(childState?.lastGuardError || "").startsWith("EXTERNAL_GODOT_REGRESSION_REQUIRED:"))return;
 return (options?.toolRecoveryGrants || []).find(g=>g.parentSessionID===sessionID && g.childSessionID===state.child && /^[a-f0-9]{64}$/.test(g.nonce || "") && !(state.consumedToolRecoveryGrants || []).includes(g.nonce));
}


// Implementation roles that may run the bounded engine/capture/ESP32 workers; read-only roles return findings.
const workerRoles=new Set(["watoom-workflow","watoom-builder","watoom-developer","watoom-3d-modeller","watoom-automation-expert","watoom-integration-expert"]);
const workerOperations=new Set(["regression","import","capture","capture-scene","capture-p7","poo-vfx-inspect","poo-vfx-export","lmb-qualify","unreal-export","blender","terrain-export","godot-game"]);
export async function gameSourceManifest(project) {
 const rows=[];
 async function walk(dir,relative="") {
  for(const entry of await readdir(dir,{withFileTypes:true})) {
   if(entry.isDirectory() && [".godot",".opencode",".git","magpie-final"].includes(entry.name))continue;
   const name=relative ? relative+"/"+entry.name : entry.name,path=posix.join(dir,entry.name);
   if(entry.isSymbolicLink())throw Error("GAME_WORKER_SOURCE_SYMLINK: source must be contained regular files");
   if(entry.isDirectory())await walk(path,name);
   else if(entry.isFile() && !entry.name.endsWith(".import")) {
    const info=await stat(path,{bigint:true});rows.push([name,String(info.size),String(info.mtimeNs)]);
    if(rows.length>20000)throw Error("GAME_WORKER_SOURCE_LIMIT: request operator review");
   }
  }
 }
 await walk(project);
 for(const name of [".opencode/validation/p6-env-capture/p6_env_capture.gd",".opencode/validation/p6-env-capture/p6_env_capture.tscn",".opencode/validation/p7-poo-capture/p7_poo_capture.gd",".opencode/validation/p7-poo-capture/p7_poo_capture.tscn"]) {
  try{const path=posix.join(project,name);if(await realpath(posix.dirname(path))!==posix.dirname(path))throw Error("GAME_WORKER_SOURCE_SYMLINK: indirect capture parent");const info=await lstat(path,{bigint:true});if(!info.isFile() || info.isSymbolicLink())throw Error("Unsafe capture source");rows.push([name,String(info.size),String(info.mtimeNs)]);}catch(e){if(e.code!=="ENOENT")throw e;}
 }
 rows.push([".watoom-worker-contract","cache-mount-v1","0"]);
 rows.sort((a,b)=>Buffer.compare(Buffer.from(a[0]),Buffer.from(b[0])));
 return rows;
}
export async function gameSourceFingerprint(project) {
 return createHash("sha256").update(JSON.stringify(await gameSourceManifest(project))).digest("hex");
}
export function validateGameWorkerInput(input,agent) {
 if(!workerRoles.has(agent))throw Error("GAME_WORKER_ROLE_DENIED: read-only roles return findings to the coordinator");
 if(typeof input?.job==="string" && /^[a-f0-9]{64}$/.test(input.job))throw Error("GAME_WORKER_JOB_IS_REQUEST_ID: job is the folder name you chose under .opencode/<operation>-jobs/ (for example test-run3), never the 64-hex request_id; use the same job name for request and status.");
 if(!input || Object.keys(input).some(k=>!["action","operation","job"].includes(k)) || !["request","status"].includes(input.action) || !workerOperations.has(input.operation) || typeof input.job!=="string" || !/^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$/.test(input.job))throw Error("GAME_WORKER_INVALID_REQUEST");
}
async function trustedGameStatus(path,request) {
 try {
  const info=await lstat(path);if(!info.isFile() || info.isSymbolicLink() || info.uid!==0 || (info.mode&0o022) || info.size>262144)throw Error("Untrusted worker status");
  const value=JSON.parse(await readFile(path,"utf8"));
  if((value.job!==undefined && value.job!==request.job) || value.request_id!==request.request_id || value.project!==request.project || value.operation!==request.operation || value.source_fingerprint!==request.source_fingerprint)throw Error("Worker status identity mismatch");
  return value;
 }catch(e){if(e.code==="ENOENT")return {status:"QUEUED",request_id:request.request_id,operation:request.operation,project:request.project,source_fingerprint:request.source_fingerprint};throw e;}
}
export async function captureSpecFingerprint(project,job) {
 const path=posix.join(project,".opencode/capture-jobs",job,"request.json");
 if(await realpath(path)!==path || (await stat(path)).size>32768)throw Error("CAPTURE_MANIFEST_PATH");
 const raw=await readFile(path),v=JSON.parse(raw);const rel=s=>typeof s==="string" && /^[A-Za-z0-9_./-]+$/.test(s) && !s.startsWith("/") && !s.split("/").includes("..") && posix.normalize(s)===s;
 if(!["images,inputs,output_directory,scene,schema","deadline_sec,images,inputs,output_directory,scene,schema"].includes(Object.keys(v).sort().join(",")) || (v.deadline_sec!==undefined && !(Number.isInteger(v.deadline_sec) && v.deadline_sec>=60 && v.deadline_sec<=1080)) || v.schema!==1 || !rel(v.scene) || !v.scene.endsWith(".tscn") || !rel(v.output_directory) || !v.output_directory.startsWith(".opencode/captures/") || !Array.isArray(v.inputs) || v.inputs.length<1 || v.inputs.length>128 || new Set(v.inputs).size!==v.inputs.length || !v.inputs.includes(v.scene) || !Array.isArray(v.images) || v.images.length<1 || v.images.length>32 || new Set(v.images).size!==v.images.length || v.images.some(n=>typeof n!=="string" || !/^[A-Za-z0-9][A-Za-z0-9_-]{0,100}\.png$/.test(n)))throw Error("CAPTURE_MANIFEST_INVALID");
 const rows=[];
 for(const name of [...v.inputs].sort()) {const file=posix.join(project,name);if(!rel(name) || await realpath(file)!==file || !(await stat(file)).isFile() || (await stat(file)).size>67108864)throw Error("CAPTURE_INPUT_PATH");rows.push([name,createHash("sha256").update(await readFile(file)).digest("hex")]);}
 return createHash("sha256").update(JSON.stringify([createHash("sha256").update(raw).digest("hex"),rows])).digest("hex");
}

// Unreal export binds only to the manifest bytes: it reads a purchased pack, not the game source. The root dispatcher
// (unreal_export_spec.py) validates every field and fails the request with a field-named reason; this checks only that
// the manifest is a direct regular JSON file so a typo is reported before anything is queued.
// Blender jobs (blender_job_spec.py) are bound the same way, to their manifest bytes.
async function manifestFingerprint(project,folder,base,label,job) {
 const path=posix.join(project,".opencode",folder,job,"request.json");
 if(await realpath(path).catch(()=>"")!==path)throw Error(label+"_MANIFEST_MISSING: write .opencode/"+folder+"/"+job+"/request.json first (a regular file, not a link)");
 if((await stat(path)).size>16384)throw Error(label+"_MANIFEST_INVALID: request.json must be at most 16 KiB");
 const raw=await readFile(path);let v;
 try{v=JSON.parse(raw);}catch(e){throw Error(label+"_MANIFEST_INVALID: request.json is not valid JSON: "+e.message);}
 if(!v || typeof v!=="object" || Array.isArray(v) || v.schema!==1)throw Error(label+"_MANIFEST_INVALID: request.json must be an object with schema:1");
 return createHash("sha256").update(JSON.stringify([base,createHash("sha256").update(raw).digest("hex")])).digest("hex");
}
export const unrealExportSpecFingerprint=(project,job)=>manifestFingerprint(project,"unreal-export-jobs","unreal-export-v1","UNREAL_EXPORT",job);
export const blenderJobFingerprint=(project,job)=>manifestFingerprint(project,"blender-jobs","blender-job-v1","BLENDER_JOB",job);
// terrain-export binds only to the manifest bytes, the same as unreal-export: it stages an existing project-local
// Unreal project under .opencode/tmp/, not the Godot game source. terrain_spec.py validates every field.
export const terrainExportSpecFingerprint=(project,job)=>manifestFingerprint(project,"terrain-jobs","terrain-export-v1","TERRAIN_EXPORT",job);
// godot-game (typed watoom-godot-game steps on Bazzite) binds to its manifest bytes too; godot_game_spec.py validates every field and the staged copy under .opencode/tmp/.
export const godotGameSpecFingerprint=(project,job)=>manifestFingerprint(project,"godot-game-jobs","godot-game-job-v1","GODOT_GAME",job);

// The check is on the calling session's own directory, not the worker allowlist; say so,
// because models otherwise misread the denial as a project-enrolment problem.
export function gameProjectDeniedMessage(directory) {
 const where=typeof directory==="string" && directory.length<=512 ? JSON.stringify(directory) : "unknown";
 return "GAME_WORKER_PROJECT_DENIED: this session's working directory is "+where+", not a game project folder /data/ai/projects/games/<project>. "+
  "Game worker requests (import, regression, capture) are only accepted from a session opened inside the game project; child sessions inherit the parent's directory. "+
  "This is not a worker allowlist or enrolment problem, and the operator cannot fix it by enrolling the project. "+
  "Stop and ask the user to select the game project in WatooM-Code and continue in a session there.";
}

// Where each operation leaves its result, so the next-step text never sends the model to a folder that does not exist.
export function gameWorkerResultWhere(operation,job) {
 const where={"godot-game":".opencode/godot-game-out/"+job+"/result.json (failure_reason and each step's log tail)","unreal-export":"the status above (worker_result.failure_reason and, when the export ran, errors) and any files already copied to .opencode/unreal-exports/"+job+"/","blender":".opencode/blender-out/"+job+"/result.json (traceback, errors, log_tail)","terrain-export":"the status above (worker_result.failure_reason and log tail) and the output/ folder of your staged uproject_dir","capture-scene":"the status above (worker_result.failure_reason) and .opencode/captures/"};
 return "Read the result: "+(where[operation] || "the status above (worker_result.failure_reason and its log tail)")+".";
}
// The rig Godot editor MCP (watoom-godot_*) needs a running editor plugin; a watoom-godot-game project (gg_ui.json/gg_project.json) is built and checked only through watoom_game_worker godot-game jobs.
export async function godotEditorToolDenied(directory) {
 if(typeof directory!=="string" || !/^\/data\/ai\/projects\/games\/[^/]+$/.test(directory))return null;
 for(const f of ["gg_ui.json","gg_project.json"])if(await stat(posix.join(directory,f)).catch(()=>null))
  return "GODOT_EDITOR_TOOL_NOT_FOR_THIS_PROJECT: this is a watoom-godot-game project, so the Godot editor tools (watoom-godot_*) are not used: no editor is running for it and they fail with ECONNREFUSED. Run, test and screenshot only through watoom_game_worker operation godot-game jobs (see the watoom-godot-game skill).";
 return null;
}
// What the model should do next for each worker status. A finished job name is never re-run, and a failed job is a result to fix, not a blocker.
export function gameWorkerGuidance(status,request,sessionID,input) {
 const out={own_session:request.session_id===sessionID};
 const ageMin=Number.isFinite(request.created_at) ? Math.round((Date.now()-request.created_at)/60000) : undefined;
 if(ageMin!==undefined)out.age_min=ageMin;
 if(!out.own_session)out.warning="This job was submitted by another session, not this one. Do not wait on it or build on it: submit your own job under a NEW name for the work you are doing now.";
 const done=["FAILED","FAIL","STALE_REQUEST","STALE_RESULT","RECONCILIATION_REQUIRED","TIMED_OUT"];
 if(done.includes(status))out.next="This job name is FINISHED and can never run again. "+gameWorkerResultWhere(input.operation,request.job)+" Fix the cause in your project or manifest, then submit under a NEW job name (and a new scratch project_dir where the operation uses one). A failed job is a result to fix, not a blocker: do not finish with BLOCKED.";
 else if(["QUEUED","WAITING_FOR_HEADROOM"].includes(status))out.next=(ageMin>30 ? "Queued "+ageMin+" min: the worker is probably not starting it. Do not resubmit; report this job name and its age to the operator and continue independent edits." : "Waiting for the worker. Do not resubmit, do not poll in a loop; continue independent edits (it notifies this session when done).");
 else if(status==="RUNNING")out.next="Running. Do not poll in a loop or resubmit; continue independent edits and read the result when it arrives.";
 else if(status==="PASS" || status==="COMPLETED")out.next="Passed. Read the receipt, then go on to the next step of your plan (a new job name for each further run).";
 return out;
}
export async function executeGameWorker(ctx,input,context,target="server") {
 if(target==="rig-stage" && !["import","regression","capture","capture-p7","capture-scene"].includes(input.operation))throw Error("RIG_GAME_OPERATION_UNSUPPORTED: use the existing server worker for this specialized operation");
 validateGameWorkerInput(input,context.agent);
 const info=unpack(await ctx.session.get({sessionID:context.sessionID}));
 const directory=info?.location?.directory;
 if(typeof directory!=="string" || !/^\/data\/ai\/projects\/games\/[^/]+$/.test(directory) || await realpath(directory).catch(()=>"")!==directory)throw Error(gameProjectDeniedMessage(directory));
 if(!/^[A-Za-z0-9_-]+$/.test(context.sessionID) || !/^[A-Za-z0-9_-]+$/.test(context.messageID) || !/^[A-Za-z0-9_-]+$/.test(context.id))throw Error("GAME_WORKER_CONTEXT_INVALID");
 if(["regression","import","capture","capture-scene","capture-p7"].includes(input.operation) && target!=="rig-stage" && (await stat(posix.join(directory,"gg_ui.json")).catch(()=>null) || await stat(posix.join(directory,"gg_project.json")).catch(()=>null)))
  throw Error("GAME_WORKER_WRONG_OPERATION: this project has gg_ui.json/gg_project.json, so it is a watoom-godot-game project. Use operation godot-game with .opencode/godot-game-jobs/<job>/request.json (tests: gg_ui.py test, screenshots: gg_ui.py shot). regression/import/capture/capture-scene are for the legacy projects and would only sit queued.");
 const folder=posix.join(directory,target==="rig-stage" ? ".opencode/rig-worker-requests" : ".opencode/worker-requests");
 await mkdir(folder,{recursive:true});if(await realpath(folder)!==folder)throw Error("GAME_WORKER_REQUEST_PATH_DENIED");
 // status never needs the source fingerprint (the request lookup below ignores it for status): a walk or manifest error there must not count as a tool failure
 const needFp=input.action!=="status" || target==="rig-stage";
 const baseFingerprint=needFp ? await gameSourceFingerprint(directory) : null;
 const source_fingerprint=!needFp ? null : input.operation==="capture-scene" ? createHash("sha256").update(JSON.stringify([baseFingerprint,await captureSpecFingerprint(directory,input.job)])).digest("hex") : input.operation==="unreal-export" ? await unrealExportSpecFingerprint(directory,input.job) : input.operation==="blender" ? await blenderJobFingerprint(directory,input.job) : input.operation==="terrain-export" ? await terrainExportSpecFingerprint(directory,input.job) : input.operation==="godot-game" ? await godotGameSpecFingerprint(directory,input.job) : baseFingerprint;
 const existing=[];
 for(const name of await readdir(folder)) {
  if(!/^[a-f0-9]{64}\.json$/.test(name))continue;
  const path=posix.join(folder,name),f=await lstat(path);if(!f.isFile() || f.isSymbolicLink() || f.size>16384)continue;
  try{const r=JSON.parse(await readFile(path,"utf8"));if(r.project===directory && r.operation===input.operation && r.job===input.job && (target==="rig-stage" || input.action==="status" || r.source_fingerprint===source_fingerprint))existing.push(r);}catch{}
 }
 for(const r of existing) { validateWorkerRequestIdentity(r,r.request_id+".json"); const onDisk=JSON.parse(await readFile(posix.join(folder,r.request_id+".json"),"utf8")); validateWorkerRequestIdentity(onDisk,r.request_id+".json"); }
 existing.sort((a,b)=>b.created_at-a.created_at);
 let request=existing[0];
 if(!request && input.action==="status")throw Error("GAME_WORKER_REQUEST_NOT_FOUND: retain the original stable job");
 if(!request) {
  const request_id=createHash("sha256").update(JSON.stringify([directory,input.operation,source_fingerprint,context.sessionID,context.messageID,context.id,...(target==="rig-stage" ? ["rig-stage"] : [])])).digest("hex");
  request={schema:1,...(target==="rig-stage" ? {worker_target:target} : {}),request_id,project:directory,operation:input.operation,job:input.job,source_fingerprint,session_id:context.sessionID,message_id:context.messageID,call_id:context.id,agent:context.agent,created_at:Date.now()};
  await writeFile(posix.join(folder,request_id+".json"),JSON.stringify(request,null,2),{flag:"wx",mode:0o644});
 }
 validateWorkerRequestIdentity(request,request.request_id+".json");
 const value=await trustedGameStatus(posix.join(folder,request.request_id+".status.json"),request);
 const guide=gameWorkerGuidance(value.status,request,context.sessionID,input);
 return {content:JSON.stringify({...value,...guide,...(target==="rig-stage" ? {job:input.job,worker_target:target,inputs_frozen:value.inputs_frozen===true,source_matches:request.source_fingerprint===source_fingerprint} : {}),note:target==="rig-stage" ? "Background RIG job registered. Continue independent work; do not wait or poll in a loop. Keep this stable job identity. Do not change its source inputs until inputs_frozen:true. Completion is durably queued to this same coordinator; only accept matching source revisions and review actual pixels. A paused RIG retains the queue." : "Request admission is not execution or PASS. Server worker publishes the actual receipt and notifies this existing coordinator; do not poll rapidly or run tests in the app."}),metadata:{request_id:request.request_id,project:directory,operation:input.operation,source_fingerprint:request.source_fingerprint,job:request.job,status:value.status}};
}

export function validateAssetCaptureInput(input,agent) {
 if(!workerRoles.has(agent))throw Error("ASSET_CAPTURE_ROLE_DENIED");
 if(!input || Object.keys(input).some(k=>!["action","job"].includes(k)) || !["request","status"].includes(input.action) || typeof input.job!=="string" || !/^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$/.test(input.job))throw Error("ASSET_CAPTURE_INVALID_REQUEST");
}
export function assetCaptureProject(path,stageProjects=[]) {return path==="/data/ai/projects/images" || (Array.isArray(stageProjects) && stageProjects.includes(path) && /^\/data\/ai\/projects\/games\/[^/]+$/.test(path));}
export async function executeAssetCapture(ctx,input,context) {
 validateAssetCaptureInput(input,context.agent);
 const info=unpack(await ctx.session.get({sessionID:context.sessionID})),project=info?.location?.directory;
 if(!assetCaptureProject(project,ctx.options?.rigAsyncStage===true ? ctx.options.rigGameProjects : []))throw Error("ASSET_CAPTURE_PROJECT_DENIED: native capture requires the session registered project /data/ai/projects/images; writing files there or changing shell cwd does not change session project scope. No capture request was registered.");
 if(await realpath(project)!==project)throw Error("ASSET_CAPTURE_PROJECT_DENIED: registered capture project is not its canonical filesystem path. No capture request was registered; operator inspection required.");
 for(const k of ["sessionID","messageID","id"])if(!/^[A-Za-z0-9_-]{1,128}$/.test(context[k] || ""))throw Error("ASSET_CAPTURE_CONTEXT_INVALID");
 const folder=posix.join(project,".opencode/asset-capture-requests");await mkdir(folder,{recursive:true});if(await realpath(folder)!==folder)throw Error("ASSET_CAPTURE_INDIRECT_DIRECTORY");
 const records=[];
 for(const name of await readdir(folder)) {
  if(!/^[a-f0-9]{64}\.json$/.test(name))continue;
  const file=posix.join(folder,name),st=await lstat(file);if(!st.isFile() || st.isSymbolicLink() || st.size>16384)continue;
  const v=JSON.parse(await readFile(file,"utf8"));if(v.project===project && v.job===input.job)records.push(v);
 }
 records.sort((a,b)=>b.created_at-a.created_at);let request=records[0];
 if(!request && input.action==="status")throw Error("ASSET_CAPTURE_REQUEST_NOT_FOUND");
 if(input.action==="request") {
  const file=posix.join(project,".opencode/capture-jobs",input.job,"request.json");
  if(await realpath(posix.dirname(file))!==posix.dirname(file))throw Error("ASSET_CAPTURE_INDIRECT_MANIFEST");
  const st=await lstat(file);if(!st.isFile() || st.isSymbolicLink() || st.size>65536)throw Error("ASSET_CAPTURE_INVALID_MANIFEST");
  const bytes=await readFile(file),body=JSON.parse(bytes.toString("utf8"));
  if(body.schema!==1 || !["inspect","still","turntable","animation","pose-inspect","pose-prepare"].includes(body.mode) || typeof body.source!=="string" || !/^[a-f0-9]{64}$/.test(body.source_sha256 || ""))throw Error("ASSET_CAPTURE_MANIFEST_SCHEMA");
  const hash=createHash("sha256").update(bytes).digest("hex");
  if(request && request.manifest_sha256!==hash)throw Error("ASSET_CAPTURE_REVISION_CHANGED: use a fresh job");
  if(!request) {
   const request_id=createHash("sha256").update(JSON.stringify([project,input.job,hash,context.sessionID,context.messageID,context.id])).digest("hex");
   request={schema:1,request_id,project,job:input.job,manifest_sha256:hash,session_id:context.sessionID,message_id:context.messageID,call_id:context.id,agent:context.agent,created_at:Date.now()};
   await writeFile(posix.join(folder,request_id+".json"),JSON.stringify(request,null,2),{flag:"wx",mode:0o644});
  }
 }
 validateWorkerRequestIdentity(request,request.request_id+".json");
 let result={status:"QUEUED",request_id:request.request_id,project,job:request.job,manifest_sha256:request.manifest_sha256};
 try {
  const file=posix.join(folder,request.request_id+".status.json"),st=await lstat(file);
  if(!st.isFile() || st.isSymbolicLink() || st.uid!==0 || (st.mode&0o022) || st.size>262144)throw Error("ASSET_CAPTURE_UNTRUSTED_STATUS");
  const value=JSON.parse(await readFile(file,"utf8"));if(["request_id","project","job","manifest_sha256"].some(k=>value[k]!==request[k]))throw Error("ASSET_CAPTURE_STATUS_IDENTITY_MISMATCH");result=value;
 }catch(e){if(e.code!=="ENOENT")throw e;}
 return {content:JSON.stringify({...result,note:"Background external Blender job. QUEUED/RUNNING/PAUSED is not completion. Record the stable identity and continue independent work; wait only for dependent steps, never poll in a loop. Completion is queued automatically. Keep source inputs unchanged and review actual pixels after the trusted receipt. Never run Blender in the app shell."}),metadata:{request_id:request.request_id,project,job:request.job,manifest_sha256:request.manifest_sha256,status:result.status}};
}

export function validateEsp32Input(input,agent) {
 if(!workerRoles.has(agent))throw Error("ESP32_ROLE_DENIED");
 if(!input || Object.keys(input).some(k=>!["action","job"].includes(k)) || !["request","status"].includes(input.action) || typeof input.job!=="string" || !/^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$/.test(input.job))throw Error("ESP32_INVALID_REQUEST");
}
export function esp32Project(path) {return path==="/data/ai/projects/llm/esp32";}
export async function executeEsp32(ctx,input,context) {
 validateEsp32Input(input,context.agent);
 const info=unpack(await ctx.session.get({sessionID:context.sessionID})),project=info?.location?.directory;
 if(!esp32Project(project) || await realpath(project)!==project)throw Error("ESP32_PROJECT_DENIED");
 for(const k of ["sessionID","messageID","id"])if(!/^[A-Za-z0-9_-]{1,128}$/.test(context[k] || ""))throw Error("ESP32_CONTEXT_INVALID");
 const folder=posix.join(project,".opencode/esp32-requests");await mkdir(folder,{recursive:true});if(await realpath(folder)!==folder)throw Error("ESP32_INDIRECT_DIRECTORY");
 const records=[];
 for(const name of await readdir(folder)) {
  if(!/^[a-f0-9]{64}\.json$/.test(name))continue;
  const file=posix.join(folder,name),st=await lstat(file);if(!st.isFile() || st.isSymbolicLink() || st.size>16384)continue;
  const v=JSON.parse(await readFile(file,"utf8"));if(v.project===project && v.job===input.job)records.push(v);
 }
 records.sort((a,b)=>b.created_at-a.created_at);let request=records[0];
 if(!request && input.action==="status")throw Error("ESP32_REQUEST_NOT_FOUND");
 if(input.action==="request") {
  const file=posix.join(project,".opencode/esp32-jobs",input.job,"request.json");
  if(await realpath(posix.dirname(file))!==posix.dirname(file))throw Error("ESP32_INDIRECT_MANIFEST");
  const st=await lstat(file);if(!st.isFile() || st.isSymbolicLink() || st.size>65536)throw Error("ESP32_INVALID_MANIFEST");
  const bytes=await readFile(file),body=JSON.parse(bytes.toString("utf8"));
  if(body.schema!==1 || !["inventory","build","probe","flash","restore","monitor","serial"].includes(body.operation))throw Error("ESP32_MANIFEST_SCHEMA");
  const hash=createHash("sha256").update(bytes).digest("hex");
  if(request && request.manifest_sha256!==hash)throw Error("ESP32_REVISION_CHANGED: use a fresh job");
  if(!request) {
   const request_id=createHash("sha256").update(JSON.stringify([project,input.job,hash,context.sessionID,context.messageID,context.id])).digest("hex");
   request={schema:1,request_id,project,job:input.job,manifest_sha256:hash,session_id:context.sessionID,message_id:context.messageID,call_id:context.id,agent:context.agent,created_at:Date.now()};
   await writeFile(posix.join(folder,request_id+".json"),JSON.stringify(request,null,2),{flag:"wx",mode:0o644});
  }
 }
 validateWorkerRequestIdentity(request,request.request_id+".json");
 let result={status:"QUEUED",request_id:request.request_id,project,job:request.job,manifest_sha256:request.manifest_sha256};
 try {
  const file=posix.join(folder,request.request_id+".status.json"),st=await lstat(file);
  if(!st.isFile() || st.isSymbolicLink() || st.uid!==0 || (st.mode&0o022) || st.size>262144)throw Error("ESP32_UNTRUSTED_STATUS");
  const value=JSON.parse(await readFile(file,"utf8"));if(["request_id","project","job","manifest_sha256"].some(k=>value[k]!==request[k]))throw Error("ESP32_STATUS_IDENTITY_MISMATCH");result=value;
 }catch(e){if(e.code!=="ENOENT")throw e;}
 return {content:JSON.stringify({...result,note:"Isolated ESP32 worker; USB access requires operator-enrolled identity. QUEUED is not completion. Retain the job identity; review compiler/flash/serial receipts. No direct app-shell device access."}),metadata:{request_id:request.request_id,project,job:request.job,manifest_sha256:request.manifest_sha256,status:result.status}};
}

export async function install(ctx) {
  const shellReadBindings=new Map();
  if(ctx.permission?.hook)await ctx.permission.hook("evaluate",event=>readShellPermission(event,shellReadBindings));
  const queues=new Map();
  const visionModels=new Set(ctx.options?.verifiedVisionModels || []);
  async function transaction(sessionID, change) {
    const prior=queues.get(sessionID) || Promise.resolve();
    const next=prior.catch(()=>{}).then(async()=>{
      const key="session/"+sessionID;
      let state=await ctx.storage.get(key);
      if (!state) {
        const info=unpack(await ctx.session.get({sessionID}));
        state=initial(info?.metadata?.watoomCoordinationSeed);
      }
      if(typeof state.isChild!=="boolean")state.isChild=Boolean(unpack(await ctx.session.get({sessionID}))?.parentID);
      state.sessionID=sessionID;
      const value=await change(state);
      await ctx.storage.set(key,state);
      return value;
    });
    queues.set(sessionID,next);
    try{return await next;}finally{if(queues.get(sessionID)===next)queues.delete(sessionID);}
  }
  await ctx.tool.transform(editor=>{
    editor.add({name:VISUAL_RECEIPT_TOOL,description:"Guard-internal: record the coordinator's independent pixel review receipt. Only offered while an image review is pending; the guard supplies the schema.",options:{codemode:false},input:{type:"object",additionalProperties:true},execute:async()=>({content:"Visual review receipt recorded. Continue the task from where it was before the image was read; this was a side check, not the task result.",metadata:{}})});
    editor.add({name:"watoom_esp32",description:"Request/status for isolated ESP32 firmware build and enrolled USB operations. First write .opencode/esp32-jobs/<job>/request.json in /data/ai/projects/llm/esp32. Fixed inventory, build, probe, flash, restore, bounded monitor and serial text; no arbitrary commands. Explicit board identity and flash authorization required. For build, optional psram ('disabled'|'enabled'|'opi', the real esp32s3 Arduino-core menu values) overrides the profile's qualified PSRAM=disabled default -- compile-only, never touches the physical board. The real chip has 8MiB OPI PSRAM, but 'opi' previously failed its serial hardware startup test during initial qualification (see esp32-development/references/operations.md); a build with it is not itself unsafe, but DO NOT flash or claim PSRAM works until a probe/monitor/flash cycle on real hardware re-confirms boot succeeds -- the existing explicit confirm_flash, physical MAC match and full pre-write backup remain the actual safety net. QUEUED means yield; keep stable job and inspect receipts.",options:{codemode:false},input:{type:"object",properties:{action:{type:"string",enum:["request","status"]},job:{type:"string",pattern:"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$",maxLength:64}},required:["action","job"],additionalProperties:false},execute:(input,context)=>executeEsp32(ctx,input,context)});
    editor.add({name:"watoom_asset_capture",description:"Request/status for the external admitted Blender capture worker (server CPU or RIG OptiX/CPU). First write the declarative .opencode/capture-jobs/<job>/request.json in this project. Supports inspect, still, turntable, existing animation, pose-inspect and pose-prepare (fixed installed helper with declarative auto/recipe/qualified rig-adapter/ts4-retarget plan); no arbitrary scripts or shell. Only coordinator/builder. Retain stable job and inspect the returned actual receipt.",options:{codemode:false},input:{type:"object",properties:{action:{type:"string",enum:["request","status"]},job:{type:"string",pattern:"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$",maxLength:64}},required:["action","job"],additionalProperties:false},execute:(input,context)=>executeAssetCapture(ctx,input,context)});
    if(ctx.options?.rigAsyncStage===true)editor.add({name:"watoom_rig_game_job",description:"STAGE: Queue/status a bounded RIG Godot import, regression, capture or capture-scene against a frozen snapshot. The RIG has a real GPU (unlike the Bazzite worker's software-rendered captures); prefer this for a capture-scene job that timed out there. Returns immediately; continue independent work while queued/running. Completion is delivered automatically to the same coordinator. No polling loops, no duplicate jobs, no live source writes, no arbitrary commands. RIG pause preserves jobs. For capture-scene, write .opencode/capture-jobs/<job>/request.json exactly as for the server worker (schema:1, scene, inputs, output_directory under .opencode/captures/, images, optional deadline_sec 60-1080) before requesting; the manifest is validated the same way, but deadline_sec is a wish against the RIG's own ~850s Windows Job Object budget, not a guarantee. Specialized LMB/VFX operations retain the existing server worker.",options:{codemode:false},input:{type:"object",properties:{action:{type:"string",enum:["request","status"]},operation:{type:"string",enum:["import","regression","capture","capture-p7","capture-scene"]},job:{type:"string",pattern:"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$",maxLength:64}},required:["action","operation","job"],additionalProperties:false},execute:(input,context)=>executeGameWorker(ctx,input,context,"rig-stage")});
    editor.add({name:"watoom_game_worker",description:"Request/status of the bounded external Godot worker for this session's game project. Fixed operations only; no shell or paths. For capture-scene first write .opencode/capture-jobs/<job>/request.json with schema:1, project-relative scene, inputs array including its scene/scripts, output_directory under .opencode/captures/, and expected images PNG basenames; optional integer deadline_sec 60-1080 (default 600) when the scene renders slowly. A WORKER_DEADLINE_EXCEEDED result means raise deadline_sec or render fewer frames, not a script error. For unreal-export (purchased Unreal pack to portable GLB/FBX/TGA) first write .opencode/unreal-export-jobs/<job>/request.json with schema:1, pack (folder name under /data/ai/assets/fab), root (/Game/<Folder>), classes (from SkeletalMesh, AnimSequence, StaticMesh, Texture2D), optional include/exclude name-fragment lists, max_assets 1-2000 (default 400) and memory_gib 2-12 (default 4); files land in .opencode/unreal-exports/<job>/ and the receipt lists them; each job name is used once. For blender (headless pinned Blender, no network, project read-only) write .opencode/blender-jobs/<job>/request.json with schema:1, script (a project .py file, or skill:<skill>/scripts/<file>.py for an installed skill script), optional blend (a project .blend opened first), optional args (strings; {out} becomes the output folder), deadline_sec 60-900 (default 300), memory_gib 2-6 (default 4; skill: scripts need 4); only .opencode/blender-out/<job>/ is writable, and the receipt gives the traceback, the script's last @@JSON@@ line and the output files. Purchased FBX with broken texture paths: script skill:blender-export-pipelines/scripts/fbx_relink_to_glb.py, never byte-patch the FBX. For terrain-export (run an existing, already-staged Unreal project + in-engine Python script on the Bazzite worker -- landscape/terrain-to-GLB extraction, never on the homelab server) first write .opencode/terrain-jobs/<job>/request.json with schema:1, uproject_dir (a project-relative path, must be under .opencode/tmp/ -- a scratch staging area, never live source), uproject_file (bare .uproject filename in that dir), script (bare .py filename in that dir, e.g. one that loads a map, finds the landscape actor and calls AssetExportTask), optional deadline_sec 60-1800 (default 900) and memory_gib 4-16 (default 8); the script must always write .../output/manifest.json with a status field (SUCCESS/PARTIAL/FAILED) even on failure, and whatever output files it produced (e.g. output/terrain.glb) land in the evidence's output/ directory. For godot-game (typed watoom-godot-game skill steps on the Bazzite worker, software GL, no GPU, so only the low-poly and pixel-art styles) first stage a scratch copy of the game under .opencode/tmp/<dir> (empty, or not yet existing, if the first step is gg_ui.py init or gg_project.py init), then write .opencode/godot-game-jobs/<job>/request.json with schema:1, project_dir (that .opencode/tmp/ path), steps (1-12 of {script, sub, args}; script from gg_project.py, gg_style.py, gg_terrain.py, gg_water.py, gg_light.py, gg_catalog.py, gg_scatter.py, gg_census.py, gg_player.py, gg_export.py, gg_ui.py (init, test, shot, overlay-check), gg_assets.py (check), gg_combat.py (init, check, slice, pickups, mp), gg_vfx.py (check) and gg_dungeon.py (catalog-init, catalog-list, catalog-validate, layout, verify) with their documented subcommands; args are plain option tokens, never paths: the worker adds --project itself and refuses --out, --work and the other path flags, including shortened forms), optional deadline_sec 120-1800 (default 900) and memory_gib 3-8 (default 4); the worker runs the verify-loop selftest first and stops at the first failing step; the staged copy comes back under .opencode/godot-game-out/<job>/project/ (files over 100 MB skipped) with a per-step receipt (exit code and log tail); the live project is never changed. Job rules: (1) submit ONLY your own current jobs, with job names that you wrote a request.json for in this session; never poll, wait on or resubmit another session's, another project's or an old job; (2) operation godot-game is the only operation for projects with gg_ui.json/gg_project.json; (3) every attempt gets a NEW job name and a NEW scratch project_dir, a finished job (FAIL/FAILED/STALE/RECONCILIATION) is never re-run; (4) status takes the same job NAME you requested, never the request_id; (5) for an existing project set \"from_project\":true so the worker copies the live project itself (project_dir must not exist yet); an init job (gg_ui.py init / gg_project.py init) may name a project_dir that does not exist yet; (6) a failed job is a result to fix, not a blocker. Legacy capture runs P6 only; never replace P6 for a custom view. Coordinator/builder only. Stable job, automatic receipt delivery; no rapid polling.",options:{codemode:false},input:{type:"object",properties:{action:{type:"string",enum:["request","status"]},operation:{type:"string",enum:["regression","import","capture","capture-scene","capture-p7","poo-vfx-inspect","poo-vfx-export","lmb-qualify","unreal-export","blender","terrain-export","godot-game"]},job:{type:"string",pattern:"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$",maxLength:64}},required:["action","operation","job"],additionalProperties:false},execute:(input,context)=>executeGameWorker(ctx,input,context)});
  });
  await ctx.tool.transform(editor=>{
    for (const entry of editor.list()) { if(entry.name==="subagent")continue; editor.update(entry.id,tool=>{
      const original=tool.execute;
      tool.execute=async(input,context)=>{
        input=typedToolkitInput(entry.name,input);
        if(/^watoom[-_]godot[-_]/.test(entry.name)){const denied=await godotEditorToolDenied(unpack(await ctx.session.get({sessionID:context.sessionID}))?.location?.directory);if(denied)throw Error(denied);}
        const invokeOriginal=async()=>{
          if(entry.name!=="shell")return original(input,context);
          const key=JSON.stringify([context.sessionID,context.messageID,context.id]);
          shellReadBindings.set(key,{agent:context.agent,command:input.command});
          try{return await original(input,context);}finally{shellReadBindings.delete(key);}
        };
        const mirror=async result=>{
          try {const copies=await archiveViewedImage(result,input,context,ctx.options?.imageReviewRoot);if(copies.length)result.metadata={...result.metadata,image_review_copies:copies};}
          catch(error){await ctx.storage.set("image-review-error/"+context.sessionID,{error:String(error),source:input.path || null,time:Date.now()});result.metadata={...result.metadata,image_review_error:String(error)};}
          return result;
        };
        if (!protectedAgents.has(context.agent)) return mirror(await invokeOriginal());
        const coordinator=context.agent==="watoom-workflow";
        const identity=context.messageID+"/"+context.id;
        const denied=await transaction(context.sessionID,state=>{
          state.callingAgent=context.agent;
          try{
            if(entry.name===VISUAL_RECEIPT_TOOL){
              if(!coordinator || !state.pendingVisual)throw new Error("VISION_REVIEW_REQUIRED: "+VISUAL_RECEIPT_TOOL+" is only for the coordinator while an image review is pending.");
              assertAllowed("write",receiptAsWrite(input,state),state,coordinator);
            } else assertAllowed(entry.name,input,state,coordinator);
            assertSearchDedup(entry.name,input,state);
          }catch(error){
            // A newly queued extra image is ordering, not a failed attempt.
            if(String(error.message).startsWith("VISION_REVIEW_QUEUED:"))return String(error.message);
            state.guardRejections=Math.min((state.guardRejections||0)+1,GUARD_REJECTION_CAP);
            if(state.pendingVisual && (entry.name==="write" || entry.name===VISUAL_RECEIPT_TOOL) && !reviewReceipt(entry.name==="write"?input:receiptAsWrite(input,state),state))
              state.receiptFailures=(state.receiptFailures||0)+1;
            state.lastGuardError=String(error.message);
            if(coordinator && state.guardRejections>=2)state.errors=Math.min(Math.max(2,state.errors),GUARD_REJECTION_CAP);
            return String(error.message);
          }
          // Nested Code Mode calls share an outer call ID. Count every actual
          // executor invocation, including identical calls, so loops cannot hide.
          state.calls=[...state.calls,identity+"/"+entry.name].slice(-64);
          if(coordinator && !exempt.has(entry.name) && !checkpoint(input)) DISCOVERY.has(entry.name) ? state.reads=(state.reads || 0)+1 : state.direct++;
          if(state.pendingVisual && entry.name==="read") state.pendingVisual.additionalReads++;
        });
        if(denied)throw new Error(denied);
        try {
          const result=await mirror(await invokeOriginal());
          if((entry.name==="write" || entry.name==="edit") && /\.(?:gd|gdshader|tscn|tres|cs)$/.test(input?.path || input?.filePath || ""))
            withLearnedWarning(result,learnedApiWarnings(String(input.content ?? input.newString ?? input.new_string ?? ""),loadLearnedLessons()));
          await transaction(context.sessionID,state=>{
            if(["watoom_game_worker","watoom_rig_game_job","watoom_asset_capture"].includes(entry.name) && result?.metadata?.request_id)state.pendingExternal=["QUEUED","RUNNING","WAITING_FOR_HEADROOM","PAUSED"].includes(result.metadata.status) ? {request_id:result.metadata.request_id,status:result.metadata.status} : null;
            const failed = !(readOnlyRoles.has(context.agent) && expectedSearchMiss(entry.name,input,result)) && (result?.isError===true || (result?.metadata?.exit !== undefined && result.metadata.exit !== 0));
            if(!failed && entry.name==="read" && readOnlyRoles.has(context.agent) && typeof input?.path==="string")
              state.readEvidence=[...new Set([...(state.readEvidence || []),input.path])].slice(-32);
            if(!failed && entry.name==="skill" && input?.id==="sims")state.simsConversationalIntake=true;
            if(failed)recordToolFailure(state,context.agent,entry.name,input,"Tool returned failure; exit="+result?.metadata?.exit);
            if(coordinator && entry.name==="write" && checkpoint(input) && (spent(state) || state.errors>=2 || state.child))state.gateCheckpointWritten=true;
            const image=imagePart(result);
            if(image) {
              const bytes=Buffer.from(image.uri.slice(image.uri.indexOf(",")+1),"base64");
              const sha256=createHash("sha256").update(bytes).digest("hex");
              if(!state.reviews.some(x=>x.sha256===sha256 && x.reviewVersion===2)) {
                const imagePath=input.path || input.filePath || "tool:"+entry.name;
                if(state.pendingVisual && state.pendingVisual.sha256!==sha256){const e=new Error("VISION_REVIEW_QUEUED: "+imagePath+" is queued for review after the current image. Finish and save the receipt for "+state.pendingVisual.path+" first; the guard then offers the next queued image.");e.queuedPath=imagePath;throw e;}
                if(!state.pendingVisual){state.pendingVisual={path:imagePath,sha256,presentedBy:null,additionalReads:0};state.receiptFailures=0;dequeueReview(state,imagePath);}
              }
            }
            const rin=entry.name===VISUAL_RECEIPT_TOOL ? receiptAsWrite(input,state) : input;
            if((entry.name==="write" || entry.name===VISUAL_RECEIPT_TOOL) && reviewReceipt(rin,state)) {
              state.reviews=[...state.reviews,{reviewVersion:2,semanticStatus:"MODEL_REPORTED_SINGLE_FRAME_ONLY",sha256:state.pendingVisual.sha256,path:rin.path,model:state.pendingVisual.presentedBy,verdict:JSON.parse(rin.content).verdict,receipt:JSON.parse(rin.content)}].slice(-16);
              state.visualResume={path:state.pendingVisual.path,verdict:JSON.parse(rin.content).verdict,defects:JSON.parse(rin.content).defects};
              state.pendingVisual=null;state.receiptFailures=0;
            }
          });
          return result;
        } catch(error) {
          if(error?.queuedPath){await transaction(context.sessionID,state=>{enqueueReview(state,error.queuedPath);});throw error;}
          await transaction(context.sessionID,state=>recordToolFailure(state,context.agent,entry.name,input,String(error.message || error)));
          throw error;
        }
      };
    }); }
  });
  // Keep the native foreground subagent Effect/job lifecycle intact. Observe it
  // through native hooks rather than crossing the Promise-tool executor bridge.
  await ctx.tool.hook("execute.before",async event=>{
    if(event.tool!=="subagent" || !protectedAgents.has(event.agent))return;
    const denied=await transaction(event.sessionID,async state=>{
      state.callingAgent=event.agent;
      try {
      if(event.input.sessionID===event.sessionID)throw new Error("CHILD_SESSION_REQUIRED: sessionID must identify an existing child, never this parent. Use lastHandoff.sessionID with its recorded agent, or omit sessionID only for a genuinely new package.");
      state.childReceiptRecovery=null;
      if(event.agent==="watoom-workflow" && state.child && event.input.sessionID===state.child) {
        const childState=await ctx.storage.get("session/"+state.child);
        if(childState?.pendingVisual && childState.callingAgent===event.input.agent)
          state.childReceiptRecovery={sessionID:state.child,agent:event.input.agent};
      }
      const priorChild=event.input.sessionID ? await ctx.storage.get("session/"+event.input.sessionID) : null;
      // 2026-11-09: constrainDelegation's schema correctly omits sessionID when errors>=2 forces a fresh
      // critic child away from a stuck non-critic one (CHILD_AGENT_MISMATCH would reject resuming it anyway).
      // But that left input.sessionID undefined while state.child was still set to the old child -- and this
      // hook's own COORDINATOR_CRITIC_REQUIRED check below used to fire on that exact mismatch unconditionally,
      // trading one unreachable combination for another. Resolve the existing child's own agent the same way
      // constrainDelegation does, so the execution gate recognizes the identical exception.
      const existingChild=state.child ? (event.input.sessionID===state.child ? priorChild : await ctx.storage.get("session/"+state.child)) : null;
      if(priorChild?.callingAgent && priorChild.callingAgent!==event.input.agent)throw new Error("CHILD_AGENT_MISMATCH: continue the existing child with agent "+priorChild.callingAgent+" and its exact sessionID.");
      const grant=event.input.sessionID===state.child ? recoveryGrant(state,event.sessionID,ctx.options,priorChild) : null;
      if(grant && visionModels.has(priorChild.pendingVisual.presentedBy)) {
        if(event.input.model!==undefined)throw new Error("CRITIC_MODEL_INHERIT: operator evidence recovery cannot override the selected model.");
        state.consumedRecoveryGrants=[...(state.consumedRecoveryGrants || []),grant.nonce];
        state.childReviewBlocked=false;state.childReviewAttempts=1;
      }
      const criticGrant=event.agent==="watoom-workflow" && event.input.sessionID===state.child && event.input.agent==="watoom-critic" && event.input.background!==true && event.input.model===undefined ? criticRecovery(state,event.sessionID,ctx.options,priorChild) : null;
      if(criticGrant) {
        const info=unpack(await ctx.session.get({sessionID:state.child}));
        if(info?.parentID!==event.sessionID)throw new Error("CRITIC_RECOVERY_PARENT_MISMATCH");
        // Reserve only; do not consume authorization until native completion reports.
        state.criticRecoveryInFlight={child:state.child,nonce:criticGrant.nonce,at:Date.now(),call:event.id};
        state.simulatedCallBlocked=null;
        // Preserve the original simulatedCallAttempts count and evidence.
      }
      const toolGrant=event.input.sessionID===state.child ? toolRecovery(state,event.sessionID,ctx.options,priorChild) : null;
      if(toolGrant) {
        const info=unpack(await ctx.session.get({sessionID:state.child}));
        if(info.parentID!==event.sessionID || event.input.model!==undefined)throw new Error("TOOL_RECOVERY_IDENTITY_REQUIRED: exact native child and inherited model required.");
        state.consumedToolRecoveryGrants=[...(state.consumedToolRecoveryGrants || []),toolGrant.nonce];
        state.simulatedCallBlocked=null;state.simulatedCallAttempts[state.child]=0;
        await transaction(state.child,child=>{child.guardRejections=0;child.terminalReport=false;});
      }
      // New work sent to a finished child gets a fresh per-package retry budget. Otherwise its
      // spent counters keep tools stripped and every reply repeats the old blocker unexecuted.
      if(event.agent==="watoom-workflow" && event.input.sessionID && event.input.sessionID!==state.child && priorChild && !priorChild.pendingVisual &&
         ((priorChild.errors || 0)>=2 || (priorChild.guardRejections || 0)>=2 || priorChild.criticConsulted))
        await transaction(event.input.sessionID,child=>{child.errors=0;child.guardRejections=0;child.criticConsulted=false;child.terminalReport=false;child.lastChildReviewError=null;child.readEvidence=[];});
      assertAllowed("subagent",event.input,state,event.agent==="watoom-workflow",existingChild?.callingAgent);
      state.childGuardBaseline=priorChild?.guardRejections || 0;
      if(state.childCall)throw new Error("COORDINATOR_SERIAL: another foreground child call is already in flight.");
      state.childCall=event.id;
      } catch(error) {
        state.guardRejections=Math.min((state.guardRejections||0)+1,GUARD_REJECTION_CAP);
        state.lastGuardError=String(error.message);
        if(event.agent==="watoom-workflow" && state.guardRejections>=2)state.errors=Math.min(Math.max(2,state.errors),GUARD_REJECTION_CAP);
        return String(error.message);
      }
    });
    if(denied)throw new Error(denied);
  });
  await ctx.tool.hook("execute.after",async event=>{
    if(event.tool!=="subagent" || !protectedAgents.has(event.agent))return;
    if(event.status==="error") {
      await transaction(event.sessionID,state=>{
        state.errors=Math.min(state.errors+1,GUARD_REJECTION_CAP);
        if(state.childCall===event.id)state.childCall=null;
        const r=state.criticRecoveryInFlight;
        if(r?.call===event.id) {
          // A native transport error has ambiguous execution status: fail closed.
          state.simulatedCallBlocked=r.child;
          state.criticRecoveryConsumed=true;
          state.consumedCriticRecoveryGrants=[...(state.consumedCriticRecoveryGrants||[]),r.nonce];
          state.criticRecoveryHistory=[...(state.criticRecoveryHistory||[]),{child:r.child,nonce:r.nonce,at:Date.now(),status:"native-error",accepted:false,error:"NATIVE_SUBAGENT_ERROR"}].slice(-8);
          state.criticRecoveryInFlight=null;
        }
      });return;
    }
    const output=event.result?.output;
    let childReview,error;
    const simulatedCall=output?.status==="completed" && /<tool_call>[\s\S]*?<function[=>]/.test(output.output || "");
    if(simulatedCall)error="NATIVE_TOOL_CALL_REQUIRED: child returned tool-call XML as ordinary text; no command in that text executed. Continue EXISTING child "+output.sessionID+" with its recorded agent, use actual enabled native tools or return an honest structured BLOCKED report. Do not create a replacement child.";
    const recoveryState=await ctx.storage.get("session/"+event.sessionID);
    const recoveryAttempt=recoveryState?.criticRecoveryInFlight?.child===output?.sessionID;
    if(recoveryAttempt && output?.status==="completed" && (output.sessionID!==recoveryState.criticRecoveryInFlight.child || !validRecoveredCriticVerdict(output.output||"")))
      error="CRITIC_RECOVERY_VERDICT_REQUIRED: expected a standalone JSON object with exactly decision (PROCEED or REVISE), findings (nonempty array), evidence (nonempty array). BLOCKED, XML, quoted instructions and incomplete outputs cannot clear the child.";
    if(!error && !simulatedCall && output?.status==="completed") {
      let childDirectory;
      try{childDirectory=unpack(await ctx.session.get({sessionID:output.sessionID}))?.location?.directory;}catch{}
      const invented=await unverifiedRequestClaims(output.output,childDirectory);
      if(invented.length)error="CHILD_CLAIM_UNVERIFIED: child "+output.sessionID+" reported worker request "+invented.map(x=>x.slice(0,12)+"…").join(", ")+" but no such request file exists, so nothing is queued. Its other claimed edits are also unverified (a compacted child can report work it never did). Do not wait for a notification or relay its summary. Verify the actual files, then continue EXISTING child "+output.sessionID+" to make the change and call the native worker tool for real.";
    }
    if(output?.status==="completed") {
      const childState=await ctx.storage.get("session/"+output.sessionID);
      if(childState?.pendingVisual) {
        const parsed=finalReceipt(output.output || "");
        const content=parsed ? JSON.stringify(parsed) : "";
        if(reviewReceipt({path:"/child/.opencode/validation/review/visual-review.json",content},childState)) {
          childReview={reviewVersion:2,semanticStatus:"MODEL_REPORTED_SINGLE_FRAME_ONLY",sha256:childState.pendingVisual.sha256,model:childState.pendingVisual.presentedBy,sessionID:output.sessionID,receipt:JSON.parse(content)};
          await transaction(output.sessionID,state=>{state.reviews=[...state.reviews,childReview].slice(-16);state.pendingVisual=null;});
        } else error="VISION_CHILD_REVIEW_REQUIRED: "+receiptMismatch({path:"/child/.opencode/validation/review/visual-review.json",content},childState)+". Continue EXISTING child "+output.sessionID+" ONLY. Runtime image="+childState.pendingVisual.path+" sha256="+childState.pendingVisual.sha256+" model="+childState.pendingVisual.presentedBy+". Return one complete JSON object, preferably under1200 characters, with observations (not observed).";
      }
    }
    await transaction(event.sessionID,async state=>{
      if(state.childCall===event.id)state.childCall=null;
      if(state.criticRecoveryInFlight?.call===event.id) {
        const r=state.criticRecoveryInFlight;
        state.criticRecoveryHistory=[...(state.criticRecoveryHistory||[]),{child:r.child,nonce:r.nonce,at:Date.now(),status:output?.status||"no-output",accepted:!error && output?.status==="completed" && output.sessionID===r.child,error:error||null}].slice(-8);
        state.criticRecoveryInFlight=null;
        state.consumedCriticRecoveryGrants=[...(state.consumedCriticRecoveryGrants||[]),r.nonce];
        state.criticRecoveryConsumed=true;
        // An unverified or malformed return must retain the original hard stop.
        if(error || output?.status!=="completed" || output?.sessionID!==r.child)state.simulatedCallBlocked=r.child;
      }
      if(output?.sessionID && (output.status==="running" || error))state.child=output.sessionID;
      if(simulatedCall) {
        state.simulatedCallAttempts ??={};
        state.simulatedCallAttempts[output.sessionID]=(state.simulatedCallAttempts[output.sessionID] || 0)+1;
        if(state.simulatedCallAttempts[output.sessionID]>=2)state.simulatedCallBlocked=output.sessionID;
      }
      if(error && !simulatedCall) {
        state.lastChildReviewError=error;
        state.childReviewAttempts=(state.childReviewAttempts || 0)+1;
        if(state.childReviewAttempts>=2)state.childReviewBlocked=true;
      }
      if(!error && output?.sessionID && output.status==="completed") {
        const retainedErrors=state.childReceiptRecovery?.sessionID===output.sessionID && event.input.agent!=="watoom-critic" ? state.errors : 0;
        state.direct=0;state.reads=0;state.errors=retainedErrors;state.child=null;state.gateCheckpointWritten=false;state.guardRejections=0;state.childReviewAttempts=0;state.childReviewBlocked=false;state.lastChildReviewError=null;
        const completedChild=await ctx.storage.get("session/"+output.sessionID);
        if(event.input.agent!=="watoom-critic" && (completedChild?.guardRejections || 0)-(state.childGuardBaseline || 0)>=2)state.errors=Math.min(Math.max(2,state.errors),GUARD_REJECTION_CAP);
        if(event.input.agent==="watoom-critic"){state.criticConsulted=true;state.criticEscalations=Math.min((state.criticEscalations||0)+1,CRITIC_ESCALATION_CAP);}
        // The cap bounds critic loops on one stuck problem, not a whole long-lived session.
        else if(state.errors===0)state.criticEscalations=0;
        state.lastHandoff={sessionID:output.sessionID,agent:event.input.agent,completed:true};
        if(childReview){state.reviews=[...state.reviews,childReview].slice(-16);if(state.pendingVisual?.sha256===childReview.sha256)state.pendingVisual=null;}
      } else if(!error && output?.status!=="running")state.errors++;
    });
    if(error)throw new Error(error);
  });
  await ctx.session.hook("http.request",async event=>{
    if(event.kind!=="primary" || !protectedAgents.has(event.agent))return;
    const state=await ctx.storage.get("session/"+event.sessionID);
    if(!state)return;
    let body=await event.request.clone().json();
    const model=event.model.providerID+"/"+(event.model.id || event.model.modelID);
    if(!state.pendingVisual && state.visualResume && new URL(event.request.url).pathname.endsWith("/chat/completions")) {
      body=resumeAfterReview(body,state.visualResume);
      event.request=new Request(event.request,{body:JSON.stringify(body)});
      await transaction(event.sessionID,s=>{s.visualResume=null;});
    }
    if(state.pendingVisual && visionModels.has(model) && requestContainsImage(body.messages,state.pendingVisual.sha256)) {
      body=isolatedReviewBody(body,state.pendingVisual,model,event.sessionID,event.agent);
      event.request=new Request(event.request,{body:JSON.stringify(body)});
      // Verify the exact image bytes are present in the outbound request.
      // requestContainsImage already confirmed SHA-256 match; record the byte
      // length as additional evidence that real image data was sent.
      const imageBytes=extractImageBytes(body.messages,state.pendingVisual.sha256);
      await transaction(event.sessionID,s=>{s.presentationInFlight={sha256:s.pendingVisual.sha256,model,url:event.request.url,reviewMode:"isolated-image-v2",imageBytes:imageBytes};});
    }
    if(new URL(event.request.url).pathname.endsWith("/chat/completions")) {
      const constrained=criticOnlyRequest(body,state,event.agent);
      if(constrained!==body){body=constrained;event.request=new Request(event.request,{body:JSON.stringify(body)});}
    }
    if(!state.terminalReport)return;
    // Only this provider's OpenAI chat endpoint, and only a tool-disabled step.
    if(!new URL(event.request.url).pathname.endsWith("/chat/completions") || body.tools?.length)return;
    body.response_format={type:"json_schema",json_schema:{name:"guarded_session_report",strict:true,schema:terminalSchema(state,event.sessionID)}};
    event.request=new Request(event.request,{body:JSON.stringify(body)});
  });
  await ctx.session.hook("http.response",async event=>{
    if(event.kind!=="primary" || !protectedAgents.has(event.agent))return;
    await transaction(event.sessionID,state=>{
      const proof=state.presentationInFlight;
      if(proof && proof.url===event.request.url && proof.sha256===state.pendingVisual?.sha256 && event.response.ok && proof.imageBytes>0) {
        state.pendingVisual.presentedBy=proof.model;
        state.pendingVisual.presentationEvidence="exact-image-request-successful-response";
        state.pendingVisual.reviewMode=proof.reviewMode;
        state.pendingVisual.imageBytesSent=proof.imageBytes;
      }
      state.presentationInFlight=null;
    });
  });
  // A capped coordinator with two errors could neither delegate (critic required) nor call the
  // critic (bound), so the session was dead even after the owner replied. A new prompt (owner
  // message or job-completion notice) re-arms exactly one critic review; the critic-before-repair
  // rule itself stays in force.
  try {
    await ctx.session.hook("prompt",async event=>{
      if(!event?.sessionID)return;
      const state=await ctx.storage.get("session/"+event.sessionID);
      if(!state)return;
      await transaction(event.sessionID,s=>{rearmAfterPrompt(s);});
      if((state.criticEscalations || 0)<CRITIC_ESCALATION_CAP)return;
      await transaction(event.sessionID,s=>{s.criticEscalations=CRITIC_ESCALATION_CAP-1;});
    });
  } catch {}
  await ctx.session.hook("context",async event=>{
    if(event.agent?.startsWith("watoom-") && Array.isArray(event.system)) {
      const drop=promptDrop(event.agent,unpack(await ctx.session.get({sessionID:event.sessionID}))?.location?.directory);
      event.system.forEach((part,index)=>{if(part?.type==="text")event.system[index]={...part,text:trimSections(part.text,drop)};});
    }
    if(!protectedAgents.has(event.agent))return;
    await transaction(event.sessionID,async state=>{
      const coordinator=event.agent==="watoom-workflow";
      state.callingAgent=event.agent;
      reconcileCompletedVisualReview(state,event);
      if(!coordinator || !state.pendingVisual)delete event.tools[VISUAL_RECEIPT_TOOL];
      const learned=learnedLessonsNote(loadLearnedLessons());
      if(learned && Array.isArray(event.system))event.system.push({type:"text",text:learned});
      if(!workerRoles.has(event.agent)){delete event.tools.watoom_game_worker;delete event.tools.watoom_rig_game_job;delete event.tools.watoom_asset_capture;}
      if(event.tools.watoom_esp32 && (!workerRoles.has(event.agent) || !esp32Project(unpack(await ctx.session.get({sessionID:event.sessionID}))?.location?.directory)))delete event.tools.watoom_esp32;
      // A primary model step starts only after its previous native tool batch
      // settled. Clear a stale call reservation after interrupt/restart; the
      // native durable job/sessionID remains authoritative for running children.
      if(coordinator)state.childCall=null;
      const key=event.model.providerID+"/"+(event.model.id || event.model.modelID);
      // Presentation is verified from exact outbound pixels plus successful response,
      // not inferred from a generic image elsewhere in session context.
      if(readOnlyRoles.has(event.agent)){delete event.tools.write;delete event.tools.edit;}
      if(readOnlyRoles.has(event.agent))event.system.push({type:"text",text:"Bounded investigation: read known receipt/artifact paths first. Never recursively search all /data/ai or helper-scripts; inspect a known component directory and narrow paths/patterns after a timeout. The application container does not expose host /etc/systemd/system; absence here is not evidence a host service is absent. Report the missing host evidence to the coordinator. Native no-match results and documented grep/rg exit 1 with no error output are discovery outcomes, not failed repairs. When tools stop, return verified findings, evidence paths, exact errors and missing evidence; a failed optional discovery must not erase an already supported diagnosis. Never claim PASS or invent unavailable evidence."});
      else event.system.push({type:"text",text:"Unlike read-only roles, a grep/rg search that legitimately finds nothing still counts as a tool failure against your error budget here -- it does not get the discovery exemption. When you need to find out whether something exists (a symbol, a file, a string) rather than confirm something you already expect to find, delegate that lookup to watoom-investigator instead of running grep/rg yourself. Only search directly for things you already expect to find, such as confirming your own edit landed."});

      if(ctx.options?.rigAsyncStage===true && workerRoles.has(event.agent))event.system.push({type:"text",text:"RIG BACKGROUND JOBS (stage): prefer native watoom_rig_game_job for fixed Godot jobs and watoom_asset_capture for Blender captures. They return a stable queued identity immediately. Record dependencies and continue independent work; wait only when the next task actually depends on the receipt. Do not poll rapidly or submit duplicate requests. A local operator pause retains the queue. Check inputs_frozen before modifying the requested source; never accept stale receipts or unreviewed pixels."});
      const reason=gate(state,coordinator);
      if(reason) {
        let allowed=reason==="vision" ? new Set(["subagent","read","write",VISUAL_RECEIPT_TOOL]) : new Set(["subagent"]);
        if(reason!=="vision" && (!state.gateCheckpointWritten || state.pendingVisual))allowed.add("write");
        if(reason==="vision" && state.pendingVisual.additionalReads>=2)allowed.delete("read");
        for(const name of Object.keys(event.tools))if(!allowed.has(name))delete event.tools[name];
      }
      if(!coordinator && (state.guardRejections>=2 || state.errors>=2)) {
        const canWriteReceipt=state.pendingVisual && !readOnlyRoles.has(event.agent) && ((state.receiptFailures||0)<2 || (state.criticConsulted && (state.receiptFailures||0)<3));
        for(const name of Object.keys(event.tools))if(!(name==="write" && canWriteReceipt) && (name!=="subagent" || !criticCallers.has(event.agent) || state.criticConsulted))delete event.tools[name];
        event.system.push({type:"text",text:"CHILD_ESCALATION_REQUIRED: repeated guard rejections. Stop tool retries. Call ONLY watoom-critic as a foreground child, no model override; after one critic review, further failure returns control to coordinator. Return the matching pixel JSON as FINAL if you have seen the pixels, with an additional escalation_required:true, blocker, last_guard_error and failed_attempts fields. Exact last rejection: "+state.lastGuardError+". Do not bypass with OCR or invent causes."});
      }
      if(event.tools.watoom_specialist_run)event.tools.watoom_specialist_run.description=(event.tools.watoom_specialist_run.description || "")+" Local Toolkit asset.search requires payload {task:'asset-search',query:'tree',limit:8}; retain a stable job and use the direct native tool.";
      state.specialistExposure={list:!!event.tools.watoom_specialist_list,run:!!event.tools.watoom_specialist_run,guardReason:reason||null};
      for(const name of ["watoom_game_worker","watoom_asset_capture","watoom_rig_game_job"])if(event.tools[name])event.system.push({type:"text",text:name+" is a DIRECT NATIVE tool enabled in this exact step. It is not reachable from Code Mode (execute). Call it as a top-level function; an execute 'Unknown tool' result is not tool absence."});
      if(event.tools.watoom_specialist_list)event.system.push({type:"text",text:"watoom_specialist_list is a DIRECT NATIVE tool enabled in this exact step. It is excluded from Code Mode search by design. Invoke the native tool directly; a Code Mode search miss is not tool absence."});
      if(state.pendingExternal)event.system.push({type:"text",text:"Existing external job "+state.pendingExternal.request_id+" is "+state.pendingExternal.status+". Continue independent work or finish with a factual pending-job handoff. Never sleep/poll in a loop. Native worker protocol files are runtime-owned: never overwrite them, invent message/call IDs, or submit a duplicate. Completion is automatic."});
      event.system.push({type:"text",text:DELEGATION_ROLE_GUIDE});
      const notes=["Never emit <tool_call> or <function=...> text. Such text executes nothing. Use only actual enabled native function calls; if no tools remain, return concise factual results or BLOCKED with the exact last error."];
      if(!state.simsIntakeParentChecked && state.isChild) {
        const info=unpack(await ctx.session.get({sessionID:event.sessionID}));
        const parent=info?.parentID ? await ctx.storage.get("session/"+info.parentID) : null;
        if(parent?.simsConversationalIntake)state.simsConversationalIntake=true;
        state.simsIntakeParentChecked=true;
      }
      if(state.simsConversationalIntake) {
        delete event.tools.question;
        notes.push("Sims conversational intake: ask any missing questions as ordinary chat and END THE TURN. The next user chat reply continues this SAME job. Do not call a blocking question/form tool, invent answers or start a duplicate job. This does not grant permission or bypass approval checks.");
      }

      if(coordinator && state.child && state.simulatedCallBlocked===state.child) {
        const childState=await ctx.storage.get("session/"+state.child);
        if(criticRecovery(state,event.sessionID,ctx.options,childState)) {
          for(const name of Object.keys(event.tools))if(name!=="subagent")delete event.tools[name];
          notes.push("ONE-USE OPERATOR CRITIC RECOVERY: continue only existing child "+state.child+" as watoom-critic with sessionID, background:false, no model override. Do not use websearch. Return ONE standalone JSON object with exactly keys decision (REVISE or PROCEED), findings (nonempty array of concrete findings), evidence (nonempty array of verified file/line or diagnostic references). If review cannot be completed, report BLOCKED but it will NOT release the parent gate. Native tool-call XML never counts as evidence.");
        } else if(toolRecovery(state,event.sessionID,ctx.options,childState)) {
          for(const name of Object.keys(event.tools))if(name!=="subagent")delete event.tools[name];
          notes.push("Operator-authorized one-use recovery after correcting parse-only regression classification: resume EXISTING child "+state.child+" with recorded agent and inherited model. Do not replay work or retry a full suite in the app.");
        } else {
          for(const name of Object.keys(event.tools))delete event.tools[name];
          notes.push("HARD STOP: existing child repeatedly returned simulated tool calls. Return BLOCKED with child ID; do not print more tool-call XML or create replacement children.");
        }
      }
      if(!coordinator && criticCallers.has(event.agent))notes.push("Child delegation accepts ONLY agent watoom-critic, background:false, no model override, once per package. Never call explore, general, builder, investigator or workflow. After critic, further failure returns BLOCKED to parent.");
      if(coordinator && state.lastHandoff && !state.child)notes.push("Each new package starts a FRESH child; a completed child ("+state.lastHandoff.sessionID+") is not resumed, because resuming replays its whole history into context. Put what the child needs in the prompt (goal, paths, receipts) or in a .opencode/work checkpoint it can read. Your parent sessionID "+event.sessionID+" is NEVER a subagent resume target.");
      if(coordinator)notes.push("Runtime coordinator guard: after six direct execution calls or eighteen read-only discovery calls delegate a bounded package via native subagent. Only a real completed child resets the budget; compaction/restart/user steering does not. Two execution failures require a critic. No parallel or duplicate child.");
      if(coordinator && state.child) {
        const childState=await ctx.storage.get("session/"+state.child);
        if(childState?.pendingVisual) {
          const v=childState.pendingVisual;
          const operatorGrant=recoveryGrant(state,event.sessionID,ctx.options,childState);
          if(!v.presentedBy) {
            for(const name of Object.keys(event.tools))delete event.tools[name];
            state.lastChildReviewError="VISION_MODEL_REQUIRED: existing child "+state.child+" has no verified image presentation for "+v.path+". Use a configured verified vision model ("+[...visionModels].join(", ")+"). Preserve completed capture and existing child. No model=null receipt, guessed pixels, replacement child or unchanged retry. Operator routing reconciliation is required.";
            notes.push(state.lastChildReviewError);
          } else if(state.childReviewBlocked && operatorGrant) {
            for(const name of Object.keys(event.tools))if(name!=="subagent")delete event.tools[name];
            notes.push("One operator-authorized evidence recovery: continue EXISTING child "+state.child+" with agent "+childState.callingAgent+", sessionID exactly matching, background:false, no model override. Request only complete FINAL JSON from pixels already presented; retain runtime image "+v.path+" SHA256 "+v.sha256+" model "+v.presentedBy+". No new child and no forged observations.");
          } else if(state.childReviewBlocked) {
            for(const name of Object.keys(event.tools))delete event.tools[name];
            notes.push("HARD STOP: repeated existing-child visual evidence recovery failed. Return BLOCKED now with child sessionID "+state.child+" and last verified evidence. No further calls, new children, critic retries, receipt fabrication or OCR bypass. User/operator reconciliation is required.");
          } else notes.push("Existing visual child recovery ONLY: subagent agent "+childState.callingAgent+", sessionID "+state.child+", background:false. Its CURRENT pending image is "+v.path+", SHA256 "+v.sha256+", verified model "+v.presentedBy+". Include these runtime facts in the continuation prompt. Ask for ONLY a FINAL JSON object with image_path, image_sha256, model, basis:pixels, verdict and at least two honest observations from pixels already seen. No shell hash is required, no different image may be read. A builder may write ONLY the matching visual-review JSON receipt; read-only children must return FINAL JSON instead. Never repeat the original full transcription prompt. A BLOCKED prose answer is not visual evidence.");
        }
      }
      if(coordinator && reason)notes.push("Current runtime gate: "+reason+". Work tools are unavailable until the required handoff/evidence is completed; checkpoint safely or report BLOCKED.");
      if(reason==="child-critic")notes.push(state.criticConsulted ? (findingsHandoff(state) ? "Stop tool retries and return PARTIAL findings to the coordinator with verified evidence, exact failed discovery/command and missing evidence. Tool failure does not erase successful reads; do not claim full completion." : "Return BLOCKED to your coordinator/owner: the post-critic repair failed; do not retry tools.") : "Two real execution failures require your single foreground critic consultation. Do not perform a third work attempt.");
      if(reason==="critic")notes.push("Critical review is required now: call subagent with agent watoom-critic, background:false, project/checkpoint paths, failed attempts and a precise question. Review evidence before repair.");
      if(state.pendingVisual) {
        const v=state.pendingVisual;
        notes.push("VISION FIRST: actual image "+v.path+" SHA256 "+v.sha256+". Pixel review is pending. Metadata, dimensions, crop scripts and file existence cannot establish visual acceptance. Verified model image presentation: "+(v.presentedBy || "NOT VERIFIED; reread actual image using a verified vision-capable model or report BLOCKED")+". Before continuing other work, "+(["watoom-investigator","watoom-reviewer","watoom-critic"].includes(event.agent) ? "return the matching JSON object as your final reply; do not write files" : "use native write to save .opencode/validation/<task-id>/visual-review.json")+" with image_path, image_sha256, model, basis:pixels, verdict:PASS|FAIL|BLOCKED, and observations (not observed): an array of at least two concrete strings, each at least12 characters after trimming. Use the exact provider-qualified model, never its short alias or the disk file hash. Keep FINAL receipt JSON complete and concise (about1200 characters), not tool-call XML or Markdown. Match the exact path/hash/model above. Do not invent observations. This receipt records model-reported single-frame observations, not proof of artistic correctness. Use review_version2, review_scope single_frame_pixels, framing {usable,issues}, defects (visible quality defects; PASS only when empty), uncertainties and inferences. Keep metadata/technical causes out of pixel observations. If delegating, pass the image path and require the child to read pixels and return its own receipt. A tool call or manifest alone is not a visual review.");
      }
      if(state.pendingVisual && ["watoom-investigator","watoom-reviewer","watoom-critic"].includes(event.agent))
        notes.push("You are read-only: do not write a file or request new permissions. After examining the actual pixels, return ONLY the matching visual-review JSON object as your final reply; the parent guard verifies it against this child's image presentation and records the receipt. If blocked, return BLOCKED with honest observations/limitations; never invent pixel observations.");
      const queueNote=reviewQueueNote(state);
      if(queueNote)notes.push(queueNote);
      constrainReceipt(event,state);
      if(state.pendingVisual && state.pendingVisual.presentedBy && !Object.keys(event.tools).length)notes.push("NO TOOLS ARE AVAILABLE. Do not print tool-call XML or retry a read. Return ONLY the complete matching visual-review JSON from pixels already presented, or an honest BLOCKED receipt. The parent validates this JSON without another tool call.");
      constrainDelegation(event,state,state.child ? await ctx.storage.get("session/"+state.child) : null);
      state.terminalReport=Object.keys(event.tools).length===0;
      if(state.terminalReport)notes.push("This step has no executable tools. Return the constrained JSON report only; no tool-call XML, executable proposal, or repeated retry.");
      if(notes.length)event.system.push({type:"text",text:notes.join("\n\n")});
    });
  });
}
export default {id:"watoom.coordinator-guard",setup:install};
