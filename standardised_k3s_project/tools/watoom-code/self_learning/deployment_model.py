"""Fail closed unless the explicitly reviewed validation model is already idle/ready."""
def validate_idle_model(gpu, selected, expected, deployment):
 if gpu.get('owner') is not None or gpu.get('phase') not in ('qwen-ready','model-ready') or gpu.get('uncertain') is not False or gpu.get('active_requests')!=0:
  raise RuntimeError('GPU controller has ownership, uncertainty, inference or an unsupported phase')
 if selected!=expected or deployment['metadata']['name']!=expected:
  raise RuntimeError('Reviewed validation deployment is not the selected model')
 spec=deployment['spec'];status=deployment.get('status',{})
 if spec['replicas']!=1 or status.get('readyReplicas')!=1 or status.get('observedGeneration',0)<deployment['metadata']['generation']:
  raise RuntimeError('Selected validation model is not ready; no model switch authorised')
