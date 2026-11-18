"""Maintain user-selected application budgets without changing backend deployments."""
import json,os,re,sys
from pathlib import Path
# Reasoning models spend output tokens thinking before the tool call. At 4096 a long thought used the whole budget
# and the call arrived cut off (finish=length, 17 times in one day), so the default is generous; the context budget
# still bounds it (output is capped at half the context).
DEFAULT_OUTPUT=16384
def update(document,inventory,context=100000,output=DEFAULT_OUTPUT):
 if not 512<=context<=100000 or not 128<=output<=32768:raise ValueError("Invalid stable application budget")
 provider=document["providers"]["watoom"];models=provider.setdefault("models",{})
 for row in inventory["data"]:
  name=row["id"]
  if not re.fullmatch("[A-Za-z0-9_.-]{1,128}",name) or name=="llama-mesh":continue
  item=models.setdefault(name,{"modelID":name,"name":name,"capabilities":{"tools":False,"input":["text"],"output":["text"]}})
  maximum=row.get("context_limit")
  limit=min(context,maximum) if isinstance(maximum,int) and maximum>=512 else context
  item["limit"]={"context":limit,"output":min(output,limit//2)}
 return document
def main():
 path=Path(sys.argv[1]);inventory=json.loads(Path(sys.argv[2]).read_text())
 before=path.read_text();document=update(json.loads(before),inventory,int(sys.argv[3]) if len(sys.argv)>3 else 100000,int(sys.argv[4]) if len(sys.argv)>4 else DEFAULT_OUTPUT)
 after=json.dumps(document,indent=2)+"\n"
 if json.loads(before)==document:print("UNCHANGED");return
 stat=path.stat();temporary=path.with_name(path.name+".context-new")
 with temporary.open("w") as f:f.write(after);f.flush();os.fsync(f.fileno())
 os.chmod(temporary,stat.st_mode&0o777);os.chown(temporary,stat.st_uid,stat.st_gid);os.replace(temporary,path);print("UPDATED")
if __name__=="__main__":main()
