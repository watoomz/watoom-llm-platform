import {lstat,readFile,realpath} from "node:fs/promises";
import path from "node:path";
import {resultText,hash} from "./engine.mjs";
export async function verifyWorker(policy,event,scope,fingerprint,io={lstat,readFile,realpath}){
 if(policy.verifier!=="native-cpu-worker-v1"||event.tool!=="watoom_game_worker"||event.input?.action!=="status"||!["import","regression"].includes(event.input.operation))return false;
 let value;try{value=JSON.parse(resultText(event.result)||"");}catch{return false;}
 if(!/^[a-f0-9]{64}$/.test(value.request_id||"")||value.project!==scope.repository||value.operation!==event.input.operation||value.source_matches!==true||value.status!=="COMPLETED"||value.worker_result?.status!=="PASS")return false;
 if(!/^\/data\/ai\/projects\/games\/[^/]+$/.test(scope.repository))return false;
 const file=path.join(scope.repository,".opencode/worker-requests",value.request_id+".status.json");
 try{
  const st=await io.lstat(file);if(!st.isFile()||st.isSymbolicLink()||st.uid!==0||(st.mode&0o022)||st.size>65536||await io.realpath(file)!==file)return false;
  const owned=JSON.parse(await io.readFile(file,"utf8"));
  for(const key of ["request_id","project","operation","source_fingerprint","status","receipt"])if(owned[key]!==value[key])return false;
  if(typeof fingerprint!=="function"||await fingerprint(scope.repository)!==owned.source_fingerprint)return false;
  if(owned.status!=="COMPLETED"||JSON.stringify(owned.worker_result)!==JSON.stringify(value.worker_result))return false;
  const receipt=value.receipt;
  if(typeof receipt!=="string"||!receipt.startsWith(scope.repository+"/.opencode/validation/operator-godot/")||await io.realpath(receipt)!==receipt)return false;
  const rs=await io.lstat(receipt);if(!rs.isFile()||rs.isSymbolicLink()||rs.uid!==0||(rs.mode&0o022)||rs.size>262144)return false;
  const raw=await io.readFile(receipt,"utf8"),r=JSON.parse(raw);
  if(r.status!=="PASS")return false;
  if(event.input.operation==="import"&&(r.source_unchanged!==true||!Array.isArray(r.errors)||r.errors.length))return false;
  if(event.input.operation==="regression"&&(r.original_project_untouched!==true||r.live_source_still_matches_snapshot!==true||r.runtime_error_count!==0||r.summary?.failed!==0||r.summary?.passed<1||r.exit_status!=="0"))return false;
  return {id:"native-worker:"+value.request_id,receiptHash:hash(raw),receipt};
 }catch{return false;}
}
