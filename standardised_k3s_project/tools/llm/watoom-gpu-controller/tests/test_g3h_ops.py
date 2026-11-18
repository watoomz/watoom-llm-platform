import unittest
from g3h_ops import restore_model, restore_timeout, router_restore_plan, MISSING, rollback, rollback_decision


class Tests(unittest.TestCase):
    def test_router_restore_preserves_unrelated_changes(self):
        before={'data':{'router.py':'guard-baseline'}}
        candidate={'data':{'router.py':'controller-client','client.py':'rpc'}}
        current={'data':{**candidate['data'],'unrelated':'new-value'}}
        deployment={'spec':{'template':{'spec':{'volumes':[{'name':'other'},{'name':'gpu-controller','hostPath':{'path':'/data/ai/helper-scripts/state/gpu-controller-router','type':'Directory'}}],
            'containers':[{'name':'router','env':[{'name':'USER_EDIT','value':'keep'}],'volumeMounts':[{'name':'gpu-controller','mountPath':'/gpu-controller','readOnly':True}]}]}}}}
        cm,result=router_restore_plan(current,deployment,before,candidate)
        self.assertEqual(cm['data'],{'router.py':'guard-baseline','unrelated':'new-value'})
        self.assertEqual(result['spec']['template']['spec']['containers'][0]['env'],[{'name':'USER_EDIT','value':'keep'}])
        self.assertEqual(result['spec']['template']['spec']['volumes'],[{'name':'other'}])
        self.assertEqual(router_restore_plan(cm,result,before,candidate),(cm,result))

    def test_timeout_restore_preserves_other_mcp_auth(self):
        document={'mcp':{'watoom-llama-mesh':{'timeout':3600000},'watoom-kali':{'authorization':'unchanged'}}}
        result=restore_timeout(document,MISSING,3600000)
        self.assertNotIn('timeout',result['mcp']['watoom-llama-mesh'])
        self.assertEqual(result['mcp']['watoom-kali'],document['mcp']['watoom-kali'])
        self.assertEqual(restore_timeout(result,MISSING,3600000),result)

    def test_native_timeout_restore_preserves_other_limits_and_servers(self):
        timeout={'startup':30000,'catalog':30000,'execution':3600000}
        document={'mcp':{'servers':{'watoom-llama-mesh':{'timeout':timeout,'codemode':False},'other':{'disabled':False}}}}
        before={'startup':10000,'catalog':20000,'execution':60000}
        result=restore_timeout(document,before,timeout)
        self.assertEqual(result['mcp']['servers']['watoom-llama-mesh']['timeout'],before)
        self.assertEqual(result['mcp']['servers']['other'],document['mcp']['servers']['other'])
        self.assertEqual(restore_timeout(result,before,timeout),result)
        with self.assertRaises(RuntimeError):
            restore_timeout(document,before,{'execution':1})

    def test_restoration_preserves_body_and_other_fields(self):
        text='---\nmodel: qwen\nsteps: 999\n---\nUser edited body\n'
        result=restore_model(text,'model: active','model: qwen')
        self.assertEqual(result,'---\nmodel: active\nsteps: 999\n---\nUser edited body\n')
        self.assertEqual(restore_model(result,'model: active','model: qwen'),result)

    def test_same_field_conflict_refused(self):
        with self.assertRaises(RuntimeError):
            restore_model('---\nmodel: custom\n---\nbody','model: active','model: qwen')

    def test_body_model_text_untouched(self):
        text='---\nmodel: qwen\n---\nmodel: qwen\n'
        self.assertTrue(restore_model(text,'model: active','model: qwen').endswith('model: qwen\n'))

    def test_rollback_live_owner_all_states(self):
        for phase in ('acquiring','stopping-qwen','starting-mesh','mesh-active','restoring','recovery-required'):
            self.assertEqual(rollback_decision({'phase':phase,'owner':'job','uncertain':True},True),'DEFER_LIVE_OWNER')

    def test_rollback_unowned_error_refused(self):
        self.assertEqual(rollback_decision({'phase':'recovery-required','owner':None,'uncertain':True},False),'BLOCKED_UNOWNED_UNSAFE_STATE')

    def test_rollback_no_side_effect_live_owner(self):
        class Client:
            def call(self,action,**kw):
                if action!='status':raise AssertionError('mutation attempted')
                return {'phase':'mesh-active','owner':'job','uncertain':False}
        self.assertEqual(rollback(Client(),lambda _:True,lambda:self.fail(),lambda:self.fail()),'DEFER_LIVE_OWNER')

    def test_failed_recovery_is_not_retried(self):
        calls=[]
        class Client:
            def call(self,action,**kw):
                calls.append(action)
                if action=='status':return {'phase':'restoring','owner':'job','generation':1,'uncertain':True}
                raise RuntimeError('unknown outcome')
        with self.assertRaises(RuntimeError):rollback(Client(),lambda _:False,lambda:self.fail(),lambda:self.fail())
        self.assertEqual(calls,['status','recover'])

    def test_health_failure_prevents_config_restoration(self):
        class Client:
            def call(self,action,**kw):return {'phase':'qwen-ready','owner':None,'uncertain':False}
        def health():raise RuntimeError('inference failed')
        with self.assertRaises(RuntimeError):rollback(Client(),lambda _:False,health,lambda:self.fail())


if __name__=='__main__':unittest.main()
