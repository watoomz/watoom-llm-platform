import base64,json,os,subprocess,tempfile,threading,unittest,urllib.request,urllib.error
from http.server import ThreadingHTTPServer
from pathlib import Path
from broker import Skills,Conflict,handle
from server import Application

SKILL="---\nname: creative-writing\ndescription: Write fiction.\n---\n# Creative writing\nBe vivid.\n"
def git(repo,*args):return subprocess.run(["git","-C",str(repo),*args],check=True,capture_output=True,text=True).stdout.strip()

class Fixture:
 def __init__(self):
  self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name)
  self.repo=root/"repo";skills=self.repo/"p/skills"
  for name,text in (("creative-writing",SKILL),("redteam","---\nname: RedTeam\ndescription: x\n---\nbody\n")):
   (skills/name).mkdir(parents=True);(skills/name/"SKILL.md").write_text(text)
  (self.repo/"unrelated.txt").write_text("a\n")
  git(self.repo,"init","-q","-b","main");git(self.repo,"-c","user.name=t","-c","user.email=t@t","add","--","p","unrelated.txt");git(self.repo,"-c","user.name=t","-c","user.email=t@t","commit","-qm","init")
  self.live=root/"live";(self.live/"creative-writing").mkdir(parents=True);(self.live/"creative-writing"/"SKILL.md").write_text(SKILL)
  self.skills=Skills({"repo":str(self.repo),"skills_path":"p/skills","live_root":str(self.live),"live_uid":os.getuid(),"live_gid":os.getgid(),"state":str(root/"state"),"author_name":"Agent Export","author_email":"codex@agent.example"})

class BrokerTests(unittest.TestCase):
 def setUp(self):self.f=Fixture();self.s=self.f.skills
 def tearDown(self):self.f.tmp.cleanup()
 def test_list_reports_live_state(self):
  names={x["name"]:x["live"] for x in self.s.list()["skills"]}
  self.assertEqual(names,{"creative-writing":"matches","redteam":"absent"})
 def test_save_commits_only_that_path_and_updates_live(self):
  (self.f.repo/"unrelated.txt").write_text("dirty\n");git(self.f.repo,"add","unrelated.txt")
  r=self.s.read("creative-writing");new=SKILL.replace("Be vivid.","Be vivid and concise.")
  out=self.s.save("creative-writing",new,r["blob"],"tighten guidance")
  self.assertTrue(out["changed"]);self.assertEqual(out["live"],"matches")
  self.assertEqual((self.f.live/"creative-writing/SKILL.md").read_text(),new)
  self.assertEqual(git(self.f.repo,"show","--name-only","--format=%s","HEAD").splitlines(),["skills(creative-writing): tighten guidance","","p/skills/creative-writing/SKILL.md"])
  self.assertEqual(git(self.f.repo,"log","-1","--format=%an <%ae>"),"Agent Export <codex@agent.example>")
  self.assertEqual(git(self.f.repo,"diff","--cached","--name-only"),"unrelated.txt")  # unrelated staged change preserved, not committed
 def test_stale_blob_is_a_conflict(self):
  r=self.s.read("creative-writing");self.s.save("creative-writing",SKILL+"one\n",r["blob"])
  with self.assertRaises(Conflict):self.s.save("creative-writing",SKILL+"two\n",r["blob"])
 def test_dirty_working_copy_blocks_save(self):
  r=self.s.read("creative-writing");(self.f.repo/"p/skills/creative-writing/SKILL.md").write_text(SKILL+"local\n")
  self.assertTrue(self.s.read("creative-writing")["dirty"])
  with self.assertRaises(Conflict):self.s.save("creative-writing",SKILL+"x\n",r["blob"])
 def test_wrong_branch_blocks_save(self):
  git(self.f.repo,"checkout","-qb","other");r=self.s.read("creative-writing")
  with self.assertRaises(Conflict):self.s.save("creative-writing",SKILL+"x\n",r["blob"])
 def test_frontmatter_name_must_be_kept(self):
  r=self.s.read("redteam")
  with self.assertRaises(ValueError):self.s.save("redteam","no front matter\n",r["blob"])
  with self.assertRaises(ValueError):self.s.save("redteam","---\nname: redteam\ndescription: x\n---\nb\n",r["blob"])
  self.assertTrue(self.s.save("redteam","---\nname: RedTeam\ndescription: y\n---\nb\n",r["blob"])["changed"])
 def test_rejects_traversal_symlink_oversize_and_nul(self):
  for name in ("../x","a/b","",".hidden"):
   with self.assertRaises(ValueError):self.s.read(name)
  os.symlink(self.f.repo/"p/skills/creative-writing",self.f.repo/"p/skills/linked")
  with self.assertRaises(ValueError):self.s.read("linked")
  r=self.s.read("creative-writing")
  with self.assertRaises(ValueError):self.s.save("creative-writing",SKILL+"x"*(256*1024),r["blob"])
  with self.assertRaises(ValueError):self.s.save("creative-writing",SKILL+"\x00",r["blob"])
  with self.assertRaises(ValueError):self.s.save("creative-writing",SKILL+"x",r["blob"],"two\nlines")
 def test_unchanged_save_makes_no_commit(self):
  head=git(self.f.repo,"rev-parse","HEAD");r=self.s.read("creative-writing")
  self.assertFalse(self.s.save("creative-writing",SKILL,r["blob"])["changed"]);self.assertEqual(git(self.f.repo,"rev-parse","HEAD"),head)
 def test_failed_commit_restores_file(self):
  r=self.s.read("creative-writing");path=self.f.repo/"p/skills/creative-writing/SKILL.md"
  hook=self.f.repo/".git/hooks/pre-commit";hook.write_text("#!/bin/sh\nexit 1\n");hook.chmod(0o755)
  with self.assertRaises(RuntimeError):self.s.save("creative-writing",SKILL+"x\n",r["blob"])
  self.assertEqual(path.read_text(),SKILL);self.assertEqual((self.f.live/"creative-writing/SKILL.md").read_text(),SKILL)
 def test_handle_rejects_unknown_action(self):
  with self.assertRaises(ValueError):handle(self.s,{"action":"delete"})

class ServerTests(unittest.TestCase):
 def setUp(self):
  self.calls=[]
  def broker(request):
   self.calls.append(request)
   if request["action"]=="list":return {"skills":[],"branch":"main","unpushed":0}
   if request["action"]=="save" and request["blob"]=="stale":
    e=ValueError("changed since opened");e.code="conflict";raise e
   return {"ok":True}
  self.app=Application("p"*30,"https://glance.example",broker)
  self.httpd=ThreadingHTTPServer(("127.0.0.1",0),self.app.handler());threading.Thread(target=self.httpd.serve_forever,daemon=True).start()
  self.base="http://127.0.0.1:%d/skills"%self.httpd.server_port
 def tearDown(self):self.httpd.shutdown();self.httpd.server_close()
 def request(self,path,body=None,headers=None,auth=True):
  h=dict(headers or {})
  if auth:h["Authorization"]="Basic "+base64.b64encode(b"admin:"+b"p"*30).decode()
  req=urllib.request.Request(self.base+path,None if body is None else json.dumps(body).encode(),h)
  try:
   with urllib.request.urlopen(req) as r:return r.status,r.read()
  except urllib.error.HTTPError as e:return e.code,e.read()
 def test_requires_authentication(self):
  self.assertEqual(self.request("/api/skills",auth=False)[0],401);self.assertEqual(self.calls,[])
 def test_referrer_policy_keeps_same_origin_header(self):
  # "no-referrer" makes browsers send Origin: null on same-origin POSTs, breaking login and save.
  with urllib.request.urlopen(self.base+"/login") as r:self.assertEqual(r.headers["Referrer-Policy"],"same-origin")
 def test_list_via_broker(self):
  code,raw=self.request("/api/skills");self.assertEqual(code,200);self.assertEqual(json.loads(raw)["branch"],"main")
 def test_save_requires_origin_and_csrf(self):
  body={"name":"x","content":"y","blob":"b"}
  self.assertEqual(self.request("/api/save",body,{"Content-Type":"application/json"})[0],403)
  self.assertEqual(self.request("/api/save",body,{"Origin":"https://evil.example","X-CSRF-Token":self.app.csrf})[0],403)
  self.assertEqual(self.request("/api/save",body,{"Origin":"https://glance.example","X-CSRF-Token":"wrong"})[0],403)
  self.assertEqual(self.calls,[])
  self.assertEqual(self.request("/api/save",body,{"Origin":"https://glance.example","X-CSRF-Token":self.app.csrf})[0],200)
 def test_conflict_maps_to_409(self):
  code,raw=self.request("/api/save",{"name":"x","content":"y","blob":"stale"},{"Origin":"https://glance.example","X-CSRF-Token":self.app.csrf})
  self.assertEqual(code,409);self.assertIn("changed",json.loads(raw)["error"])
 def test_paths_outside_prefix_are_404(self):
  req=urllib.request.Request("http://127.0.0.1:%d/api/skills"%self.httpd.server_port)
  with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(req)
  self.assertEqual(e.exception.code,404)
 def test_login_sets_cookie_session(self):
  data=b"password="+b"p"*30
  req=urllib.request.Request(self.base+"/login",data,{"Origin":"https://glance.example","Content-Type":"application/x-www-form-urlencoded"})
  class NoRedirect(urllib.request.HTTPRedirectHandler):
   def redirect_request(self,*a,**k):return None
  try:urllib.request.build_opener(NoRedirect).open(req)
  except urllib.error.HTTPError as e:
   self.assertEqual(e.code,303);cookie=e.headers["Set-Cookie"]
  self.assertIn("HttpOnly",cookie);self.assertIn("SameSite=Strict",cookie);self.assertIn("Secure",cookie)
  token=cookie.split(";")[0]
  self.assertEqual(self.request("/api/skills",headers={"Cookie":token},auth=False)[0],200)

if __name__=="__main__":unittest.main()
