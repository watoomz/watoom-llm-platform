import unittest,sqlite3
from capability_maintenance import summary
from lesson_audit import audit
class HealthTests(unittest.TestCase):
 def test_pinned_prior_version_is_not_stale_but_changed_approval_is(self):
  c=sqlite3.connect(':memory:');a=sqlite3.connect(':memory:');a.execute('create table kv(key,value)')
  c.executescript("create table skills(id,sha256,validation);create table sources(repo,commit_sha);create table approvals(skill_id,approved_sha);create table approval_context(skill_id,commit_sha);create table _watoom_skill_review(skill_id,content_sha,revision,state);alter table skills add column repo;")
  c.execute("insert into skills values('s','new','valid','repo')");c.execute("insert into sources values('repo','new-commit')");c.execute("insert into approvals values('s','old')");c.execute("insert into approval_context values('s','old-commit')");c.execute("insert into _watoom_skill_review values('s','old','old-commit','ENABLED')")
  self.assertEqual(summary(c,a)['staleApprovalReferences'],[])
  c.execute("update approvals set approved_sha='wrong'");self.assertEqual(summary(c,a)['staleApprovalReferences'],['s'])
class LessonTests(unittest.TestCase):
 def test_mechanics_move_without_losing_receipt_requirements_or_applying_mutations(self):
  policy={'id':'test','steps':['Inspect the actual result.','python3 /data/ai/tool.py --check','Inspect the actual result.'],'validation':'Require a matching verified receipt.','recovery':'Preserve the last accepted artifact.'}
  result=audit([policy]);self.assertFalse(result['automaticMutation']);self.assertEqual([x['verdict'] for x in result['findings'][:3]],['keep-candidate','move','delete-proposal']);self.assertTrue(all(not x['applied'] for x in result['findings']));self.assertEqual(policy['steps'][1],'python3 /data/ai/tool.py --check')
 def test_secrets_are_not_copied_to_audit_findings(self):
  self.assertEqual(audit([{'steps':['password=private-value']}])['findings'],[])
if __name__=='__main__':unittest.main()
