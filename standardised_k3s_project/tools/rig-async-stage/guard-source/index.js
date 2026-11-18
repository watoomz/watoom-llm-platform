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
const protectedAgents = new Set(["watoom-workflow","watoom-builder","watoom-investigator","watoom-reviewer","watoom-critic","watoom-creative-writer"]);
const criticCallers = new Set(["watoom-builder","watoom-investigator","watoom-reviewer"]);
const readOnlyRoles = new Set(["watoom-investigator","watoom-reviewer","watoom-critic"]);
const exempt = new Set(["skill","question","watoom_memory_recall"]);
const unpack = value => value?.data ?? value;
const initial = seed => ({version:1,direct:seed?.direct || 0,errors:seed?.requireCritic ? 2 : 0,child:null,pendingVisual:null,reviews:[],calls:[]});
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
export function constrainReceipt(event,state) {
  if(!state.pendingVisual || !event.tools.write)return;
  const tool=event.tools.write,input=structuredClone(tool.input || {type:"object",properties:{}});
  input.properties ??={};
  input.properties.path={type:"string",enum:[posix.join(posix.dirname(state.pendingVisual.path),".opencode/validation",event.sessionID,"visual-review.json")],description:"Accepted visual receipt path; content must match the pending image/hash/model and contain pixel observations."};
  event.tools.write={...tool,input,description:"Save the pending pixel-review JSON receipt to the exact path in the schema. Do not write a checkpoint or image file."};
}

export function semanticReceipt(value) {
 if(!value || Object.keys(value).some(k=>!["review_version","review_scope","image_path","image_sha256","model","basis","verdict","observations","framing","uncertainties","inferences"].includes(k)))return false;
 if(value?.review_version!==2 || value.review_scope!=="single_frame_pixels")return false;
 if(typeof value.framing?.usable!=="boolean" || !Array.isArray(value.framing.issues) || !Array.isArray(value.uncertainties) || !Array.isArray(value.inferences))return false;
 if(value.inferences.length!==0 || value.framing.issues.length>6 || value.uncertainties.length>6 || (!value.framing.usable && value.framing.issues.length===0))return false;
 if(![...value.framing.issues,...value.uncertainties,...value.inferences].every(x=>typeof x==="string" && x.length<=600))return false;
 return value.verdict!=="PASS" || (value.framing.usable && value.framing.issues.length===0);
}
export function reviewSchema(v) {
 const base={type:"object",additionalProperties:false,required:["review_version","review_scope","image_path","image_sha256","model","basis","verdict","observations","framing","uncertainties","inferences"],properties:{review_version:{const:2},review_scope:{const:"single_frame_pixels"},image_path:{const:v.path},image_sha256:{const:v.sha256},model:{const:v.presentedBy},basis:{const:"pixels"},verdict:{enum:["PASS","FAIL","BLOCKED"]},observations:{type:"array",minItems:2,maxItems:6,items:{type:"string",minLength:12,maxLength:400}},framing:{type:"object",additionalProperties:false,required:["usable","issues"],properties:{usable:{type:"boolean"},issues:{type:"array",maxItems:6,items:{type:"string",maxLength:600}}}},uncertainties:{type:"array",maxItems:6,items:{type:"string",maxLength:600}},inferences:{const:[]}}};
 const branch=(verdicts,usable,minIssues,maxIssues)=>{
  const schema=structuredClone(base);
  schema.properties.verdict={enum:verdicts};
  schema.properties.framing.properties.usable={const:usable};
  Object.assign(schema.properties.framing.properties.issues,{minItems:minIssues,maxItems:maxIssues});
  return schema;
 };
 // Constrain generation as well as post-validation. Never silently rewrite a
 // model's verdict or discard framing issues to turn a rejection into a PASS.
 return {...base,anyOf:[branch(["PASS"],true,0,0),branch(["FAIL","BLOCKED"],true,0,6),branch(["FAIL","BLOCKED"],false,1,6)]};
}

export function isolatedReviewBody(body,pending,model,sessionID) {
 let image;
 const visit=x=>{if(!x || typeof x!=="object")return;if(x.type==="image_url" && requestContainsImage(x,pending.sha256))image=x;for(const v of Object.values(x))if(Array.isArray(v))v.forEach(visit);else if(v && typeof v==="object")visit(v);};visit(body.messages);
 if(!image)return body;
 const schema=reviewSchema({...pending,presentedBy:model});
 const path=posix.join(posix.dirname(pending.path),".opencode/validation",sessionID,"visual-review.json");
 const write=(body.tools || []).find(x=>x.type==="function" && x.function?.name==="write");
 const instruction="Review ONLY the attached pixels, independently of filenames, prior scene descriptions and desired results. Give 2-6 short visible facts with location, approximate count, colours and framing. Use 'bright patch' instead of inferring a sun/light; uncertain objects must remain uncertain. Never infer renderer/API, source pack/GLB IDs, dimensions, normals, hidden meshes, animation, correctness or technical cause from a static view. Do not invent hypotheses in a pixel-only inspection: inferences must be []. Put missing evidence in uncertainties; causal investigation happens separately using source/runtime evidence. Use broad positions, not unmeasured numerical percentages or physical dimensions. Describe featureless fields as background, not an assumed sky/ground type unless clearly identifiable. Check whether the main subject/ground is actually visible, readable and framed, or mostly background/clipped/occluded. If framing prevents assessment, framing.usable=false and verdict=FAIL or BLOCKED, never PASS. PASS means this single frame is usable for inspection, NOT complete task acceptance, rig/engine validation or correct art. Empty/unhelpful views fail. Do not fill missing content from expectations. Produce DATA, never a JSON schema. Copy only these fixed metadata fields: "+JSON.stringify({review_version:2,review_scope:"single_frame_pixels",image_path:pending.path,image_sha256:pending.sha256,model,basis:"pixels"})+". Add verdict (FAIL, BLOCKED, or PASS), observations (2-6 short strings), framing {usable:boolean,issues:string[]}, uncertainties:string[], and inferences:[]. If issues is nonempty or usable is false, verdict MUST NOT be PASS. Framing issues are obstacles to assessing the visible scene; harmless interface labels/logos can be recorded as observations instead. If you do list any framing issue, choose FAIL or BLOCKED even if the scene looks attractive. Never remove a real obstruction just to obtain PASS. Do not add type/properties/required/const schema keywords. "+(write ? "Call only native write once, path "+JSON.stringify(path)+", content the complete JSON receipt. Do not read other files, explain plans or print XML." : "Return ONLY the complete JSON receipt.");
 const next={...body,messages:[{role:"system",content:"Independent pixel-only visual inspection. Task history and author claims are intentionally excluded."},{role:"user",content:[{type:"text",text:instruction},image]}],temperature:0,parallel_tool_calls:false};
 if(write){next.tools=[write];next.tool_choice={type:"function",function:{name:write.function.name}};delete next.response_format;}
 else {delete next.tools;delete next.tool_choice;next.response_format={type:"json_schema",json_schema:{name:"isolated_pixel_review",strict:true,schema}};}
 return next;
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
 return (state.reviews || []).some(r=>r.reviewVersion===2 && r.receipt && ["review_version","review_scope","image_path","image_sha256","model","basis","verdict","observations","framing","uncertainties","inferences"].every(k=>JSON.stringify(r.receipt[k])===JSON.stringify(v?.[k])));
}
export const DELEGATION_ROLE_GUIDE="Investigator gathers a specific missing fact; critic challenges a diagnosis/plan and is mandatory after two execution failures; builder implements and validates; reviewer checks finished results/pixels; coordinator owns scope/checkpoints. Reuse known evidence instead of repeating discovery. Critic first when required; investigator cannot satisfy that gate. No automatic chain through every role.";
export function constrainDelegation(event,state,childState) {
 const tool=event.tools.subagent;
 if(!tool)return;
 const coordinator=event.agent==="watoom-workflow";
 if(!coordinator && (!criticCallers.has(event.agent) || state.criticConsulted)){delete event.tools.subagent;return;}
 let allowed=coordinator ? ["watoom-builder","watoom-investigator","watoom-reviewer","watoom-critic","watoom-kali"] : ["watoom-critic"];
 if(coordinator && state.child && childState?.callingAgent)allowed=[childState.callingAgent];
 else if(coordinator && state.errors>=2)allowed=["watoom-critic"];
 const input=structuredClone(tool.input || {type:"object",properties:{}});
 input.properties ??={};
 input.properties.agent={type:"string",enum:allowed,description:(coordinator && state.errors>=2 && !state.child ? "Mandatory critic review now; investigator is forbidden until that review completes. " : "")+DELEGATION_ROLE_GUIDE};
 input.properties.background={type:"boolean",enum:[false],description:"Serial foreground execution only."};
 if(!coordinator)delete input.properties.model;
 if(state.child) {
  input.properties.sessionID={type:"string",enum:[state.child],description:"Resume this existing child; never use the parent sessionID."};
  input.required=[...new Set([...(input.required || []),"sessionID"])];
 } else if(state.lastHandoff?.sessionID && allowed.includes(state.lastHandoff.agent)) {
  input.properties.sessionID={type:"string",enum:[state.lastHandoff.sessionID],description:"Optional: resume only this known child with its recorded agent. Omit for a new package."};
 } else {
  // A new child has no resume identity. Do not expose an unconstrained string
  // that invites the model to copy its own session ID into this field.
  delete input.properties.sessionID;
  input.required=(input.required || []).filter(name=>name!=="sessionID");
 }
 input.additionalProperties=false;
 event.tools.subagent={...tool,input,description:"Serial bounded native delegation. Allowed agent: "+allowed.join(", ")+". "+
  (state.child ? "Continue existing child "+state.child+" only." : "Omit sessionID for new work; resume only a real child ID with its recorded agent.")+
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
  if (coordinator && state.direct >= BUDGET) return "handoff";
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
export function assertWorkerProtocolAccess(name,input) {
 const path=input?.path || input?.filePath || input?.file_path || "";
 if((["write","edit","apply_patch","patch"].includes(name) && (workerProtocolPath(posix.normalize(path)) || workerProtocolPath(input?.patch || input?.patchText))) ||
    (name==="shell" && workerProtocolPath(input?.command) && !shellReadOnly(input?.command)))
  throw Error("WORKER_PROTOCOL_READ_ONLY: native worker request/status files are runtime-owned. Never create, edit, replace or delete them through write/edit/shell. Use the native worker request/status tool; declarative capture-jobs inputs remain writable. Read existing protocol evidence with native read or a permitted read-only shell command. Corruption requires operator reconciliation, never invented IDs or another job.");
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
 const s=String(command || "").trim();
 if(/[;&|`\n\r]|\$\(/.test(s))return false;
 const simple=/^(?:timeout\s+\d+\s+)?(?:[^\s]+\/)?godot(?:[0-9.-]*)?\s+(.*)$/i.exec(s);
 if(!simple)return false;
 const args=simple[1];
 if(/^(?:--version|--help|-h)$/.test(args.trim()))return true;
 return /(?:^|\s)--check-only(?:\s|$)/.test(args) && /(?:^|\s)(?:--script|-s)\s+[^\s]+\.gd(?:\s|$)/.test(args) && !/\.tscn(?:\s|$)|--(?:editor|import|write-movie|scene|main-loop)(?:\s|=|$)/.test(args);
}

export function assertAllowed(name, input, state, coordinator) {
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
    throw Error("EXTERNAL_GODOT_WORKER_REQUIRED: every Godot scene, capture and executable script launch must use the bounded external worker. --headless, xvfb-run, timeout and calling it a syntax/load check do not make a scene launch safe in the2GiB app. Only standalone --version/--help or --check-only with --script/-s and no scene/import/project execution are allowed. Use the installed native worker operation; unsupported captures require operator worker enrollment, never local rendering.");
  if (name === "subagent") {
    if(!coordinator && input.model!==undefined)throw new Error("CRITIC_MODEL_INHERIT: child critics must inherit the selected model; omit model.");
    if(!coordinator && (!criticCallers.has(state.callingAgent) || input.agent!=="watoom-critic"))
      throw new Error("CRITIC_ONLY_DELEGATION: child agents may call only watoom-critic; critic cannot delegate.");
    if(!coordinator && state.criticConsulted)throw new Error("RETURN_TO_COORDINATOR: critic already consulted; do not create another retry chain.");
    if(input.background===true)throw new Error("COORDINATOR_SERIAL: use foreground subagent.");
    if(state.childCall)throw new Error("COORDINATOR_SERIAL: a child is already in flight.");
    const receiptContinuation=coordinator && state.child && input.sessionID===state.child &&
      state.childReceiptRecovery?.sessionID===state.child && state.childReceiptRecovery?.agent===input.agent;
    if (coordinator && input.background === true) throw new Error("COORDINATOR_SERIAL: use foreground subagent with background:false.");
    if(coordinator && state.child && state.simulatedCallBlocked===state.child)throw new Error("NATIVE_CHILD_BLOCKED: repeated simulated tool calls from existing child; report BLOCKED with its ID, no replacement or automatic retry.");
    if(coordinator && state.childReviewBlocked)throw new Error("VISION_CHILD_BLOCKED: two evidence-recovery returns failed; stop delegation and report BLOCKED with the existing child sessionID. Do not restart or replace it.");
    if (state.child && input.sessionID !== state.child) throw new Error("COORDINATOR_CHILD_PENDING: continue existing sessionID "+state.child+"; never duplicate it.");
    if (coordinator && state.errors >= 2 && input.agent !== "watoom-critic" && !receiptContinuation) throw new Error("COORDINATOR_CRITIC_REQUIRED: call watoom-critic before another repair attempt.");
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
      if(typeof input?.path==="string" && /\.(?:png|jpe?g|webp|gif|bmp|tiff?)$/i.test(input.path) && input.path!==state.pendingVisual.path)
        throw new Error("VISION_REVIEW_REQUIRED: finish the current image review before reading another image.");
      return;
    }
    throw new Error("VISION_REVIEW_REQUIRED: inspect the actual image with a verified vision model, then write the matching visual-review JSON receipt before further execution. Metadata and cropping are not review.");
  }
  if(!coordinator && state.errors>=2)
    throw new Error(state.criticConsulted ? "RETURN_TO_COORDINATOR: repair failed after critic; return BLOCKED and exact evidence, no more work calls." : "CHILD_ESCALATION_REQUIRED: two failed executions; consult ONLY watoom-critic before another work call.");
  if (coordinator && (state.child || state.errors >= 2 || state.direct >= BUDGET)) {
    if (name === "write" && checkpoint(input) && !state.gateCheckpointWritten) return;
    throw new Error("COORDINATOR_HANDOFF_REQUIRED: write at most one checkpoint then call the native subagent tool; use write with verified complete checkpoint content, not an exact-string edit of stale text. Passive-tool retries do not bypass this boundary.");
  }
}
export function requestContainsImage(value,sha256) {
 if(!value || typeof value!=="object")return false;
 if(value.type==="image_url") {
  const url=typeof value.image_url==="string" ? value.image_url : value.image_url?.url;
  if(typeof url==="string" && /^data:image\/[^;]+;base64,/.test(url))return createHash("sha256").update(Buffer.from(url.slice(url.indexOf(",")+1),"base64")).digest("hex")===sha256;
 }
 return Object.values(value).some(x=>Array.isArray(x)?x.some(v=>requestContainsImage(v,sha256)):requestContainsImage(x,sha256));
}

export function typedToolkitInput(name,input) {
 if(name!=="watoom_specialist_run" || input?.specialistID!=="local-toolkit" || input?.capability!=="asset.search" || !input.payload || typeof input.payload!=="object" || Array.isArray(input.payload) || input.payload.task!==undefined)return input;
 // Canonical local typed discriminator, verified against the installed backend contract.
 return {...input,payload:{...input.payload,task:"asset-search"}};
}
export function terminalSchema(state,sessionID) {
 const v=state.pendingVisual;
 if(v?.presentedBy)return reviewSchema(v);
 return {type:"object",additionalProperties:false,required:["result","session_id","blocker"],properties:{result:{const:"BLOCKED"},session_id:{const:sessionID},blocker:{const:state.lastChildReviewError || (v && !v.presentedBy ? "VISION_MODEL_REQUIRED: exact image presentation is not verified; use a configured verified vision model before pixel review. No model=null receipt or invented observations." : null) || state.lastExecutionError?.message || state.lastGuardError || "Native execution is unavailable at the current guarded boundary; return to the existing coordinator."}}};
}
export function toolRecovery(state,sessionID,options,childState) {
 if(state.simulatedCallBlocked!==state.child || childState?.pendingVisual || childState?.errors || !String(childState?.lastGuardError || "").startsWith("EXTERNAL_GODOT_REGRESSION_REQUIRED:"))return;
 return (options?.toolRecoveryGrants || []).find(g=>g.parentSessionID===sessionID && g.childSessionID===state.child && /^[a-f0-9]{64}$/.test(g.nonce || "") && !(state.consumedToolRecoveryGrants || []).includes(g.nonce));
}


const workerRoles=new Set(["watoom-workflow","watoom-builder"]);
const workerOperations=new Set(["regression","import","capture","capture-scene","capture-p7","poo-vfx-inspect","poo-vfx-export","lmb-qualify"]);
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
 if(Object.keys(v).sort().join(",")!=="images,inputs,output_directory,scene,schema" || v.schema!==1 || !rel(v.scene) || !v.scene.endsWith(".tscn") || !rel(v.output_directory) || !v.output_directory.startsWith(".opencode/captures/") || !Array.isArray(v.inputs) || v.inputs.length<1 || v.inputs.length>128 || new Set(v.inputs).size!==v.inputs.length || !v.inputs.includes(v.scene) || !Array.isArray(v.images) || v.images.length<1 || v.images.length>32 || new Set(v.images).size!==v.images.length || v.images.some(n=>typeof n!=="string" || !/^[A-Za-z0-9][A-Za-z0-9_-]{0,100}\.png$/.test(n)))throw Error("CAPTURE_MANIFEST_INVALID");
 const rows=[];
 for(const name of [...v.inputs].sort()) {const file=posix.join(project,name);if(!rel(name) || await realpath(file)!==file || !(await stat(file)).isFile() || (await stat(file)).size>67108864)throw Error("CAPTURE_INPUT_PATH");rows.push([name,createHash("sha256").update(await readFile(file)).digest("hex")]);}
 return createHash("sha256").update(JSON.stringify([createHash("sha256").update(raw).digest("hex"),rows])).digest("hex");
}

export async function executeGameWorker(ctx,input,context,target="server") {
 if(target==="rig-stage" && !["import","regression","capture","capture-p7","capture-scene"].includes(input.operation))throw Error("RIG_GAME_OPERATION_UNSUPPORTED: use the existing server worker for this specialized operation");
 validateGameWorkerInput(input,context.agent);
 const info=unpack(await ctx.session.get({sessionID:context.sessionID}));
 const directory=info?.location?.directory;
 if(typeof directory!=="string" || !/^\/data\/ai\/projects\/games\/[^/]+$/.test(directory) || await realpath(directory)!==directory)throw Error("GAME_WORKER_PROJECT_DENIED: selected canonical game project required");
 if(!/^[A-Za-z0-9_-]+$/.test(context.sessionID) || !/^[A-Za-z0-9_-]+$/.test(context.messageID) || !/^[A-Za-z0-9_-]+$/.test(context.id))throw Error("GAME_WORKER_CONTEXT_INVALID");
 const folder=posix.join(directory,target==="rig-stage" ? ".opencode/rig-worker-requests" : ".opencode/worker-requests");
 await mkdir(folder,{recursive:true});if(await realpath(folder)!==folder)throw Error("GAME_WORKER_REQUEST_PATH_DENIED");
 const baseFingerprint=await gameSourceFingerprint(directory);
 const source_fingerprint=input.operation==="capture-scene" ? createHash("sha256").update(JSON.stringify([baseFingerprint,await captureSpecFingerprint(directory,input.job)])).digest("hex") : baseFingerprint;
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
 return {content:JSON.stringify({...value,...(target==="rig-stage" ? {job:input.job,worker_target:target,inputs_frozen:value.inputs_frozen===true,source_matches:request.source_fingerprint===source_fingerprint} : {}),note:target==="rig-stage" ? "Background RIG job registered. Continue independent work; do not wait or poll in a loop. Keep this stable job identity. Do not change its source inputs until inputs_frozen:true. Completion is durably queued to this same coordinator; only accept matching source revisions and review actual pixels. A paused RIG retains the queue." : "Request admission is not execution or PASS. Server worker publishes the actual receipt and notifies this existing coordinator; do not poll rapidly or run tests in the app."}),metadata:{request_id:request.request_id,project:directory,operation:input.operation,source_fingerprint:request.source_fingerprint,job:request.job,status:value.status}};
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
export function esp32Project(path) {return path==="/data/ai/projects/esp32";}
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
    editor.add({name:"watoom_esp32",description:"Request/status for isolated ESP32 firmware build and enrolled USB operations. First write .opencode/esp32-jobs/<job>/request.json in /data/ai/projects/esp32. Fixed inventory, build, probe, flash, restore, bounded monitor and serial text; no arbitrary commands. Explicit board identity and flash authorization required. QUEUED means yield; keep stable job and inspect receipts.",options:{codemode:false},input:{type:"object",properties:{action:{type:"string",enum:["request","status"]},job:{type:"string",pattern:"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$",maxLength:64}},required:["action","job"],additionalProperties:false},execute:(input,context)=>executeEsp32(ctx,input,context)});
    editor.add({name:"watoom_asset_capture",description:"Request/status for the external admitted Blender capture worker (server CPU or RIG OptiX/CPU). First write the declarative .opencode/capture-jobs/<job>/request.json in this project. Supports inspect, still, turntable, existing animation, pose-inspect and pose-prepare (fixed installed helper with declarative auto/recipe/qualified rig-adapter/ts4-retarget plan); no arbitrary scripts or shell. Only coordinator/builder. Retain stable job and inspect the returned actual receipt.",options:{codemode:false},input:{type:"object",properties:{action:{type:"string",enum:["request","status"]},job:{type:"string",pattern:"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$",maxLength:64}},required:["action","job"],additionalProperties:false},execute:(input,context)=>executeAssetCapture(ctx,input,context)});
    if(ctx.options?.rigAsyncStage===true)editor.add({name:"watoom_rig_game_job",description:"STAGE: Queue/status a bounded RIG Godot import, regression, capture or capture-scene against a frozen snapshot. The RIG has a real GPU (unlike the Bazzite worker's software-rendered captures); prefer this for a capture-scene job that timed out there. Returns immediately; continue independent work while queued/running. Completion is delivered automatically to the same coordinator. No polling loops, no duplicate jobs, no live source writes, no arbitrary commands. RIG pause preserves jobs. For capture-scene, write .opencode/capture-jobs/<job>/request.json exactly as for the server worker (schema:1, scene, inputs, output_directory under .opencode/captures/, images, optional deadline_sec 60-1080) before requesting; the manifest is validated the same way, but deadline_sec is a wish against the RIG's own ~850s Windows Job Object budget, not a guarantee. Specialized LMB/VFX operations retain the existing server worker.",options:{codemode:false},input:{type:"object",properties:{action:{type:"string",enum:["request","status"]},operation:{type:"string",enum:["import","regression","capture","capture-p7","capture-scene"]},job:{type:"string",pattern:"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$",maxLength:64}},required:["action","operation","job"],additionalProperties:false},execute:(input,context)=>executeGameWorker(ctx,input,context,"rig-stage")});
    editor.add({name:"watoom_game_worker",description:"Request/status of the bounded external Godot worker for this session's game project. Fixed operations only; no shell or paths. For capture-scene first write .opencode/capture-jobs/<job>/request.json with schema:1, project-relative scene, inputs array including its scene/scripts, output_directory under .opencode/captures/, and expected images PNG basenames. Legacy capture runs P6 only; never replace P6 for a custom view. Coordinator/builder only. Stable job, automatic receipt delivery; no rapid polling.",options:{codemode:false},input:{type:"object",properties:{action:{type:"string",enum:["request","status"]},operation:{type:"string",enum:["regression","import","capture","capture-scene","capture-p7","poo-vfx-inspect","poo-vfx-export","lmb-qualify"]},job:{type:"string",pattern:"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$",maxLength:64}},required:["action","operation","job"],additionalProperties:false},execute:(input,context)=>executeGameWorker(ctx,input,context)});
  });
  await ctx.tool.transform(editor=>{
    for (const entry of editor.list()) { if(entry.name==="subagent")continue; editor.update(entry.id,tool=>{
      const original=tool.execute;
      tool.execute=async(input,context)=>{
        input=typedToolkitInput(entry.name,input);
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
          try{assertAllowed(entry.name,input,state,coordinator);}catch(error){
            state.guardRejections=(state.guardRejections || 0)+1;
            if(state.pendingVisual && entry.name==="write" && !reviewReceipt(input,state))
              state.receiptFailures=(state.receiptFailures||0)+1;
            state.lastGuardError=String(error.message);
            if(coordinator && state.guardRejections>=2)state.errors=Math.max(2,state.errors);
            return String(error.message);
          }
          // Nested Code Mode calls share an outer call ID. Count every actual
          // executor invocation, including identical calls, so loops cannot hide.
          state.calls=[...state.calls,identity+"/"+entry.name].slice(-64);
          if(coordinator && !exempt.has(entry.name) && !checkpoint(input)) state.direct++;
          if(state.pendingVisual && entry.name==="read") state.pendingVisual.additionalReads++;
        });
        if(denied)throw new Error(denied);
        try {
          const result=await mirror(await invokeOriginal());
          await transaction(context.sessionID,state=>{
            if(["watoom_game_worker","watoom_rig_game_job","watoom_asset_capture"].includes(entry.name) && result?.metadata?.request_id)state.pendingExternal=["QUEUED","RUNNING","WAITING_FOR_HEADROOM","PAUSED"].includes(result.metadata.status) ? {request_id:result.metadata.request_id,status:result.metadata.status} : null;
            const failed = result?.isError===true || (result?.metadata?.exit !== undefined && result.metadata.exit !== 0);
            if(!failed && entry.name==="skill" && input?.id==="sims")state.simsConversationalIntake=true;
            if(failed){state.lastExecutionError={tool:entry.name,message:"Tool returned failure; exit="+result?.metadata?.exit};state.errors++;if(!coordinator && state.criticConsulted)state.errors=Math.max(2,state.errors);}
            if(coordinator && entry.name==="write" && checkpoint(input) && (state.direct>=BUDGET || state.errors>=2 || state.child))state.gateCheckpointWritten=true;
            const image=imagePart(result);
            if(image) {
              const bytes=Buffer.from(image.uri.slice(image.uri.indexOf(",")+1),"base64");
              const sha256=createHash("sha256").update(bytes).digest("hex");
              if(!state.reviews.some(x=>x.sha256===sha256 && x.reviewVersion===2)) {
                if(state.pendingVisual && state.pendingVisual.sha256!==sha256)throw new Error("VISION_REVIEW_REQUIRED: previous image review remains pending; do not replace it.");
                if(!state.pendingVisual){state.pendingVisual={path:input.path || input.filePath || "tool:"+entry.name,sha256,presentedBy:null,additionalReads:0};state.receiptFailures=0;}
              }
            }
            if(entry.name==="write" && reviewReceipt(input,state)) {
              state.reviews=[...state.reviews,{reviewVersion:2,semanticStatus:"MODEL_REPORTED_SINGLE_FRAME_ONLY",sha256:state.pendingVisual.sha256,path:input.path,model:state.pendingVisual.presentedBy,verdict:JSON.parse(input.content).verdict,receipt:JSON.parse(input.content)}].slice(-16);
              state.pendingVisual=null;state.receiptFailures=0;
            }
          });
          return result;
        } catch(error) {
          await transaction(context.sessionID,state=>{state.lastExecutionError={tool:entry.name,message:String(error.message || error)};state.errors++;if(!coordinator && state.criticConsulted)state.errors=Math.max(2,state.errors);});
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
      if(priorChild?.callingAgent && priorChild.callingAgent!==event.input.agent)throw new Error("CHILD_AGENT_MISMATCH: continue the existing child with agent "+priorChild.callingAgent+" and its exact sessionID.");
      const grant=event.input.sessionID===state.child ? recoveryGrant(state,event.sessionID,ctx.options,priorChild) : null;
      if(grant && visionModels.has(priorChild.pendingVisual.presentedBy)) {
        if(event.input.model!==undefined)throw new Error("CRITIC_MODEL_INHERIT: operator evidence recovery cannot override the selected model.");
        state.consumedRecoveryGrants=[...(state.consumedRecoveryGrants || []),grant.nonce];
        state.childReviewBlocked=false;state.childReviewAttempts=1;
      }
      const toolGrant=event.input.sessionID===state.child ? toolRecovery(state,event.sessionID,ctx.options,priorChild) : null;
      if(toolGrant) {
        const info=unpack(await ctx.session.get({sessionID:state.child}));
        if(info.parentID!==event.sessionID || event.input.model!==undefined)throw new Error("TOOL_RECOVERY_IDENTITY_REQUIRED: exact native child and inherited model required.");
        state.consumedToolRecoveryGrants=[...(state.consumedToolRecoveryGrants || []),toolGrant.nonce];
        state.simulatedCallBlocked=null;state.simulatedCallAttempts[state.child]=0;
        await transaction(state.child,child=>{child.guardRejections=0;child.terminalReport=false;});
      }
      assertAllowed("subagent",event.input,state,event.agent==="watoom-workflow");
      state.childGuardBaseline=priorChild?.guardRejections || 0;
      if(state.childCall)throw new Error("COORDINATOR_SERIAL: another foreground child call is already in flight.");
      state.childCall=event.id;
      } catch(error) {
        state.guardRejections=(state.guardRejections || 0)+1;
        state.lastGuardError=String(error.message);
        if(event.agent==="watoom-workflow" && state.guardRejections>=2)state.errors=Math.max(2,state.errors);
        return String(error.message);
      }
    });
    if(denied)throw new Error(denied);
  });
  await ctx.tool.hook("execute.after",async event=>{
    if(event.tool!=="subagent" || !protectedAgents.has(event.agent))return;
    if(event.status==="error") {
      await transaction(event.sessionID,state=>{state.errors++;if(state.childCall===event.id)state.childCall=null;});return;
    }
    const output=event.result?.output;
    let childReview,error;
    const simulatedCall=output?.status==="completed" && /<tool_call>[\s\S]*?<function[=>]/.test(output.output || "");
    if(simulatedCall)error="NATIVE_TOOL_CALL_REQUIRED: child returned tool-call XML as ordinary text; no command in that text executed. Continue EXISTING child "+output.sessionID+" with its recorded agent, use actual enabled native tools or return an honest structured BLOCKED report. Do not create a replacement child.";
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
        state.direct=0;state.errors=retainedErrors;state.child=null;state.gateCheckpointWritten=false;state.guardRejections=0;state.childReviewAttempts=0;state.childReviewBlocked=false;state.lastChildReviewError=null;
        const completedChild=await ctx.storage.get("session/"+output.sessionID);
        if(event.input.agent!=="watoom-critic" && (completedChild?.guardRejections || 0)-(state.childGuardBaseline || 0)>=2)state.errors=2;
        if(event.input.agent==="watoom-critic")state.criticConsulted=true;
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
    if(state.pendingVisual && visionModels.has(model) && requestContainsImage(body.messages,state.pendingVisual.sha256)) {
      body=isolatedReviewBody(body,state.pendingVisual,model,event.sessionID);
      event.request=new Request(event.request,{body:JSON.stringify(body)});
      await transaction(event.sessionID,s=>{s.presentationInFlight={sha256:s.pendingVisual.sha256,model,url:event.request.url,reviewMode:"isolated-image-v2"};});
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
      if(proof && proof.url===event.request.url && proof.sha256===state.pendingVisual?.sha256 && event.response.ok) {
        state.pendingVisual.presentedBy=proof.model;
        state.pendingVisual.presentationEvidence="exact-image-request-successful-response";
        state.pendingVisual.reviewMode=proof.reviewMode;
      }
      state.presentationInFlight=null;
    });
  });
  await ctx.session.hook("context",async event=>{
    if(!protectedAgents.has(event.agent))return;
    await transaction(event.sessionID,async state=>{
      const coordinator=event.agent==="watoom-workflow";
      reconcileCompletedVisualReview(state,event);
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
      if(ctx.options?.rigAsyncStage===true && workerRoles.has(event.agent))event.system.push({type:"text",text:"RIG BACKGROUND JOBS (stage): prefer native watoom_rig_game_job for fixed Godot jobs and watoom_asset_capture for Blender captures. They return a stable queued identity immediately. Record dependencies and continue independent work; wait only when the next task actually depends on the receipt. Do not poll rapidly or submit duplicate requests. A local operator pause retains the queue. Check inputs_frozen before modifying the requested source; never accept stale receipts or unreviewed pixels."});
      const reason=gate(state,coordinator);
      if(reason) {
        let allowed=reason==="vision" ? new Set(["subagent","read","write"]) : new Set(["subagent"]);
        if(reason!=="vision" && (!state.gateCheckpointWritten || state.pendingVisual))allowed.add("write");
        if(reason==="vision" && state.pendingVisual.additionalReads>=2)allowed.delete("read");
        for(const name of Object.keys(event.tools))if(!allowed.has(name))delete event.tools[name];
      }
      if(!coordinator && (state.guardRejections>=2 || state.errors>=2)) {
        const canWriteReceipt=state.pendingVisual && !["watoom-investigator","watoom-reviewer","watoom-critic"].includes(event.agent) && ((state.receiptFailures||0)<2 || (state.criticConsulted && (state.receiptFailures||0)<3));
        for(const name of Object.keys(event.tools))if(!(name==="write" && canWriteReceipt) && (name!=="subagent" || !criticCallers.has(event.agent) || state.criticConsulted))delete event.tools[name];
        event.system.push({type:"text",text:"CHILD_ESCALATION_REQUIRED: repeated guard rejections. Stop tool retries. Call ONLY watoom-critic as a foreground child, no model override; after one critic review, further failure returns control to coordinator. Return the matching pixel JSON as FINAL if you have seen the pixels, with an additional escalation_required:true, blocker, last_guard_error and failed_attempts fields. Exact last rejection: "+state.lastGuardError+". Do not bypass with OCR or invent causes."});
      }
      if(event.tools.watoom_specialist_run)event.tools.watoom_specialist_run.description=(event.tools.watoom_specialist_run.description || "")+" Local Toolkit asset.search requires payload {task:'asset-search',query:'tree',limit:8}; retain a stable job and use the direct native tool.";
      state.specialistExposure={list:!!event.tools.watoom_specialist_list,run:!!event.tools.watoom_specialist_run,guardReason:reason||null};
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
        if(toolRecovery(state,event.sessionID,ctx.options,childState)) {
          for(const name of Object.keys(event.tools))if(name!=="subagent")delete event.tools[name];
          notes.push("Operator-authorized one-use recovery after correcting parse-only regression classification: resume EXISTING child "+state.child+" with recorded agent and inherited model. Do not replay work or retry a full suite in the app.");
        } else {
          for(const name of Object.keys(event.tools))delete event.tools[name];
          notes.push("HARD STOP: existing child repeatedly returned simulated tool calls. Return BLOCKED with child ID; do not print more tool-call XML or create replacement children.");
        }
      }
      if(!coordinator && criticCallers.has(event.agent))notes.push("Child delegation accepts ONLY agent watoom-critic, background:false, no model override, once per package. Never call explore, general, builder, investigator or workflow. After critic, further failure returns BLOCKED to parent.");
      if(coordinator && state.lastHandoff)notes.push("Resume pointer: last child sessionID "+state.lastHandoff.sessionID+" uses agent "+state.lastHandoff.agent+". Your parent sessionID "+event.sessionID+" is NEVER a subagent resume target.");
      if(coordinator)notes.push("Runtime coordinator guard: after six direct calls delegate a bounded package via native subagent. Only a real completed child resets the budget; compaction/restart/user steering does not. Two execution failures require a critic. No parallel or duplicate child.");
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
      if(reason==="child-critic")notes.push(state.criticConsulted ? "Return BLOCKED to your coordinator/owner: the post-critic repair failed; do not retry tools." : "Two real execution failures require your single foreground critic consultation. Do not perform a third work attempt.");
      if(reason==="critic")notes.push("Critical review is required now: call subagent with agent watoom-critic, background:false, project/checkpoint paths, failed attempts and a precise question. Review evidence before repair.");
      if(state.pendingVisual) {
        const v=state.pendingVisual;
        notes.push("VISION FIRST: actual image "+v.path+" SHA256 "+v.sha256+". Pixel review is pending. Metadata, dimensions, crop scripts and file existence cannot establish visual acceptance. Verified model image presentation: "+(v.presentedBy || "NOT VERIFIED; reread actual image using a verified vision-capable model or report BLOCKED")+". Before continuing other work, "+(["watoom-investigator","watoom-reviewer","watoom-critic"].includes(event.agent) ? "return the matching JSON object as your final reply; do not write files" : "use native write to save .opencode/validation/<task-id>/visual-review.json")+" with image_path, image_sha256, model, basis:pixels, verdict:PASS|FAIL|BLOCKED, and observations (not observed): an array of at least two concrete strings, each at least12 characters after trimming. Use the exact provider-qualified model, never its short alias or the disk file hash. Keep FINAL receipt JSON complete and concise (about1200 characters), not tool-call XML or Markdown. Match the exact path/hash/model above. Do not invent observations. This receipt records model-reported single-frame observations, not proof of artistic correctness. Use review_version2, review_scope single_frame_pixels, framing {usable,issues}, uncertainties and inferences. Keep metadata/technical causes out of pixel observations. If delegating, pass the image path and require the child to read pixels and return its own receipt. A tool call or manifest alone is not a visual review.");
      }
      if(state.pendingVisual && ["watoom-investigator","watoom-reviewer","watoom-critic"].includes(event.agent))
        notes.push("You are read-only: do not write a file or request new permissions. After examining the actual pixels, return ONLY the matching visual-review JSON object as your final reply; the parent guard verifies it against this child's image presentation and records the receipt. If blocked, return BLOCKED with honest observations/limitations; never invent pixel observations.");
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
