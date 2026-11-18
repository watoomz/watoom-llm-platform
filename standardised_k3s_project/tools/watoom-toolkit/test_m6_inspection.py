"""Published inspection must resolve only immutable, hash-verified local inputs."""
import hashlib,json,os,pathlib,tempfile,unittest
import agent
import kube_worker
from unittest.mock import patch

class PublishedInspection(unittest.TestCase):
    def test_worker_maps_published_input_read_only_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as directory:
            state=pathlib.Path(directory);job=state/'jobs/0123456789abcdef';job.mkdir(parents=True)
            calls=[]
            image='127.0.0.1:5000/watoom-toolkit@sha256:'+'a'*64
            def api(method,path,body=None,raw=False):
                calls.append((method,path,body))
                if method=='POST':return {'metadata':{'name':body['metadata']['name'],'uid':'test-owner'}}
                if method=='DELETE':return {}
                if '/log?' in path:return 'worker output'
                if '/pods?' in path:return {'items':[{'metadata':{'name':'test-worker','ownerReferences':[{'uid':'test-owner'}]},'spec':{'automountServiceAccountToken':False,'securityContext':{'runAsUser':1010}},'status':{'containerStatuses':[{'imageID':image}]}}]}
                return {'status':{'succeeded':1}}
            environment={'WATOOM_WORKER_IMAGE':image,'WATOOM_HOST_STATE':'/approved/state','WATOOM_HOST_WORKSPACE':'/approved/workspace','WATOOM_WORKER_NAMESPACE':'watoom-code','WATOOM_3D_PUBLISH':'/generated','WATOOM_HOST_PUBLISH':'/approved/generated'}
            payload={'task':'3d-inspect','path':'generated/watoom-toolkit-3d/v1/abcdefabcdefabcd/asset.glb'}
            argv=['blender','--',json.dumps({'task':'3d-inspect','input':'/generated/abcdefabcdefabcd/asset.glb','output':'/state/jobs/0123456789abcdef/artifacts'})]
            with patch.dict(os.environ,environment),patch.object(kube_worker,'api',api):
                result=kube_worker.execute(argv,60,job,state,pathlib.Path('/workspace'),payload)
            specification=calls[0][2];worker=specification['spec']['template']['spec']
            volume=next(item for item in worker['volumes'] if item['name']=='input')
            mount=next(item for item in worker['containers'][0]['volumeMounts'] if item['name']=='input')
            self.assertEqual(volume['hostPath']['path'],'/approved/generated/abcdefabcdefabcd/asset.glb')
            self.assertTrue(mount['readOnly']);self.assertFalse(worker['automountServiceAccountToken'])
            self.assertEqual(result['status'],'PASS');self.assertEqual(calls[-1][0],'DELETE')

    def test_published_input_and_rejections(self):
        with tempfile.TemporaryDirectory() as directory:
            root=pathlib.Path(directory);published=root/'published';published.mkdir()
            version=published/'0123456789abcdef';version.mkdir()
            asset=version/'asset.glb';asset.write_bytes(b'test-asset')
            manifest={'outputs':[{'path':'asset.glb','bytes':10,'sha256':hashlib.sha256(b'test-asset').hexdigest()}]}
            (version/'manifest.json').write_text(json.dumps(manifest))
            previous=dict(os.environ)
            try:
                os.environ.update(WATOOM_3D_PUBLISH=str(published),WATOOM_3D_PUBLIC_REFERENCE='generated/watoom-toolkit-3d/v1')
                reference='generated/watoom-toolkit-3d/v1/0123456789abcdef/asset.glb'
                self.assertEqual(agent.inspection_path(reference),asset)
                for invalid in (reference.replace('asset.glb','../asset.glb'),reference.replace('asset.glb','manifest.json'),reference.replace('0123456789abcdef','ffffffffffffffff')):
                    with self.assertRaises((ValueError,OSError)):agent.inspection_path(invalid)
                asset.write_bytes(b'tampered')
                with self.assertRaises(ValueError):agent.inspection_path(reference)
                asset.unlink();outside=root/'outside';outside.write_bytes(b'test-asset');asset.symlink_to(outside)
                with self.assertRaises(ValueError):agent.inspection_path(reference)
            finally:os.environ.clear();os.environ.update(previous)

if __name__=='__main__':unittest.main()
