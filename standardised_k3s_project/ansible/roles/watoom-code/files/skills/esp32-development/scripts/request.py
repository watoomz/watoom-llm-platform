"""Read-only source revision helper; native watoom_esp32 submits jobs."""
import argparse,json
from contract import fingerprint,sources
p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('--profile',default='standard',help="source budget profile: standard or large; add source_profile to the build manifest when not standard");a=p.parse_args()
out={'source':a.source,'source_sha256':fingerprint(a.source,a.profile),'files':sources(a.source,a.profile)}
if a.profile!='standard':out['source_profile']=a.profile
print(json.dumps(out,indent=2))
