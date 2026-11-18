# Neutral native-input repair -> real MCP HTTP -> durable queue; no worker.
import json,subprocess,tempfile,threading,unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from server import Application
class ScopeTransport(unittest.TestCase):
 def test_model_omissions_are_corrected_before_real_queue_insertion(self):
  with tempfile.TemporaryDirectory() as tmp:
   app=Application(tmp,"fixture-password","http://localhost",image_mcp_token="fixture-token");app.operations=object()
   record={"id":"a"*64,"revision":"b"*40,"kind":"diffusion-pipeline","registered":True,"settings":{},"repository":"fixture/sdxl"}
   with app.store.db:app.store.db.execute("INSERT INTO models VALUES(?,?,?)",(record["id"],record["revision"],json.dumps(record)))
   server=ThreadingHTTPServer(("127.0.0.1",0),app.handler());thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
   script=Path(tmp)/"fixture.mjs";module=Path(__file__).resolve().parents[2]/"ansible/roles/watoom-code/files/image-scope/index.js"
   script.write_text('import { install } from '+json.dumps(module.as_uri())+';\n'+r"""
let hook;const source="Positive prompt:\nA wooden bench in a quiet park. outdoors\n\nNegative prompt:\nwatermark, blur\n\nExecution settings:\nTask: Create 3 images.\n\nSpecification:\n- Number of images: 3\n";
await install({tool:{async hook(n,f){if(n==="execute.before")hook=f;}},session:{async get(){return {id:"ses_fixture"};},async context(){return [{id:"usr_fixture",type:"user",text:source}];}},storage:{async set(){}}});
for(let i=0;i<3;i++){
 const event={tool:"watoom-images_submit_image",sessionID:"ses_fixture",id:"call_fixture_"+i,input:{request_id:"scope-fixture-"+i,installation_id:"a".repeat(64),revision:"b".repeat(40),prompt:["A wooden bench in a quiet park, front view.","A wooden bench in a quiet park, side view.","A wooden bench in a quiet park, rear view."][i],settings:{seed:0}}};
 await hook(event);
 const response=await fetch(process.argv[2],{method:"POST",headers:{"Authorization":"Bearer fixture-token","Content-Type":"application/json"},body:JSON.stringify({jsonrpc:"2.0",id:i,method:"tools/call",params:{name:"submit_image",arguments:event.input,_meta:{"ai.opencode/sessionID":"ses_fixture"}}}),signal:AbortSignal.timeout(5000)});
 const result=await response.json();if(!response.ok||result.result?.isError||!result.result?.structuredContent?.job_id)throw Error("Fixture submission failed");
}
console.log("PASS neutral three-job HTTP transport");
""")
   try:
    result=subprocess.run(["node",str(script),"http://127.0.0.1:"+str(server.server_address[1])+"/mcp"],capture_output=True,text=True,timeout=20)
    self.assertEqual(result.returncode,0,result.stderr)
    rows=app.store.jobs();self.assertEqual(len(rows),3)
    for row in rows:
     selection=json.loads(row["selection"]);self.assertIn(selection["prompt"],["A wooden bench in a quiet park, front view.","A wooden bench in a quiet park, side view.","A wooden bench in a quiet park, rear view."]);self.assertEqual(selection["negative_prompt"],"watermark, blur");self.assertEqual(row["state"],"QUEUED")
    self.assertEqual(len({json.loads(row["selection"])["prompt"] for row in rows}),3)
    self.assertEqual(app.store.db.execute("SELECT count(*) FROM image_request_sessions WHERE session_id='ses_fixture'").fetchone()[0],3)
   finally:server.shutdown();server.server_close();thread.join();app.store.close()
