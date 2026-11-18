import assert from 'node:assert/strict';
import {criticRecovery} from '../../ansible/roles/watoom-code/files/coordinator-guard/index.js';
const parent='ses_parentAAAA',child='ses_childBBBB',n1='a'.repeat(64),n2='b'.repeat(64),now=Date.parse('2026-10-29T00:00:00Z');
const blocked=()=>({child,simulatedCallBlocked:child,simulatedCallAttempts:{[child]:2}});
const critic={callingAgent:'watoom-critic'};
const grant=(nonce,extra={})=>({parentSessionID:parent,childSessionID:child,agent:'watoom-critic',nonce,...extra});
// Any session pair named by a grant is eligible; nothing is hard-coded.
assert.equal(criticRecovery(blocked(),parent,{criticRecoveryGrants:[grant(n1)]},critic,now)?.nonce,n1);
assert.equal(criticRecovery(blocked(),'ses_other',{criticRecoveryGrants:[grant(n1)]},critic,now),undefined);
// Preconditions still gate every grant.
assert.equal(criticRecovery({...blocked(),simulatedCallAttempts:{[child]:1}},parent,{criticRecoveryGrants:[grant(n1)]},critic,now),undefined);
assert.equal(criticRecovery(blocked(),parent,{criticRecoveryGrants:[grant(n1)]},{callingAgent:'watoom-builder'},now),undefined);
assert.equal(criticRecovery(blocked(),parent,{criticRecoveryGrants:[grant('short')]},critic,now),undefined);
// Expiry is honoured when present; malformed expiry fails closed.
assert.equal(criticRecovery(blocked(),parent,{criticRecoveryGrants:[grant(n1,{expiresAt:'2026-10-30T00:00:00Z'})]},critic,now)?.nonce,n1);
assert.equal(criticRecovery(blocked(),parent,{criticRecoveryGrants:[grant(n1,{expiresAt:'2026-10-28T00:00:00Z'})]},critic,now),undefined);
assert.equal(criticRecovery(blocked(),parent,{criticRecoveryGrants:[grant(n1,{expiresAt:'soon'})]},critic,now),undefined);
// One use: a consumed grant is never reused, and a plain second grant is refused.
const consumed={...blocked(),criticRecoveryConsumed:true,consumedCriticRecoveryGrants:[n1],
  criticRecoveryHistory:[{child,nonce:n1,status:'native-error',accepted:false,error:'NATIVE_SUBAGENT_ERROR'}]};
assert.equal(criticRecovery(consumed,parent,{criticRecoveryGrants:[grant(n1)]},critic,now),undefined);
assert.equal(criticRecovery(consumed,parent,{criticRecoveryGrants:[grant(n2)]},critic,now),undefined);
// A follow-up grant applies only after that exact nonce ended in a native subagent error.
assert.equal(criticRecovery(consumed,parent,{criticRecoveryGrants:[grant(n2,{afterNativeErrorOf:n1})]},critic,now)?.nonce,n2);
const completed={...consumed,criticRecoveryHistory:[{...consumed.criticRecoveryHistory[0],status:'completed',accepted:true,error:undefined}]};
assert.equal(criticRecovery(completed,parent,{criticRecoveryGrants:[grant(n2,{afterNativeErrorOf:n1})]},critic,now),undefined);
const twice={...consumed,criticRecoveryHistory:[...consumed.criticRecoveryHistory,consumed.criticRecoveryHistory[0]]};
assert.equal(criticRecovery(twice,parent,{criticRecoveryGrants:[grant(n2,{afterNativeErrorOf:n1})]},critic,now),undefined);
assert.equal(criticRecovery({...consumed,consumedCriticRecoveryGrants:[n1,n2]},parent,{criticRecoveryGrants:[grant(n2,{afterNativeErrorOf:n1})]},critic,now),undefined);
console.log('PASS critic recovery grants are data-driven, one-use, expiring and follow-up only after a native error');
