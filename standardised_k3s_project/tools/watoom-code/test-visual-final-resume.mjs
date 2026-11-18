import assert from 'node:assert/strict';
import {reconcileCompletedVisualReview,resumeAfterReview} from '../../ansible/roles/watoom-code/files/coordinator-guard/index.js';
const hash='a'.repeat(64),model='watoom/tiel-coder-35b-a3b-mtp';const receipt={review_version:2,review_scope:'single_frame_pixels',image_path:'/project/image.png',image_sha256:hash,model,basis:'pixels',verdict:'FAIL',observations:['The ground is visibly almost flat.','No readable creek appears in this frame.'],framing:{usable:false,issues:['The intended subject is absent.']},defects:[],uncertainties:[],inferences:[]};
const state=()=>({direct:6,errors:1,pendingVisual:{path:receipt.image_path,sha256:hash,presentedBy:model,reviewMode:'isolated-image-v2',presentationEvidence:'exact-image-request-successful-response'},reviews:[]});
const event=r=>({agent:'watoom-workflow',sessionID:'ses_fixture',messages:[{role:'assistant',content:[{type:'text',text:'```json\n'+JSON.stringify(r)+'\n```'}]},{role:'user',content:'continue'}]});
let s=state();assert.equal(reconcileCompletedVisualReview(s,event(receipt)),true);assert.equal(s.pendingVisual,null);assert.equal(s.reviews[0].receipt.verdict,'FAIL');assert.equal(s.direct,6);assert.equal(s.errors,1);assert.equal(reconcileCompletedVisualReview(s,event(receipt)),false);assert.equal(s.reviews.length,1);
for(const bad of [{...receipt,image_sha256:'b'.repeat(64)},{...receipt,model:'other'},{...receipt,verdict:'PASS'}])assert.equal(reconcileCompletedVisualReview(state(),event(bad)),false);
s=state();delete s.pendingVisual.presentationEvidence;assert.equal(reconcileCompletedVisualReview(s,event(receipt)),false);
let e=event(receipt);e.messages[0].role='user';assert.equal(reconcileCompletedVisualReview(state(),e),false);
e=event(receipt);e.agent='watoom-builder';assert.equal(reconcileCompletedVisualReview(state(),e),false);
// Hand-back after the review: one note telling the coordinator to continue, not to end with review JSON.
s=state();reconcileCompletedVisualReview(s,event(receipt));assert.deepEqual(s.visualResume,{path:'/project/image.png',verdict:'FAIL',defects:[]});
const withDefects=resumeAfterReview({messages:[{role:'system',content:'base'}]},{path:'/project/image.png',verdict:'FAIL',defects:['Ground is flat green with no texture.']});assert.match(withDefects.messages[0].content,/visible defects: Ground is flat green with no texture\.\).*fix those defects/);
const note=b=>JSON.stringify(b.messages);
let body=resumeAfterReview({messages:[{role:'system',content:'base'},{role:'user',content:'task'}]},s.visualResume);
assert.equal(body.messages.length,2);assert.equal(body.messages[0].role,'system');assert.match(body.messages[0].content,/^base\n\nGuard note: .*\/project\/image\.png.*FAIL.*Continue the task/);
body=resumeAfterReview({messages:[{role:'system',content:[{type:'text',text:'base'}]},{role:'user',content:'task'}]},s.visualResume);
assert.equal(body.messages[0].content.length,2);assert.match(note(body),/side check/);
body=resumeAfterReview({messages:[{role:'user',content:'task'}]},s.visualResume);
assert.equal(body.messages[0].role,'system');assert.equal(body.messages[1].content,'task');
assert.equal(state().visualResume,undefined);
console.log('PASS verified final FAIL releases only the review gate; provenance, role, budget, and deduplication preserved');

// Coordinator hands its review back through a forced guard tool so the turn continues.
{
 const {isolatedReviewBody,receiptAsWrite,reviewReceipt,VISUAL_RECEIPT_TOOL}=await import('../../ansible/roles/watoom-code/files/coordinator-guard/index.js');
 const png='data:image/png;base64,iVBORw0KGgo=';
 const {createHash}=await import('node:crypto');
 const sha=createHash('sha256').update(Buffer.from(png.slice(png.indexOf(',')+1),'base64')).digest('hex');
 const pending={path:'/data/ai/projects/games/x/renders/a.png',sha256:sha};
 const body={messages:[{role:'user',content:[{type:'image_url',image_url:{url:png}}]}],tools:[{type:'function',function:{name:'write'}}]};
 const co=isolatedReviewBody(body,pending,'watoom/m','s1','watoom-workflow');
 assert.equal(co.tools.length,1);assert.equal(co.tools[0].function.name,VISUAL_RECEIPT_TOOL);
 assert.equal(co.tool_choice.function.name,VISUAL_RECEIPT_TOOL);assert.equal(co.response_format,undefined);
 assert.equal(co.tools[0].function.parameters.anyOf,undefined);assert.deepEqual(co.tools[0].function.parameters.properties.verdict.enum,["PASS","FAIL","BLOCKED"]);
 const ch=isolatedReviewBody(body,pending,'watoom/m','s1','watoom-builder');
 assert.equal(ch.tools[0].function.name,'write');
 const receipt={review_version:2,review_scope:'single_frame_pixels',image_path:pending.path,image_sha256:sha,model:'watoom/m',basis:'pixels',verdict:'FAIL',observations:['grey flat field at the bottom','small dark object at centre left'],framing:{usable:true,issues:[]},defects:['large flat single colour surface with no texture'],uncertainties:[],inferences:[]};
 const st={pendingVisual:{...pending,presentedBy:'watoom/m',reviewMode:'isolated-image-v2'}};
 assert.equal(reviewReceipt(receiptAsWrite(receipt,st),st),true);
 const {verdict,...bad}=receipt;
 assert.equal(reviewReceipt(receiptAsWrite(bad,st),st),false);
}

// The registered receipt tool must return the {content,metadata} shape every other guard tool uses;
// {output} was rejected by the host ("output without an output schema") and ended the turn.
{
 const src=(await import('node:fs')).readFileSync(new URL('../../ansible/roles/watoom-code/files/coordinator-guard/index.js',import.meta.url),'utf8');
 const m=src.match(/name:VISUAL_RECEIPT_TOOL,[^\n]*execute:async\(\)=>\((\{.*?\})\)\}\);/);
 assert.ok(m,'receipt tool registration found');
 const r=eval('('+m[1]+')');
 assert.equal(typeof r.content,'string');assert.equal(r.output,undefined);
}
