#!/usr/bin/env python3
"""Drive a WatooM-Code model session from the operator side: start or continue a session with a prompt file, approve its
game-worker permission, wait for the turn to end, and say what happened (tools used, worker jobs, stalled or not).

  drive_model_session.py start  --project /data/ai/projects/games/<p> --prompt-file F [--agent watoom-builder] [--title T] [--watch]
  drive_model_session.py send   --session ses_x --prompt-file F [--watch]
  drive_model_session.py watch  --session ses_x [--max-min 90] [--auto-resume F]
  drive_model_session.py status --session ses_x [--project P]

A turn that ends with a BLOCKED report and no tool call is a STALL (the guard lock-in that a new prompt now clears; a stuck
older session may still need `start`). `--auto-resume F` sends F once when a watched turn ends stalled. Needs root (the maintenance guard).
"""
import argparse, collections, glob, json, os, pathlib, sys, tempfile, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ALLOWED_PERMISSIONS = {'watoom_game_worker'}


def summarise(messages):
    """-> {tools: Counter, last_text, stalled, last_tool_input} from a session's messages (newest first, as the API returns them)."""
    tools = collections.Counter(); last_text = None; last_turn_tools = 0; seen_assistant = False
    for x in messages:
        if x.get('type') != 'assistant':
            continue
        n = 0
        for p in x.get('content') or []:
            if not isinstance(p, dict):
                continue
            if p.get('type') == 'tool':
                tools[p.get('name')] += 1; n += 1
            elif p.get('type') == 'text' and last_text is None:
                last_text = p.get('text', '')
        if not seen_assistant:
            last_turn_tools = n; seen_assistant = True
    stalled = bool(last_text) and '"BLOCKED"' in last_text.replace(' ', '').replace('\n', '').replace('"result":', '"result":') and last_turn_tools == 0
    return {'tools': dict(tools), 'last_text': last_text, 'stalled': stalled}


def job_statuses(project):
    """{job: status} from <project>/.opencode/worker-requests/*.status.json, newest request first."""
    rows = []
    for f in glob.glob(os.path.join(project, '.opencode/worker-requests/*.status.json')):
        try:
            d = json.load(open(f)); rows.append((os.path.getmtime(f), d.get('job'), d.get('status'), (d.get('reason') or '')[:90]))
        except (OSError, ValueError):
            continue
    return [(j, s, r) for _, j, s, r in sorted(rows, reverse=True)]


def client():
    from maintenance_guard import Maintenance
    return Maintenance('watoom-code', 'watoom-code', pathlib.Path(tempfile.mkdtemp()), True, True)


def wait_idle(m, tries=40):
    for _ in range(tries):
        try:
            if not m.request('/api/session/active')['data']:
                return True
        except Exception:
            pass
        time.sleep(3)
    return False


def send(m, session, text):
    if not wait_idle(m):
        raise SystemExit('app is busy with another session; not sending')
    m.request('/api/session/' + session + '/prompt', {'text': text})


def watch(m, session, max_min=90, resume_text=None, out=print):
    t0 = time.time(); seen = set(); idle = 0; resumed = False
    while time.time() - t0 < max_min * 60:
        try:
            for r in m.request('/api/session/' + session + '/permission')['data']:
                if r['id'] in seen:
                    continue
                seen.add(r['id']); out('PERMISSION ' + str(r.get('action')))
                if r.get('action') in ALLOWED_PERMISSIONS:
                    m.request('/api/session/' + session + '/permission/' + r['id'] + '/reply', {'decision': 'once'}); out('approved once')
            idle = idle + 1 if session not in m.request('/api/session/active')['data'] else 0
            if idle >= 2 and time.time() - t0 > 60:
                info = summarise(m.request('/api/session/' + session + '/message')['data'])
                if info['stalled'] and resume_text and not resumed:
                    send(m, session, resume_text); resumed = True; idle = 0; out('stalled: sent the resume prompt'); continue
                break
        except Exception as e:
            out('retry ' + repr(e)[:80])
        time.sleep(20)
    out('DONE %ds' % (time.time() - t0))


def report(m, session, project=None, out=print):
    info = summarise(m.request('/api/session/' + session + '/message')['data'])
    out('tools: %s' % info['tools']); out('stalled: %s' % info['stalled'])
    if info['last_text']:
        out('last text: ' + info['last_text'][:600].replace('\n', ' '))
    if project:
        for job, status, reason in job_statuses(project)[:8]:
            out('job %-18s %-26s %s' % (job, status, reason))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('start'); p.add_argument('--project', required=True); p.add_argument('--prompt-file', required=True)
    p.add_argument('--agent', default='watoom-builder'); p.add_argument('--title', default='model session'); p.add_argument('--watch', action='store_true'); p.add_argument('--max-min', type=int, default=90)
    p = sub.add_parser('send'); p.add_argument('--session', required=True); p.add_argument('--prompt-file', required=True); p.add_argument('--watch', action='store_true'); p.add_argument('--max-min', type=int, default=90)
    p = sub.add_parser('watch'); p.add_argument('--session', required=True); p.add_argument('--max-min', type=int, default=90); p.add_argument('--auto-resume')
    p = sub.add_parser('status'); p.add_argument('--session', required=True); p.add_argument('--project')
    a = ap.parse_args(argv)
    if os.geteuid() != 0:
        raise SystemExit('needs root')
    m = client()
    if a.cmd == 'start':
        if not wait_idle(m):
            raise SystemExit('app is busy with another session; not starting')
        s = m.request('/api/session', {'agent': a.agent, 'location': {'directory': a.project}, 'title': a.title})['data']['id']
        print('session', s, flush=True)
        m.request('/api/session/' + s + '/prompt', {'text': pathlib.Path(a.prompt_file).read_text()})
        if a.watch:
            watch(m, s, a.max_min); report(m, s, a.project)
    elif a.cmd == 'send':
        send(m, a.session, pathlib.Path(a.prompt_file).read_text())
        if a.watch:
            watch(m, a.session, a.max_min)
    elif a.cmd == 'watch':
        watch(m, a.session, a.max_min, pathlib.Path(a.auto_resume).read_text() if a.auto_resume else None)
    else:
        report(m, a.session, a.project)
    return 0


if __name__ == '__main__':
    sys.exit(main())
