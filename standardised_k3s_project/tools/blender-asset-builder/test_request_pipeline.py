import contextlib
import fcntl
import importlib.util
import io
import json
import pathlib
import sys
import tempfile
import types
import unittest
from unittest import mock

import request_pipeline as runner


class RequestRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=pathlib.Path(self.temp.name);self.pipeline=self.base/'pipeline';self.root=self.pipeline/'revision';self.root.mkdir(parents=True)
        self.skills=self.base/'skills';self.policy=self.skills/'blender-core/scripts';self.policy.mkdir(parents=True)
        for name in ('worker_profile.py','worker-profiles.json'):(self.policy/name).write_text('{}')
        qa=self.skills/'blender-asset-qa/scripts';qa.mkdir(parents=True)
        for name in ('qa_check.py','_bpyx.py'):(qa/name).write_text('# fixture')
        self.binary=self.base/'blender';self.binary.write_text('fixture')
        for name in ('references.json','specification.json','stage.py','runtime.blend'):(self.root/name).write_text('fixture')
        self.req={'schema':1,'brief':'Regression fixture','references':'references.json','specification':'specification.json','engine_source':'runtime.blend','stages':[{'name':n,'script':'stage.py','outputs':[n+'.out']} for n in ('MODEL','MATERIALS','QA','EXPORT')]}
        self.request=self.root/'request.json';self.save_request()
        fake=types.SimpleNamespace(verify_external=lambda:{'boundary':'fixture'},verify_binary=lambda p:None,PROFILES=self.policy/'worker-profiles.json')
        original_sha=runner.sha
        for patcher in (mock.patch.object(runner,'ROOT',self.pipeline),mock.patch.object(runner,'SKILLS',self.skills),mock.patch.object(runner,'BLENDER',self.binary),mock.patch.object(runner,'sha',side_effect=lambda p:runner.BLENDER_SHA256 if p==self.binary else original_sha(p)),mock.patch.dict(sys.modules,{'worker_profile':fake})):
            patcher.start();self.addCleanup(patcher.stop)

    def save_request(self):self.request.write_text(json.dumps(self.req))

    def resume_state(self):
        (self.root/'reports').mkdir(exist_ok=True)
        (self.root/'MODEL.out').write_text('retained output')
        state={'schema':2,'request_sha256':runner.sha(self.request),'stages':{'MODEL':{'status':'FAIL','attempts':1}},'result':'FAIL'}
        (self.root/'state.json').write_text(json.dumps(state))

    def call_main(self,*flags):
        with mock.patch.object(sys,'argv',['pipeline.py','--request',str(self.request),*flags]):return runner.main()

    def test_validate_before_archive_preserves_retry_for_invalid_timeout_and_blend(self):
        for patch,message in (({'timeout':301},'timeout outside'),({'blend':'missing.blend'},'Missing input'),({'args':[7]},'arguments must be strings')):
            with self.subTest(patch=patch):
                self.req['stages'][0]={'name':'MODEL','script':'stage.py','outputs':['MODEL.out'],**patch};self.save_request();self.resume_state()
                before=(self.root/'state.json').read_bytes()
                with mock.patch.object(runner.subprocess,'Popen') as process:
                    for attempt in range(2):
                        with self.assertRaisesRegex(ValueError,message):self.call_main('--resume','--retry-failed')
                        self.assertEqual((self.root/'MODEL.out').read_text(),'retained output')
                        self.assertFalse((self.root/'reports/retained-MODEL-1').exists())
                        self.assertEqual((self.root/'state.json').read_bytes(),before)
                    process.assert_not_called()

    def test_lock_contention_is_clean_blocked_exit_two(self):
        (self.root/'reports').mkdir()
        with (self.root/'reports/pipeline.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with contextlib.redirect_stdout(io.StringIO()) as output, mock.patch.object(runner.subprocess,'Popen') as process:
                self.assertEqual(self.call_main(),2)
                self.assertEqual(output.getvalue().strip(),'BLOCKED: task already running')
                process.assert_not_called()
        self.assertFalse((self.root/'state.json').exists())

    def test_engine_missing_manifest_is_value_error_and_connection_closes(self):
        db=mock.Mock();body={'path':'pipelines/'+str((self.root/'runtime.blend').relative_to(self.pipeline.parent)),'parameters':{'engine_validation':1}}
        db.execute.return_value.fetchall.return_value=[('completed',json.dumps(body),json.dumps({'artifacts':[]}))]
        with mock.patch.object(runner.sqlite3,'connect',return_value=db):
            with self.assertRaisesRegex(ValueError,'no manifest artifact'):runner.engine(self.root,self.req,'fixture-job')
        db.close.assert_called_once_with()

    def test_policy_fallback_works_for_tools_and_role_copies(self):
        project=pathlib.Path(__file__).resolve().parents[2]
        expected=project/'ansible/roles/watoom-code/files/skills/blender-core/scripts'
        for path in (project/'tools/blender-asset-builder/request_pipeline.py',project/'ansible/roles/watoom-code/files/skills/watoom-blender-asset-builder/scripts/request_pipeline.py'):
            with self.subTest(copy=str(path)):
                spec=importlib.util.spec_from_file_location('policy_fixture',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
                module.SKILLS=self.base/'absent'
                self.assertEqual(module.policy_scripts(),expected)

    def test_explicit_engine_job_validates_once_and_resume_revalidates_once(self):
        stages=iter([*self.req['stages'],{'outputs':['reports/source-qa.json']}])
        def start(*args,**kwargs):
            stage=next(stages)
            def wait(**options):
                for name in stage['outputs']:(self.root/name).write_text('fixture output')
                return 0
            return types.SimpleNamespace(wait=wait)
        result={'status':'PASS','job':'explicit-job'}
        with mock.patch.object(runner.subprocess,'Popen',side_effect=start), mock.patch.object(runner,'engine',return_value=result) as engine, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.call_main('--engine-job','explicit-job'),2)
            engine.assert_called_once_with(self.root,self.req,'explicit-job')
            engine.reset_mock()
            self.assertEqual(self.call_main('--resume'),2)
            engine.assert_called_once_with(self.root,self.req,'explicit-job')


if __name__=='__main__':unittest.main()
