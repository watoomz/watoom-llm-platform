#!/usr/bin/env python3
"""Point this checkout at your own domain, network and GitHub account.

The published source uses placeholders instead of the original author's values:
  homelab.example       domain (hosts look like glance.internal.homelab.example)   (--domain)
  10.99.x.y             LAN / VLAN addressing, e.g. host 10.99.20.225              (--subnet, first two octets)
  192.168.250.225       the DMZ interface address                                  (--dmz-address)
  YOUR_GITHUB_USER      GitHub account used for source links                       (--github-owner)
  10.242.0.x            k3s pod network (your cluster's own default may differ)    (--pod-subnet)
  10.243.x.y            k3s service network (your cluster's own default may differ) (--svc-subnet)
  agent.example         agent/automation identity email domain                      (--agent-domain)
  Agent Export           agent/automation identity display name                      (--agent-name)
  homelab-host          the server's inventory/host name                            (--host-name)
  RIG_USER              the Windows rig account in C:\\Users\\RIG_USER paths          (--rig-user)

Examples:
  python3 tools/set-domain.py --domain lab.mydomain.net --subnet 10.10 --dry-run
  python3 tools/set-domain.py --domain lab.mydomain.net --subnet 10.10 --dmz-address 192.168.5.20 --github-owner me
  python3 tools/set-domain.py --pod-subnet 10.42.0 --svc-subnet 10.43 --agent-domain agents.mydomain.net --agent-name "My Agent"

Only options you pass are changed. It rewrites text files in place (skips .git and binaries) and prints every
file it changed. Run it once, review `git diff`, and commit. Use --dry-run first. Disk paths are handled
separately by tools/set-paths.py.
"""
import argparse, pathlib, re, sys

PLACEHOLDER_DOMAIN = 'homelab.example'
PLACEHOLDER_SUBNET = '10.99'
PLACEHOLDER_DMZ = '192.168.250.225'
PLACEHOLDER_OWNER = 'YOUR_GITHUB_USER'
PLACEHOLDER_POD_SUBNET = '10.242.0'
PLACEHOLDER_SVC_SUBNET = '10.243'
PLACEHOLDER_AGENT_DOMAIN = 'agent.example'
PLACEHOLDER_AGENT_NAME = 'Agent Export'
PLACEHOLDER_HOST = 'homelab-host'
PLACEHOLDER_RIG_USER = 'RIG_USER'
SKIP_DIRS = {'.git', 'node_modules', '__pycache__'}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--domain', help='your base domain, e.g. lab.mydomain.net')
    ap.add_argument('--subnet', help='first two octets of your LAN, e.g. 10.10 (the placeholder is 10.99)')
    ap.add_argument('--dmz-address', help='address of the DMZ interface')
    ap.add_argument('--github-owner', help='your GitHub user or organisation')
    ap.add_argument('--pod-subnet', help='your k3s pod network, first three octets, e.g. 10.42.0 (the placeholder is 10.242.0)')
    ap.add_argument('--svc-subnet', help='your k3s service network, first two octets, e.g. 10.43 (the placeholder is 10.243)')
    ap.add_argument('--agent-domain', help='domain for your agent/automation identity email, e.g. agents.mydomain.net')
    ap.add_argument('--agent-name', help='display name for your agent/automation identity, e.g. "My Agent"')
    ap.add_argument('--host-name', help='your server host name (the placeholder is homelab-host)')
    ap.add_argument('--rig-user', help='your Windows rig account name (the placeholder is RIG_USER)')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    if not any((a.domain, a.subnet, a.dmz_address, a.github_owner, a.pod_subnet, a.svc_subnet, a.agent_domain, a.agent_name,
                a.host_name, a.rig_user)):
        sys.exit('Nothing to do: pass at least one of --domain, --subnet, --dmz-address, --github-owner, '
                  '--pod-subnet, --svc-subnet, --agent-domain, --agent-name, --host-name, --rig-user')
    for v, flag in ((a.host_name, '--host-name'), (a.rig_user, '--rig-user')):
        if v and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', v):
            sys.exit(flag + ' may contain only letters, digits, dot, underscore and hyphen')
    if a.domain and not re.fullmatch(r'[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?', a.domain):
        sys.exit('--domain must be a plain domain name, e.g. lab.mydomain.net')
    if a.subnet and not re.fullmatch(r'(?:25[0-5]|2[0-4]\d|1?\d?\d)\.(?:25[0-5]|2[0-4]\d|1?\d?\d)', a.subnet):
        sys.exit('--subnet must be two octets such as 10.10')
    if a.dmz_address and not re.fullmatch(r'(?:\d{1,3}\.){3}\d{1,3}', a.dmz_address):
        sys.exit('--dmz-address must be an IPv4 address')
    if a.github_owner and not re.fullmatch(r'[A-Za-z0-9-]+', a.github_owner):
        sys.exit('--github-owner may contain only letters, digits and hyphens')
    if a.pod_subnet and not re.fullmatch(r'(?:\d{1,3}\.){2}\d{1,3}', a.pod_subnet):
        sys.exit('--pod-subnet must be three octets such as 10.42.0')
    if a.svc_subnet and not re.fullmatch(r'(?:25[0-5]|2[0-4]\d|1?\d?\d)\.(?:25[0-5]|2[0-4]\d|1?\d?\d)', a.svc_subnet):
        sys.exit('--svc-subnet must be two octets such as 10.43')
    if a.agent_domain and not re.fullmatch(r'[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?', a.agent_domain):
        sys.exit('--agent-domain must be a plain domain name, e.g. agents.mydomain.net')
    here = pathlib.Path(__file__).resolve().parents[1]
    rules = []
    if a.domain:
        rules.append((re.compile(r'\b' + re.escape(PLACEHOLDER_DOMAIN) + r'\b'), a.domain))
    if a.subnet:
        rules.append((re.compile(r'\b' + re.escape(PLACEHOLDER_SUBNET) + r'\.(\d{1,3})\.(\d{1,3})\b'), a.subnet + r'.\1.\2'))
    if a.dmz_address:
        rules.append((re.compile(r'\b' + re.escape(PLACEHOLDER_DMZ) + r'\b'), a.dmz_address))
    if a.github_owner:
        rules.append((re.compile(r'\b' + re.escape(PLACEHOLDER_OWNER) + r'\b'), a.github_owner))
    if a.pod_subnet:
        rules.append((re.compile(r'\b' + re.escape(PLACEHOLDER_POD_SUBNET) + r'\.(\d{1,3})\b'), a.pod_subnet + r'.\1'))
    if a.svc_subnet:
        rules.append((re.compile(r'\b' + re.escape(PLACEHOLDER_SVC_SUBNET) + r'\.(\d{1,3})\.(\d{1,3})\b'), a.svc_subnet + r'.\1.\2'))
    if a.agent_domain:
        rules.append((re.compile(r'\b' + re.escape(PLACEHOLDER_AGENT_DOMAIN) + r'\b'), a.agent_domain))
    if a.host_name:
        rules.append((re.compile(r'\b' + re.escape(PLACEHOLDER_HOST) + r'\b'), a.host_name))
    if a.rig_user:
        rules.append((re.compile(r'\b' + re.escape(PLACEHOLDER_RIG_USER) + r'\b'), a.rig_user))
    if a.agent_name:
        rules.append((re.compile(r'\b' + re.escape(PLACEHOLDER_AGENT_NAME) + r'\b'), a.agent_name))
    changed = 0
    for path in sorted(here.rglob('*')):
        if not path.is_file() or SKIP_DIRS & set(path.parts) or path.is_symlink() or path.resolve() == pathlib.Path(__file__).resolve():
            continue
        try:
            text = path.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        new = text
        for pattern, value in rules:
            new = pattern.sub(value, new)
        if new != text:
            changed += 1
            print(('would change ' if a.dry_run else 'changed ') + str(path.relative_to(here)))
            if not a.dry_run:
                path.write_text(new)
    print('%d file(s) %s' % (changed, 'would change' if a.dry_run else 'changed'))


if __name__ == '__main__':
    main()
