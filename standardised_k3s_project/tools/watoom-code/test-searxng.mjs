import assert from "node:assert/strict";
import plugin, {search} from "../../ansible/roles/watoom-code/files/native/plugins/searxng-search/index.js";
let registered;
await plugin.setup({websearch:{transform:async fn=>fn({add:x=>registered=x})}});
assert.equal(registered.id,"searxng");assert.equal(typeof registered.execute,"function");
const result = {url:"https://example.com",title:"Example",content:"sample"};
const response = (results=[], errors=[]) => new Response(JSON.stringify({results,unresponsive_engines:errors}));
const mock=async url=>{assert.equal(url.searchParams.get("q"),"test");return response([result,{url:"https://example.com"},{url:"file:///etc/passwd"},{url:"bad"}]);};
assert.deepEqual(await search(" test ",undefined,mock),[{url:"https://example.com/",title:"Example",content:"sample",time:{}}]);
await assert.rejects(()=>search(" ",undefined,mock));
await assert.rejects(()=>search("test",undefined,async()=>new Response("{}",{status:503})),/503/);
await assert.rejects(()=>search("test",undefined,async()=>new Response("{}")),/Invalid/);
await assert.rejects(()=>search("test",undefined,async()=>new Response("no JSON")));

let calls=[], signals=[];
const original="Arduino-ESP32 2.0.10 EspClass getPsramFreeSize getFreeHeap getTotalHeap API";

const recovered=await search(original,undefined,async(url,options)=>{
  calls.push(url.searchParams.get("q")); signals.push(options.signal);
  return response(calls.length===3?[result]:[],[["brave","too many requests"]]);
});
assert.deepEqual(calls,[original,"Arduino ESP32 EspClass getPsramFreeSize","Arduino ESP32"]);
assert.ok(signals.every(s=>s===signals[0]),"retries must share a deadline");
assert.match(recovered[0].content,/Search broadened from/);
assert.match(recovered[0].content,/verify relevance/);
assert.equal(recovered[0].url,"https://example.com/");

calls=[];
await assert.rejects(()=>search(original,undefined,async url=>{
  calls.push(url.searchParams.get("q"));return response([],[["duckduckgo","CAPTCHA"]]);
}),/3 attempt\(s\).*duckduckgo: CAPTCHA/);
assert.equal(calls.length,3);
calls=[];
await assert.rejects(()=>search("one two three",undefined,async url=>{
  calls.push(url.searchParams.get("q"));return response([{url:"file:///etc/passwd"}]);
}),/no usable results/);
assert.deepEqual(calls,["one two three","one two"]);

calls=[];
const ac=new AbortController();
await assert.rejects(()=>search(original,ac.signal,async url=>{
  calls.push(url.searchParams.get("q"));ac.abort();return response();
}),{name:"AbortError"});
assert.equal(calls.length,1,"cancellation must prevent retry");
let count=0;
await assert.rejects(()=>search(original,undefined,async()=>{count++;return new Response("{}",{status:503});}),/503/);
assert.equal(count,1,"outages must not trigger broad-query retries");
calls=[];
await search('"ESP32 memory" getFreeHeap getPsramSize example',undefined,async url=>{
  calls.push(url.searchParams.get("q"));return response(calls.length===2?[result]:[]);
});
assert.deepEqual(calls,['"ESP32 memory" getFreeHeap getPsramSize example','"ESP32 memory" getFreeHeap']);
console.log("PASS registration, direct results, URL filtering, validation, bounded fallback, provenance, engine errors, cancellation and outage behavior");
