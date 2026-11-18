import {hash,sensitive} from "./engine.mjs";
// Existing Skill revisions are immutable. Selection changes take effect only in
// a new plugin instance after the deployment controller obtains its idle fence.
export class Optimisation {
 constructor({storage,scope,artifacts,now=()=>new Date().toISOString()}){Object.assign(this,{storage,scope,artifacts,now});this.key="optimisation/v1/"+hash(scope);this.serial=Promise.resolve();}
 async state(){await this.serial.catch(()=>{});return await this.storage.get(this.key)||{schema:1,skills:{},revisions:{},sessions:{},events:{},comparisons:{},history:[]};}
 async transaction(fn){const p=this.serial.catch(()=>{}).then(async()=>{const s=await this.storage.get(this.key)||{schema:1,skills:{},revisions:{},sessions:{},events:{},comparisons:{},history:[]};const r=await fn(s);s.scope??=this.scope;await this.storage.set(this.key,s);return r;});this.serial=p;return p;}
 async inventory(list){return this.transaction(async s=>{
  for(const k of list){const digest=hash(k.content),revision="existing-"+hash([this.scope,k.id,digest]);
   if(!s.revisions[revision]){if(sensitive(k.content)){s.skills[k.id]={...(s.skills[k.id]||{}),id:k.id,status:"BLOCKED_SENSITIVE",sha256:digest,baseline:null,active:null,baselineTests:null,sourceChanged:true,metrics:s.skills[k.id]?.metrics||{loads:0,failedLoads:0,attempts:0,failures:0,repeats:0,verifiedSuccesses:0,corrections:0}};continue;}
    const path=await this.artifacts.write(revision,k.content);s.revisions[revision]={id:revision,skill:k.id,sha256:digest,path,bytes:Buffer.byteLength(k.content),state:"baseline",created:this.now(),previous:null};}
   const old=s.skills[k.id];s.skills[k.id]={...old,id:k.id,name:k.name,description:k.description||"",source:k.path,sha256:digest,baseline:revision,status:"INVENTORIED",baselineTests:old?.sha256===digest?old.baselineTests:null,metrics:old?.metrics||{loads:0,failedLoads:0,attempts:0,failures:0,repeats:0,verifiedSuccesses:0,corrections:0},sourceChanged:Boolean(old&&old.sha256!==digest)};
   if(old?.sha256!==digest)s.skills[k.id].active=null;
   for(const r of Object.values(s.revisions))if(r.skill===k.id&&["candidate","evaluated"].includes(r.state)&&r.previous!==(s.skills[k.id].active||revision)){
    r.state="superseded";r.supersededBy=revision;r.retiredAt=this.now();
   }
  }return Object.keys(s.skills).length;
 });}
 async observe(e){return this.transaction(s=>{
  const event=hash([e.sessionID,e.messageID,e.id,e.tool]);if(s.events[event])return;s.events[event]=true;
  const session=s.sessions[e.sessionID]??={loaded:[],commands:{},failed:[],outcomes:[]};
  if(e.tool==="skill") {const k=s.skills[e.input?.id];if(!k)return;k.metrics??={loads:0,failedLoads:0,attempts:0,failures:0,repeats:0,verifiedSuccesses:0,corrections:0};const ok=e.status==="completed"&&e.result?.isError!==true;k.metrics[ok?"loads":"failedLoads"]++;if(ok&&!session.loaded.includes(k.id))session.loaded.push(k.id);return;}
  if(!session.loaded.length)return;
  // Persist fingerprints, never commands, arguments, output, prompts or secrets.
  const signature=hash([e.tool,e.input]);const failed=e.status!=="completed"||e.result?.isError===true||Number(e.result?.metadata?.exit||0)!==0;
  for(const id of session.loaded){const m=s.skills[id].metrics;m.attempts++;if(failed)m.failures++;if(session.commands[signature])m.repeats++;}
  session.commands[signature]=(session.commands[signature]||0)+1;
  if(failed)session.failed.push({event,signature,tool:e.tool});
 });}
 async verified({sessionID,receipt,success,correctionOf=[],correctionSignature,lesson}){if(!receipt||typeof success!=="boolean")throw Error("Independent verifier receipt required");return this.transaction(s=>{
  const session=s.sessions[sessionID];if(!session||session.outcomes.includes(receipt))return;
  if(correctionSignature)correctionOf=session.failed.filter(f=>f.signature===correctionSignature&&!f.resolved).map(f=>f.event);
  if(lesson&&sensitive(lesson))throw Error("Sensitive correction lesson rejected");
  if(correctionOf.some(id=>!session.failed.some(f=>f.event===id)))throw Error("Correction does not reference a recorded failed attempt");
  session.outcomes.push(receipt);for(const id of session.loaded){const m=s.skills[id].metrics;if(success)m.verifiedSuccesses++;if(success&&correctionOf.length){m.corrections++;const k=s.skills[id];k.lessons??=[];if(lesson&&!k.lessons.some(l=>l.hash===hash(lesson)))k.lessons.push({hash:hash(lesson),text:lesson,receipt,failures:correctionOf});}}
  if(success)for(const failed of session.failed)if(correctionOf.includes(failed.event))failed.resolved=receipt;
 });}
 async baseline(id,report){return this.transaction(s=>{const k=s.skills[id];if(!k||report.hash!==k.sha256||!report.cases?.length||report.cases.some(c=>!c.id||!c.task||!c.regression||!c.receipt||typeof c.correctness!=="boolean"||typeof c.safety!=="boolean"||!Array.isArray(c.coverage)||!c.coverage.length))throw Error("Representative task and regression receipts required");if(k.baselineTests?.hash===k.sha256&&k.baselineTests.cases.some(old=>!report.cases.some(c=>c.id===old.id)))throw Error("Established baseline coverage cannot be dropped");k.baselineHistory??=[];if(k.baselineTests)k.baselineHistory.push(k.baselineTests);k.baselineTests=structuredClone(report);});}
 async propose(){return this.transaction(async s=>{
  const result=[];
  for(const k of Object.values(s.skills).filter(k=>k.baseline&&k.id!=="report").sort((a,b)=>score(b)-score(a)||a.id.localeCompare(b.id))){
   const old=s.revisions[k.active||k.baseline],body=await this.artifacts.read(old.path);
   // Conservative automatic proposal: remove repeated blank lines outside code
   // fences; preserve every nonblank line and fenced byte exactly. A byte saving
   // is recorded, never presented as measured token or workflow improvement.
   const appendix=(k.lessons||[]).filter(l=>!body.includes(l.text)).map(l=>"- "+l.text+" (verified receipt "+l.receipt+")").join("\n");
   const candidate=compact(body)+(appendix?"\n\n## Verified recovery notes for evaluation\n"+appendix+"\n":"");if(candidate===body)continue;
   const id="revision-"+hash([k.id,old.sha256,candidate]);if(s.revisions[id])continue;
   const path=await this.artifacts.write(id,candidate);s.revisions[id]={id,skill:k.id,sha256:hash(candidate),path,bytes:Buffer.byteLength(candidate),previous:old.id,state:"candidate",method:"outside-fence-blank-line-compaction",created:this.now(),byteSaving:Buffer.byteLength(body)-Buffer.byteLength(candidate)};result.push(id);
  }return result;
 });}
 async compare(id,report){return this.transaction(s=>{
  const candidate=s.revisions[id],k=s.skills[candidate?.skill];if(!candidate||!k?.baselineTests||k.sourceChanged)throw Error("Tested unchanged baseline required");
  if(report.baselineHash!==s.revisions[candidate.previous].sha256||report.candidateHash!==candidate.sha256||!report.environment||!report.cases?.length)throw Error("Paired replay identity required");
  const expected=k.baselineTests.cases.map(c=>c.id).sort();if(JSON.stringify(report.cases.map(c=>c.id).sort())!==JSON.stringify(expected))throw Error("Representative/regression coverage reduced");
  let benefit=false;const metrics=["tokens","repeatedCommands","failedAttempts","latencyMs"];
  for(const c of report.cases){const baseline=k.baselineTests.cases.find(x=>x.id===c.id);if(c.task!==baseline.task||c.regression!==baseline.regression||!c.original?.receipt||!c.candidate?.receipt||c.original.receipt===c.candidate.receipt)throw Error("Independent paired task receipts required");
   if(c.original.correctness!==baseline.correctness||c.original.safety!==baseline.safety||c.candidate.correctness!==true||c.candidate.safety!==true)throw Error("Correctness or safety regressed");
   for(const arm of [c.original,c.candidate])if(!Array.isArray(arm.coverage)||baseline.coverage.some(x=>!arm.coverage.includes(x)))throw Error("Coverage regressed");
   if(c.original.correctness===false||c.original.safety===false)benefit=true;
   for(const metric of metrics){const a=c.original[metric],b=c.candidate[metric];if(a==null&&b==null)continue;if(!Number.isFinite(a)||!Number.isFinite(b)||a<0||b<0||b>a)throw Error("Measured metric regressed or missing");if(b<a)benefit=true;}
  }
  if(!benefit)throw Error("No measured task benefit; byte savings alone are insufficient");
  s.comparisons[id]=structuredClone(report);candidate.state="evaluated";return candidate;
 });}
 async select(id,fence){if(fence?.nativeGateHeld!==true||fence?.activeSessions!==0||fence?.rolloutAtIdle!==true)throw Error("Verified idle deployment fence required");return this.transaction(async s=>{
  const r=s.revisions[id],k=s.skills[r?.skill];if(!r||r.state!=="evaluated"||!s.comparisons[id]||k.sourceChanged||r.previous!==(k.active||k.baseline))throw Error("Unproven revision");
  if(hash(await this.artifacts.read(r.path))!==r.sha256)throw Error("Candidate integrity failed");r.previous=k.active||k.baseline;k.active=id;r.state="selected-next-start";s.history.push({action:"select",id,previous:r.previous,time:this.now()});
 });}
 async regression(id,receipt){if(!receipt)throw Error("Regression receipt required");return this.transaction(s=>{const r=s.revisions[id],k=s.skills[r?.skill];if(!r||k.active!==id)return;r.state="rollback-pending";k.pendingRollback=r.previous;s.history.push({action:"automatic-rollback-requested",id,receipt,time:this.now()});});}
 async rollback(id,fence){if(fence?.nativeGateHeld!==true||fence?.activeSessions!==0||fence?.rolloutAtIdle!==true)throw Error("Verified idle deployment fence required");return this.transaction(async s=>{const k=s.skills[id],old=s.revisions[k?.pendingRollback];if(!old||hash(await this.artifacts.read(old.path))!==old.sha256)throw Error("Previous immutable revision unavailable");k.active=old.state==="baseline"?null:old.id;k.pendingRollback=null;s.history.push({action:"rollback-next-start",id,previous:old.id,time:this.now()});});}
 async frozenOverrides(allowed=null){const s=await this.state(),out=[];for(const k of Object.values(s.skills)){
  const ids=allowed===null?[k.active]:allowed.filter(id=>s.revisions[id]?.skill===k.id);if(ids.length>1)throw Error("Ambiguous existing Skill selection");const r=s.revisions[ids[0]];
  if(!r||(k.pendingRollback&&r.id===k.active)||k.sourceChanged)continue;const content=await this.artifacts.read(r.path);if(hash(content)!==r.sha256)continue;out.push({id:k.id,sourceHash:k.sha256,content,revision:r.id});}return out;}
 async account(sessionID,tokens,cost){return this.transaction(s=>{
  const session=s.sessions[sessionID];if(!session?.loaded.length)return;
  const current={input:tokens?.input,output:tokens?.output,reasoning:tokens?.reasoning,cacheRead:tokens?.cache?.read,cacheWrite:tokens?.cache?.write,cost};
  if(Object.values(current).some(v=>!Number.isFinite(v)||v<0))throw Error("Native token accounting unavailable");
  const previous=session.accounted||{};
  for(const id of session.loaded){const k=s.skills[id];k.sessionCost??={input:0,output:0,reasoning:0,cacheRead:0,cacheWrite:0,cost:0};for(const [key,value] of Object.entries(current))k.sessionCost[key]+=Math.max(0,value-(previous[key]||0));k.measuredSessionTokens=k.sessionCost.input+k.sessionCost.output+k.sessionCost.reasoning;}
  session.accounted=current;
 });}
 async priorities(){const s=await this.state();return Object.values(s.skills).map(k=>({id:k.id,...k.metrics,sessionCost:k.sessionCost||null,priority:(k.metrics?.loads||0)+5*(k.metrics?.failures||0)+2*(k.metrics?.repeats||0)+(k.measuredSessionTokens||0)/1000,baseline:k.baselineTests?(k.baselineTests.scope==="structural-contract"?"CONTRACT_TESTED_DOMAIN_PENDING":"TASK_TESTED"):"TASK_TESTS_REQUIRED",costAttribution:"shared session cost; not causal per-Skill cost"})).sort((a,b)=>b.priority-a.priority||a.id.localeCompare(b.id));}
}
export function compact(body){let fence=null,blank=false;return body.split("\n").filter(line=>{const m=line.match(/^\s{0,3}(`{3,}|~{3,})(.*)$/);if(m){if(!fence)fence={char:m[1][0],length:m[1].length};else if(m[1][0]===fence.char&&m[1].length>=fence.length&&!m[2].trim())fence=null;blank=false;return true;}if(fence)return true;if(line.trim()){blank=false;return true;}if(blank)return false;blank=true;return true;}).join("\n");}

function score(k){return (k.metrics?.loads||0)+5*(k.metrics?.failures||0)+2*(k.metrics?.repeats||0)+(k.measuredSessionTokens||0)/1000;}
