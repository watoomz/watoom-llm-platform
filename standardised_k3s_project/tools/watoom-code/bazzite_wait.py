"""Owner policy (2026-11-07): heavy work waits for Bazzite; the rig is allowed only after 10 minutes; never the homelab server."""
RIG_AFTER_SEC=600
def bazzite_wait(old,now,window=RIG_AFTER_SEC):
 """(waiting_since, rig_eligible): the rig is allowed only after Bazzite has been unavailable for `window` seconds (owner policy 2026-11-07)."""
 since=(old or {}).get('waiting_since')
 since=since if isinstance(since,(int,float)) and since<=now else now
 return since,now-since>=window
def wait_reason(since,eligible,now):
 minutes=int((now-since)//60)
 if eligible:return 'Bazzite has been unavailable for %d min. The rig route is now permitted: submit the equivalent watoom_rig_game_job if it is enabled; otherwise this request keeps retrying Bazzite. Never the homelab server.'%minutes
 return 'Bazzite unavailable for %d of %d min; retrying every poll. The rig is only allowed after %d min. Never the homelab server.'%(minutes,RIG_AFTER_SEC//60,RIG_AFTER_SEC//60)
