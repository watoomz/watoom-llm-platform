#!/usr/bin/env python3
"""Watchdog for game-project coordinator sessions that "just stop".

game_worker_bridge.py already prompts the coordinator session exactly once when a worker job reaches a
terminal status (COMPLETED/FAILED/STALE_RESULT/RECONCILIATION_REQUIRED) -- see its one call to
'/api/session/<id>/prompt'. That is a single-shot, best-effort notification: if the session was mid-restart,
the pod cycled (a deploy, a migration, this host's own maintenance), or the push simply failed, nothing ever
retries it, and the agent has no other reason to look at that job again. That silent, one-shot delivery is the
most likely explanation for "it just stops sometimes" -- not a crash, a design gap.

This script is the retry: every run (meant to be wired to a timer, default every 20 minutes) it looks at every
game project's worker-requests for two distinct failure classes, and is careful to tell them apart:

  1. STALE_TERMINAL  - a job finished (pass or fail) more than --stale-after seconds ago and nothing newer has
     happened in that project's worker-requests since. The original resume prompt may never have landed.
     ACTION: send exactly one follow-up resume prompt to the job's coordinator session (same call the bridge
     itself makes), then write a sidecar `<request>.nudged` marker so it is never repeated for this status.
  2. UNDISPATCHED    - a request.json exists with no matching .status.json at all after --undispatched-after
     seconds. watoom-game-worker.timer polls every 30s when idle, so this means the worker never even picked
     the request up (bridge/timer down, or a bug such as T-0133's agent allow-list drift). It is reported for
     the operator AND the coordinator gets exactly one resume prompt saying the job never ran, so it stops
     waiting on QUEUED forever; a `<request>.undispatched` marker keeps that prompt one-shot.

Read-only except for: (a) writing the `.nudged`/`.undispatched` markers (idempotency bookkeeping, not project data) and
(b) the one resume-prompt HTTP call, which is the exact same safe, idempotent action game_worker_bridge.py
already performs on every terminal job -- this script only resends it when the first attempt apparently did
not get through. It never writes receipts, never touches a model lease, never replays or duplicates a request.

Usage
-----
  game_session_watchdog.py                      # scan, nudge, print a JSON report
  game_session_watchdog.py --dry-run             # scan and report only, no prompt sent, no marker written
  game_session_watchdog.py --report DIR          # also append a line to DIR/game-session-watchdog.log
"""
import argparse
import json
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from maintenance_guard import Maintenance  # noqa: E402

GAMES = pathlib.Path('/data/ai/projects/games')
TERMINAL = {'COMPLETED', 'FAILED', 'STALE_RESULT', 'RECONCILIATION_REQUIRED'}
STALE_AFTER_DEFAULT = 20 * 60
UNDISPATCHED_AFTER_DEFAULT = 20 * 60


def worker_dirs(project):
    d = project / '.opencode' / 'worker-requests'
    if d.is_dir():
        yield d


def scan(stale_after, undispatched_after):
    now = time.time()
    nudges, undispatched = [], []
    if not GAMES.is_dir():
        return nudges, undispatched
    for project in sorted(p for p in GAMES.iterdir() if p.is_dir()):
        for d in worker_dirs(project):
            all_json = list(d.glob('*.json'))
            if not all_json:
                continue
            # Only the single most-recently-touched file in this project's whole worker-requests directory is
            # a nudge candidate: nudging every historical terminal status (there can be hundreds) would spam
            # every project's session on first run. "Most recent thing has gone quiet" is the actual signal.
            latest = max(all_json, key=lambda p: p.stat().st_mtime)
            if latest.name.endswith('.status.json'):
                req = d / (latest.name[: -len('.status.json')] + '.json')
                status = latest
            else:
                req, status = latest, d / (latest.stem + '.status.json')
            if not req.is_file():
                continue
            if not status.is_file():
                age = now - req.stat().st_mtime
                if age > undispatched_after:
                    try:
                        v = json.loads(req.read_text())
                    except (OSError, ValueError):
                        v = {}
                    marker = d / (req.stem + '.undispatched')
                    undispatched.append({'project': str(project), 'request': str(req), 'age_sec': round(age),
                                         'session_id': v.get('session_id'), 'job': v.get('job'),
                                         'operation': v.get('operation'), 'marker': str(marker),
                                         'prompted': marker.exists()})
                continue
            try:
                doc = json.loads(status.read_text())
            except (OSError, ValueError):
                continue
            if doc.get('status') not in TERMINAL:
                continue
            age = now - status.stat().st_mtime
            if age < stale_after:
                continue
            marker = d / (req.stem + '.nudged')
            if marker.exists():
                continue
            try:
                session_id = json.loads(req.read_text()).get('session_id')
            except (OSError, ValueError):
                session_id = None
            if not session_id:
                continue
            nudges.append({'project': str(project), 'status_file': str(status), 'marker': str(marker),
                          'session_id': session_id, 'job': doc.get('job'), 'operation': doc.get('operation'),
                          'terminal_status': doc.get('status'), 'age_sec': round(age)})
    return nudges, undispatched


def coordinator_of(m, session_id):
    """Walk parentID the same way game_worker_bridge.py does to find the top-level coordinator session."""
    coordinator, current = session_id, m.request('/api/session/' + session_id).get('data', {})
    while current.get('parentID'):
        coordinator = current['parentID']
        current = m.request('/api/session/' + coordinator).get('data', {})
    return coordinator


def nudge(m, item):
    coordinator = coordinator_of(m, item['session_id'])
    text = ('A worker job may not have reached you: ' + str(item['operation']) + ' job ' + str(item['job']) +
            ' finished with status ' + str(item['terminal_status']) + ' ' + str(item['age_sec']) +
            's ago (status file ' + item['status_file'] + '). This is a one-time follow-up resume from the ' +
            'session watchdog, not a new request -- read the existing status and receipt before acting; ' +
            'do not duplicate or replay the job. If the underlying issue was already fixed (e.g. a request ' +
            'manifest edited since this run), re-submit the SAME job name to pick up the new manifest.')
    m.request('/api/session/' + coordinator + '/prompt', {'text': text, 'resume': True})


def nudge_undispatched(m, item):
    coordinator = coordinator_of(m, item['session_id'])
    text = ('The game worker never picked up ' + str(item['operation']) + ' job ' + str(item['job']) +
            ': no status after ' + str(item['age_sec']) + 's (request ' + item['request'] + '). It did not run '
            'and will not run, so stop waiting on QUEUED. This is a one-time notice from the session watchdog; the '
            'operator has been told. If the result is still needed, submit it once under a NEW job name; if that '
            'also stays QUEUED, record the blocker and continue with other work.')
    m.request('/api/session/' + coordinator + '/prompt', {'text': text, 'resume': True})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--stale-after', type=int, default=STALE_AFTER_DEFAULT)
    ap.add_argument('--undispatched-after', type=int, default=UNDISPATCHED_AFTER_DEFAULT)
    ap.add_argument('--dry-run', action='store_true', help='report only; send no prompt, write no marker')
    ap.add_argument('--report', type=pathlib.Path, help='dir to append a game-session-watchdog.log line to')
    args = ap.parse_args()

    nudges, undispatched = scan(args.stale_after, args.undispatched_after)
    acted, failed = [], []
    pending = [i for i in undispatched if i['session_id'] and not i['prompted']]
    if (nudges or pending) and not args.dry_run:
        m = Maintenance('watoom-code', 'watoom-code', pathlib.Path('/tmp'), True, True)
        for send, item in [(nudge, i) for i in nudges] + [(nudge_undispatched, i) for i in pending]:
            try:
                send(m, item)
                pathlib.Path(item['marker']).touch()
                item['prompted'] = True
                acted.append({'job': item['job'], 'session_id': item['session_id']})
            except Exception as e:  # noqa: BLE001
                failed.append({'job': item['job'], 'error': str(e)[:300]})

    report = {'ts': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'dry_run': args.dry_run,
              'stale_candidates': nudges if args.dry_run else len(nudges), 'nudged': acted, 'nudge_failed': failed,
              'undispatched': undispatched}
    print(json.dumps(report, indent=2))

    if args.report:
        try:
            args.report.mkdir(parents=True, exist_ok=True)
            with (args.report / 'game-session-watchdog.log').open('a') as f:
                f.write(json.dumps({'ts': report['ts'], 'nudged': len(acted), 'nudge_failed': len(failed),
                                    'undispatched': len(undispatched)}) + '\n')
        except OSError as e:
            print('[watchdog] could not write report: ' + str(e), file=sys.stderr)

    sys.exit(1 if failed or undispatched else 0)


if __name__ == '__main__':
    main()
