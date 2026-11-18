import {readFile,writeFile,mkdir} from "node:fs/promises";import path from "node:path";import {hash,sensitive} from "./engine.mjs";import {compact} from "./optimisation.mjs";
// Run with the already installed Bun toolchain, using the actual native parser.
import {parse} from "/data/ai/projects/llm/watoom-code/prompt-builder-20261020/source/packages/core/src/config/plugin/skill-file.ts";
const root=process.argv[2];if(!root?.startsWith("/data/ai/helper-scripts/watoom-self-learning-"))throw Error("Private evidence path required");
const out=path.join(root,"existing-skills"),inventory=JSON.parse(await readFile(path.join(out,"native-inventory.json"),"utf8"));const reports=[];await mkdir(path.join(out,"proposals"),{recursive:true,mode:0o700});
for(const k of inventory.data){
 const body=compact(k.content),front="---\nname: "+JSON.stringify(k.id)+"\ndescription: "+JSON.stringify(k.description||k.name)+"\n---\n";
 const original=parse(out,path.join(out,k.id+".md"),front+k.content),candidate=parse(out,path.join(out,k.id+".md"),front+body);
 const unchangedInstructions=JSON.stringify(k.content.split("\n").filter(l=>l.trim()))===JSON.stringify(body.split("\n").filter(l=>l.trim()));
 const originalParsed=original._tag==="Parsed"&&original.skill.id===k.id,candidateParsed=candidate._tag==="Parsed"&&candidate.skill.id===k.id;
 const record={id:k.id,sourceHash:hash(k.content),candidateHash:hash(body),originalParsed,candidateParsed,unchangedNonblankInstructions:unchangedInstructions,originalBytes:Buffer.byteLength(k.content),candidateBytes:Buffer.byteLength(body),structuralStatus:originalParsed&&candidateParsed&&unchangedInstructions?"PASS":"FAIL",workflowStatus:"TASK_TESTS_REQUIRED",promotion:"BLOCKED_PENDING_PAIRED_TASK_METRICS",secretScan:sensitive(body)?"REVIEW_REQUIRED":"PASS",proposed:body!==k.content};
 if(record.proposed&&!sensitive(body))await writeFile(path.join(out,"proposals",k.id+"-"+record.candidateHash+".md"),front+body,{mode:0o600});reports.push(record);
}
const report={status:reports.every(r=>r.structuralStatus==="PASS")?"STRUCTURAL_PASS_WORKFLOW_PENDING":"FAIL",count:reports.length,proposals:reports.filter(r=>r.proposed).length,promoted:0,tests:reports,limits:"Native parsing and instruction-retention checks are structural baselines. Skill-specific representative tasks, safety/coverage regression receipts and measured paired task benefit remain mandatory before any activation."};
await writeFile(path.join(out,"corpus-validation.json"),JSON.stringify(report,null,2),{mode:0o600});console.log(JSON.stringify({status:report.status,count:report.count,proposals:report.proposals,promoted:0}));if(report.status==="FAIL")process.exitCode=1;
