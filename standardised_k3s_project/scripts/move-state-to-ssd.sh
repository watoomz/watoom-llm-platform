#!/usr/bin/env bash
# Move the performance-sensitive app state from the HDD (/data) to the SSD (/app) and bind-mount it back at the ORIGINAL path.
# Pod hostPaths, host tools and the repo keep using /data/ai/<name> unchanged; the bytes simply live on the SSD.
#
#   scripts/move-state-to-ssd.sh            # dry run: prints the plan
#   scripts/move-state-to-ssd.sh --apply    # stop the app pods and timers briefly, copy, mount, restart, verify
#
# Why: application.sqlite (500+ MB) and the AgentMemory store are read at random by every page of the GUI. On the shared
# spinning disk, cold pages took 6-25 s whenever a game import was reading the project, so Memory/Catalogue/Skills/Prompt
# builder failed to load and the readiness probe timed out.
#
# Rollback: umount the path, remove its fstab line, mv <path>.hdd-old back (kept until --apply verifies, then removed).
set -euo pipefail
APPLY=0; [[ "${1:-}" == "--apply" ]] && APPLY=1
SRC_BASE=/data/ai; DST_BASE=/app/ai
DIRS=(watoom-code-stage agentmemory watoom-code-rig-jobs-stage)
NS_APP=opencode-watoom-stage; NS_RIG=opencode-rig-jobs-stage
TIMERS=(watoom-game-worker.timer watoom-learning-recovery.timer watoom-learning-optimisation.timer watoom-learning-curator.timer watoom-capability-health.timer)
LOG=/root/move-state-to-ssd-$(date +%Y%m%d-%H%M%S).log
say() { echo "== $*" | tee -a "$LOG"; }
run() { echo "+ $*" | tee -a "$LOG"; [[ $APPLY == 1 ]] && "$@" || true; }
die() { echo "REFUSE: $*" >&2; exit 1; }

say "plan (apply=$APPLY, log $LOG)"
for d in "${DIRS[@]}"; do [[ -d $SRC_BASE/$d ]] || die "$SRC_BASE/$d missing"; done
mountpoint -q /app || die "/app is not mounted"
for d in "${DIRS[@]}"; do mountpoint -q "$SRC_BASE/$d" && die "$SRC_BASE/$d is already a mount (already moved?)"; done
need=$(du -sk $(printf "$SRC_BASE/%s " "${DIRS[@]}") | awk '{s+=$1} END{print s}')
free=$(df -k --output=avail /app | tail -1)
(( free > need * 2 )) || die "not enough SSD space: need about $((need/1024)) MiB x2, have $((free/1024)) MiB"
if [[ $APPLY == 1 ]]; then
  # Stop new passes first, then wait (up to 45 min) for a running pass or Bazzite job to finish so no result is lost.
  systemctl stop watoom-game-worker.timer
  for _ in $(seq 1 540); do
    [[ "$(systemctl is-active watoom-game-worker.service)" == "inactive" ]] && ! pgrep -f "^/usr/bin/python3 .*/tools/watoom-code/game_(bazzite|worker_bridge).py" >/dev/null && break
    sleep 5
  done
  [[ "$(systemctl is-active watoom-game-worker.service)" == "inactive" ]] || { systemctl start watoom-game-worker.timer; die "the game worker did not go idle in 45 minutes"; }
fi

say "1. pause timers that touch the app pod"
for t in "${TIMERS[@]}"; do run systemctl stop "$t"; done
run sleep 3

say "2. scale the app pods down (records replicas)"
declare -A REPL
for spec in "$NS_APP:watoom-code" "$NS_APP:agentmemory" "$NS_RIG:watoom-code"; do
  ns=${spec%%:*}; dep=${spec##*:}
  REPL[$spec]=$(kubectl -n "$ns" get deploy "$dep" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo 0)
  [[ ${REPL[$spec]} -gt 0 ]] || REPL[$spec]=1   # never recorded running as "scale back to 0"; a prior run already had them down
  echo "   $spec replicas=${REPL[$spec]}" | tee -a "$LOG"
  [[ "$(kubectl -n "$ns" get deploy "$dep" -o jsonpath='{.spec.replicas}' 2>/dev/null)" != 0 ]] && run kubectl -n "$ns" scale deploy/"$dep" --replicas=0
done
SCALED_DOWN=1; DONE=0
restore_on_failure() {
  [[ $APPLY == 1 && $SCALED_DOWN == 1 && $DONE == 0 ]] || return 0
  echo "== restoring pods and timers after a failure (automatic)" | tee -a "$LOG"
  for spec in "${!REPL[@]}"; do kubectl -n "${spec%%:*}" scale deploy/"${spec##*:}" --replicas="${REPL[$spec]}" 2>&1 | tee -a "$LOG"; done
  for t in "${TIMERS[@]}"; do systemctl start "$t" 2>&1 | tee -a "$LOG"; done
}
trap restore_on_failure EXIT
if [[ $APPLY == 1 ]]; then
  for ns in $NS_APP $NS_RIG; do
    kubectl -n "$ns" wait --for=delete pod -l app=watoom-code --timeout=180s >/dev/null 2>&1 || true
  done
  kubectl -n $NS_APP wait --for=delete pod -l app=agentmemory --timeout=180s >/dev/null 2>&1 || true
fi

say "3. copy to the SSD (ACLs, xattrs, hard links kept) and verify by checksum"
for d in "${DIRS[@]}"; do
  run mkdir -p "$DST_BASE/$d"
  run rsync -aHAX --numeric-ids --delete "$SRC_BASE/$d/" "$DST_BASE/$d/"
  if [[ $APPLY == 1 ]]; then
    run sync
    # A short settle-and-retry loop: the pod is already gone (step 2 waited for that), but a late filesystem
    # flush or a host-side timer outside the ones we pause can still touch a byte or two right after. Re-run the
    # copy (rsync only touches what actually changed) and recheck a few times before refusing, logging exactly
    # what differed each time.
    ok=0
    for attempt in 1 2 3; do
      # || true: a clean copy means grep finds nothing to print and exits 1, which under set -eo pipefail would
      # abort the whole script right here on every SUCCESSFUL verify -- this was killing every real run.
      diff_lines=$(rsync -aHAXcn --delete --itemize-changes "$SRC_BASE/$d/" "$DST_BASE/$d/" 2>&1 | grep -v '^skipping non-regular file' || true)
      diffs=$(printf '%s\n' "$diff_lines" | grep -c . || true)
      echo "   $d: $diffs difference(s) after copy (attempt $attempt)" | tee -a "$LOG"
      if [[ $diffs -eq 0 ]]; then ok=1; break; fi
      printf '%s\n' "$diff_lines" | tee -a "$LOG"
      [[ $attempt -lt 3 ]] && { sleep 5; run rsync -aHAX --numeric-ids --delete "$SRC_BASE/$d/" "$DST_BASE/$d/"; }
    done
    [[ $ok == 1 ]] || die "checksum mismatch for $d after 3 attempts (see the differing paths just above in $LOG); nothing was switched over. Scale the pods back up yourself: kubectl -n $NS_APP scale deploy/watoom-code --replicas=1; kubectl -n $NS_APP scale deploy/agentmemory --replicas=1; kubectl -n $NS_RIG scale deploy/watoom-code --replicas=1"
  fi
  run chcon -R -t container_file_t "$DST_BASE/$d"
  run semanage fcontext -a -t container_file_t "$DST_BASE/$d(/.*)?"
done

say "4. switch: keep the old copy aside, bind-mount the SSD copy at the original path"
for d in "${DIRS[@]}"; do
  run mv "$SRC_BASE/$d" "$SRC_BASE/$d.hdd-old"
  run mkdir "$SRC_BASE/$d"
  line="$DST_BASE/$d $SRC_BASE/$d none bind,nofail,x-systemd.requires-mounts-for=$DST_BASE:$SRC_BASE 0 0"
  grep -qF "$DST_BASE/$d $SRC_BASE/$d " /etc/fstab || { echo "+ fstab: $line" | tee -a "$LOG"; [[ $APPLY == 1 ]] && echo "$line" >> /etc/fstab; }
done
run systemctl daemon-reload
for d in "${DIRS[@]}"; do run mount "$SRC_BASE/$d"; done

say "5. bring everything back"
for spec in "${!REPL[@]}"; do
  ns=${spec%%:*}; dep=${spec##*:}
  [[ ${REPL[$spec]} -gt 0 ]] && run kubectl -n "$ns" scale deploy/"$dep" --replicas="${REPL[$spec]}"
done
if [[ $APPLY == 1 ]]; then
  kubectl -n $NS_APP rollout status deploy/watoom-code --timeout=300s
  kubectl -n $NS_APP rollout status deploy/agentmemory --timeout=300s
fi
for t in "${TIMERS[@]}"; do run systemctl start "$t"; done
DONE=1

if [[ $APPLY == 1 ]]; then
  say "6. verify"
  for d in "${DIRS[@]}"; do echo "   $(findmnt -no SOURCE,TARGET "$SRC_BASE/$d" | tr '\n' ' ')" | tee -a "$LOG"; done
  kubectl -n $NS_APP exec deploy/watoom-code -c app -- sh -c 'stat -c "app db device %d %n" /state/application.sqlite'
  echo "   the old HDD copies are kept as $SRC_BASE/<name>.hdd-old until you remove them:  rm -rf $SRC_BASE/*.hdd-old" | tee -a "$LOG"
fi
