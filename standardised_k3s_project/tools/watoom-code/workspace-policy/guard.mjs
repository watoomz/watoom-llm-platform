import fs from "node:fs";
import path from "node:path";
const reads = new Set(["read","glob","grep","ls","skill","watoom_skill_search","question","watoom_workspace_status","watoom_specialist_list","watoom_learning_status"]);
export function safePath(raw, root) {
  if(typeof raw!=="string" || !raw || raw.includes("\0")) return false;
  const base=fs.realpathSync(root), target=path.resolve(base,raw);
  if(target!==base && !target.startsWith(base+path.sep)) return false;
  const relative=path.relative(base,target);
  if(relative.split(path.sep).some(x=>x===".git") || /^(?:opencode\.jsonc?|\.watoom-workspace\.json)$/.test(relative))return false;
  if(relative.startsWith(".opencode/") && !/^\.opencode\/(?:work|artifacts)(?:\/|$)/.test(relative))return false;
  let existing=target;
  while(true){try{fs.lstatSync(existing);break;}catch(error){if(error.code!=="ENOENT")return false;const parent=path.dirname(existing);if(parent===existing)return false;existing=parent;}}
  let resolved;try{resolved=fs.realpathSync(existing);}catch{return false;}
  return resolved===base || resolved.startsWith(base+path.sep);
}
export function assess(name,args,root) {
  if(reads.has(name))return true;
  if(name==="subagent")return !args?.directory || path.resolve(args.directory)===root;
  if(!["write","edit"].includes(name))return false;
  const keys=["filePath","file_path","path"].filter(k=>Object.hasOwn(args??{},k));
  return keys.length===1 && safePath(args[keys[0]],root);
}
export async function resolveBoundary(id,lookup,policy,seen=new Set()) {
  if(seen.size>16 || seen.has(id))throw Error("WORKSPACE_PARENT_CHAIN_INVALID");
  seen.add(id);const session=await lookup(id);
  if(!session)throw Error("WORKSPACE_SESSION_UNKNOWN");
  if(session.parentID){
    const parent=await resolveBoundary(session.parentID,lookup,policy,seen);
    if(parent && session.location?.directory!==parent.root)throw Error("WORKSPACE_CHILD_LOCATION_MISMATCH");
    return parent;
  }
  const directory=session.location?.directory;
  if(directory!==policy.root && !directory?.startsWith(policy.root+"/"))return null;
  if((session.time?.created??0)<policy.enrollAfter)return null;
  if(fs.realpathSync(policy.root)!==policy.root)throw Error("WORKSPACE_ROOT_SYMLINK");
  return {root:policy.root,sessionID:id};
}
export async function install(ctx) {
  const policy=JSON.parse(fs.readFileSync(ctx.options.policy,"utf8"));
  if(policy.version!==2 || typeof policy.enrollAfter!=="number" || !path.isAbsolute(policy.root))throw Error("WORKSPACE_POLICY_INVALID");
  const lookup=async id=>{const value=await ctx.session.get({sessionID:id});return value?.data??value;};
  // The native pre-execution hook also covers tools registered after this plugin.
  await ctx.tool.hook("execute.before",async event=>{
    const boundary=await resolveBoundary(event.sessionID,lookup,policy);
    if(boundary && !assess(event.tool,event.input,boundary.root))throw Error("WORKSPACE_DENIED: unmediated execution/write route; use direct read/write/edit inside the registered checkout. Shell, code, delegates and workers require a separately qualified sandbox.");
  });
  await ctx.session.hook("context",async event=>{
    const boundary=await resolveBoundary(event.sessionID,lookup,policy);
    if(!boundary)return;
    for(const name of Object.keys(event.tools))if(!reads.has(name) && !["write","edit","subagent"].includes(name))delete event.tools[name];
    event.system.push({type:"text",text:"Homelab/LLM workspace is enrolled: "+boundary.root+". Direct edits only in this checkout; .git and runtime config are protected. Children inherit this boundary. Shell/code/delegate/worker execution is intentionally unavailable until an OS-sandboxed route is qualified. Do not ask approval to bypass this guard. Model integration is operator-reviewed dev only, never main. This is tool mediation, not an OS sandbox."});
  });
}
export default {id:"watoom.homelab-workspace",setup:install};
