import assert from 'node:assert/strict';
import {validateAssetCaptureInput,assetCaptureProject,executeAssetCapture} from './guard-source/index.js';
validateAssetCaptureInput({action:'request',job:'clothed-test'},'watoom-builder');
for(const role of ['watoom-reviewer','watoom-investigator','unknown'])assert.throws(()=>validateAssetCaptureInput({action:'request',job:'j'},role));
for(const v of [{action:'request',job:'../escape'},{action:'request',job:'j',script:'bad'},{action:'render',job:'j'}])assert.throws(()=>validateAssetCaptureInput(v,'watoom-builder'));
assert(assetCaptureProject('/data/ai/projects/images'));assert(!assetCaptureProject('/data/ai/projects/images/../private'));assert(!assetCaptureProject('/tmp'));
console.log('PASS native capture role, schema and selected-project boundaries');

// Session scope is independent of where files were written; deny before any FS access.
for(const action of ['request','status'])for(const directory of ['/tmp','/data/ai/projects/pipelines/staging','/data/ai/projects/images/../private']) {
 const ctx={session:{get:async()=>({data:{location:{directory}}})}};
 await assert.rejects(()=>executeAssetCapture(ctx,{action,job:'neutral-scope-fixture'},{agent:'watoom-builder',sessionID:'neutral',messageID:'neutral',id:'neutral'}),e=>e.message.startsWith('ASSET_CAPTURE_PROJECT_DENIED:') && e.message.includes('session registered project') && e.message.includes('No capture request was registered'));
}
console.log('PASS request/status fail closed for staging and unrelated session projects');
