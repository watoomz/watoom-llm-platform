"""Deterministic CPU provider for native-hook acceptance; no inference."""
import http.server,json,time,pathlib,hashlib
class Handler(http.server.BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  b=json.dumps({"data":[{"id":"cpu-fixture","object":"model","owned_by":"fixture"}]}).encode();self.send_response(200);self.end_headers();self.wfile.write(b)
 def do_POST(self):
  start=time.monotonic();d=json.loads(self.rfile.read(int(self.headers['Content-Length'])));messages=d.get('messages',[]);tools=d.get('tools',[])
  lastuser=next((str(x.get('content','')) for x in reversed(messages) if x.get('role')=='user'),"")
  toolname="watoom_learning_status" if "STATUS" in lastuser else "watoom_learning_fixture"
  skill=None
  for m in messages:
   text=str(m.get('content',''))
   import re
   found=re.search(r'"id":\s*"(learned-[a-z0-9-]+)"',text)
   if found:skill=found.group(1)
  tool_messages=[x for x in messages if x.get('role')=='tool']
  called=[t.get('function',{}).get('name') for m in messages for t in m.get('tool_calls',[])]
  if "RETRIEVE" in lastuser and skill and "skill" not in called:toolname="skill";args={"id":skill}
  else:args={}
  import re
  existing=re.search(r"LOAD_EXISTING:([a-z0-9-]+)",lastuser)
  if existing:toolname="skill";args={"id":existing.group(1)}
  available={x.get('function',{}).get('name') for x in tools}
  if toolname not in called and toolname in available:
   delta={"role":"assistant","tool_calls":[{"index":0,"id":"call_fixture_"+str(time.time_ns()),"type":"function","function":{"name":toolname,"arguments":json.dumps(args)}}]};finish="tool_calls"
  else:delta={"role":"assistant","content":"CPU fixture completed."};finish="stop"
  log={"time":time.time(),"messages":len(messages),"request_bytes":len(json.dumps(d).encode()),"metadata_present":any("Relevant verified project procedures" in str(m.get('content','')) for m in messages),"skill_id_present":bool(skill),"requested_tool":delta.get("tool_calls",[{}])[0].get("function",{}).get("name"),"latency_ms":(time.monotonic()-start)*1000}
  with open('/learning/state/provider-metrics.jsonl','a') as f:f.write(json.dumps(log)+'\n')
  self.send_response(200)
  if d.get('stream'):
   self.send_header('Content-Type','text/event-stream');self.end_headers()
   for part in [{"id":"chatcmpl-fixture","object":"chat.completion.chunk","created":int(time.time()),"model":"cpu-fixture","choices":[{"index":0,"delta":delta,"finish_reason":None}]},{"id":"chatcmpl-fixture","object":"chat.completion.chunk","created":int(time.time()),"model":"cpu-fixture","choices":[{"index":0,"delta":{},"finish_reason":finish}]}]:
    self.wfile.write(('data: '+json.dumps(part)+'\n\n').encode())
   self.wfile.write(b'data: [DONE]\n\n')
  else:
   delta.pop('index',None)
   for x in delta.get('tool_calls',[]):x.pop('index',None)
   self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(json.dumps({"id":"chatcmpl-fixture","object":"chat.completion","created":int(time.time()),"model":"cpu-fixture","choices":[{"index":0,"message":delta,"finish_reason":finish}]}).encode())
http.server.ThreadingHTTPServer(('127.0.0.1',18080),Handler).serve_forever()
