"""Advisory principle/recipe review adapted from the installed audit-agents skill.
Never rewrites source, promotes a recipe, removes evidence, or weakens acceptance.
"""
import re
MECHANICS=re.compile(r"(?:--[a-z]|/(?:data|app|config|workspace)/|\b(?:kubectl|python3?|sudo|git|blender|godot)\s|\bv?\d+\.\d+|\b\d+\s*(?:GiB|MiB|GB|threads|seconds)\b)",re.I)
SENSITIVE=re.compile(r"-----BEGIN.*PRIVATE KEY|Bearer\s+\S+|(?:password|api[_-]?key|token|secret)\s*[:=]\s*\S+",re.I)
def audit(policies):
 findings=[]
 for policy in policies:
  seen=set()
  lines=[('steps.'+str(i),text) for i,text in enumerate(policy.get('steps',[]))]+[(name,policy.get(name,'')) for name in ['validation','recovery']]
  for source,text in lines:
   if not isinstance(text,str) or not text or SENSITIVE.search(text):continue
   normalized=' '.join(text.lower().split())
   if normalized in seen:verdict,owner,reason='delete-proposal','reviewed guidance','Duplicate wording; retain original evidence and recipe until reviewed.'
   elif MECHANICS.search(text):verdict,owner,reason='move','versioned verified recipe','Mechanics belong with environment/interface hashes and rollback, not universal agent guidance.'
   else:verdict,owner,reason='keep-candidate','skill guidance','Potential lasting lesson; a reviewer must confirm it changes a new contributor decision.'
   seen.add(normalized);findings.append({'policy':policy.get('id'),'source':source,'quote':text[:1200],'verdict':verdict,'owner':owner,'reason':reason,'applied':False})
 return {'sourceSkill':'github:dzhng/skills:skills/authoring/audit-agents','mode':'advisory; not an AGENTS.md rewrite or execution approval','findings':findings,'principles':['Keep lasting, concrete guidance separate from environment-specific mechanics.','Keep exact commands and successful arguments in provenance-pinned recipes.','Run the narrowest check that answers the current question; run complete required acceptance when implementation is ready.','Never promote a suggestion, failed run, stale environment or unverified model claim as a successful recipe.','Review proposed changes before activation; preserve active versions, evidence and rollback.'],'automaticMutation':False}
