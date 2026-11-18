#!/usr/bin/env python3
"""Owned animation catalogue (SQLite) built from the Fab library, grouped by what the animations are for.

Sources, all read-only: (1) the authenticated UE-format library feed (raw records: description, Fab category, versions), (2) listing details for
owned items that feed omits (non-Unreal formats; resolved by title through Fab's bearer endpoints) and (3) an owner-provided copy of the Fab
"My Library > Animations" page (the only complete list of what is owned: titles, publisher, local size). Nothing is downloaded and no credentials are stored.

  animation_catalog.py build --raw RAW.json --listings LISTINGS.json --owner-list LIST.txt [--db PATH]
  animation_catalog.py refresh [--owner-list LIST.txt]   # re-runs the two bun dumps then builds
Query: sqlite3 animations.db "select primary_type,count(*) from packs group by 1"; views v_packs_by_type, v_clips_by_type.
"""
import argparse, datetime, glob, hashlib, json, os, pathlib, re, sqlite3, subprocess, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
DOC_PATH = HERE.parent.parent / 'docs/guide/animation-library.md'
DEFAULT_DB = pathlib.Path('/data/ai/assets/catalog/animations.db')
OWNER_LIST = pathlib.Path('/data/ai/assets/catalog/sources/fab-library-animations-20261107.txt')
FAB_DISK = pathlib.Path('/data/ai/assets/fab')

# type -> (description, keyword regex). Scores add up per match; the highest-scoring type is primary, every type with a hit is listed.
TYPES = {
    'fighting': ('Hand-to-hand combat: strikes, martial arts, brawling, grapples, blocks, combos', r'\bfight|\bcombat|martial|brawl|punch|kick\b|boxing|kung ?fu|karate|judo|mma\b|\bstrike|\bjab\b|combo|grapple|takedown|choke|throat|\bblock\b|knee|elbow|sweep'),
    'weapons_firearms': ('Guns: rifles, pistols, shooting, aiming, reloads, FPS arms animations', r'rifle|pistol|\bgun|shooting|\bfps\b|ak-?47|aks74|shotgun|tactical|reload|\baim|handgun|soldier|sniper|bullet'),
    'weapons_melee': ('Held melee weapons: swords, spears, axes, staves', r'sword|spear|katana|\baxe\b|blade|\bstaff|\bmace|halberd|lance|dagger|knife'),
    'locomotion': ('Moving around: idle, walk, run, strafe, sprint, crawl, gait cycles, motion matching sets', r'locomotion|\bwalk|\brun\b|\bjog|sprint|\bidle|strafe|\bgait|motion matching|crawl|levitat|8 way|turn in place|\bstride'),
    'traversal': ('Getting past things: climbing, ladders, ziplines, gliding, dashes, jumps, swimming, vaulting', r'ladder|climb|zipline|skydiv|glid|paraglid|\bdash|parkour|vault|\bjump|swim|\bfall|\bleap|mantle|\broll'),
    'reactions': ('Taking damage and dying: hits, deaths, falls, injuries, exhaustion, lying/dead poses', r'\bdeath|\bdying|\bdead|\bdie\b|hit by|hit react|injur|exhaust|ragdoll|struggle|lying|wound|\bhurt|knock ?down|stagger|collapse|limp'),
    'emotes_social': ('Communication and expression: emotes, gestures, dances, attitudes, talking, sign language, mudras', r'emote|\bdance|gesture|attitude|\btalk|\bwave\b|social|sign language|mudra|greet|celebrat|taunt|\bshrug|\bnod\b|conversation'),
    'poses_hands': ('Static poses and hand/finger sets', r'finger|hand pose|\bpose\b|poses\b|hand animation'),
    'daily_life': ('Everyday actions and object interaction: sitting, kneeling, doors, pick-ups, vehicles, tools', r'daily|lifestyle|interaction|\bsit\b|squat|kneel|motorcycle|vehicle|flashlight|\bdoor|pick ?up|carry|\bdrink|\beat\b|phone|\bbike'),
    'sport_fitness': ('Exercise and sport: gym, workouts, yoga, qi gong, stretching', r'sport|gym|fitness|workout|yoga|qi ?gong|stretch|kettlebell|dumbbell|calisthenic|pilates'),
    'magic_fantasy': ('Spellcasting and fantasy movement', r'mage|magic|spell|wizard|fantasy|\bwing|\bfly\b|flying|levitat|sorcer'),
    'creature_zombie': ('Zombies, creatures and animals (rig-specific)', r'zombie|creature|animal|dino|monster|rhino|raptor'),
}
WEIGHT = {'poses_hands': 0.3, 'daily_life': 0.5, 'reactions': 0.7, 'emotes_social': 0.7, 'weapons_firearms': 0.8, 'traversal': 0.8, 'magic_fantasy': 0.7, 'creature_zombie': 0.7}
GENERIC = 'general_variety'
PRIORITY = ['fighting', 'weapons_firearms', 'weapons_melee', 'reactions', 'traversal', 'locomotion', 'sport_fitness', 'emotes_social', 'poses_hands', 'magic_fantasy', 'daily_life', 'creature_zombie']
FAB_CATEGORY_HINT = {'Combat': 'fighting', 'Gestures': 'emotes_social', 'Locomotion / Gaits': 'locomotion'}

RIG_PATTERNS = [
    ('ue5_mannequin', r'ue5 mannequin|\bmanny\b|\bquinn\b|ue5 skeleton|unreal engine 5 skeleton|epic skeleton|\blyra\b|ue5 standard'),
    ('ue4_mannequin', r'ue4 mannequin|ue4 skeleton|ue4 standard|unreal engine 4 skeleton'),
    ('metahuman', r'metahuman'),
    ('mixamo', r'mixamo'),
    ('reallusion', r'reallusion|actorcore|character creator|\bcc[34]\b|iclone'),
    ('unity_humanoid', r'mecanim|unity humanoid|humanoid rig'),
    ('daz', r'\bdaz\b|genesis [0-9]'),
    ('paragon', r'paragon'),
]

TARGET_NOTES = {  # how a pack is applied, by the evidence about its skeleton/format
    'ue5_mannequin': 'Bone names match the MetaHuman body skeleton: retarget with the identity map (tools: retarget_animation.gd).',
    'ue4_mannequin': 'UE4 mannequin names differ slightly from MetaHuman: use the humanoid map in retarget_animation.gd (spine/clavicle/arm names align; extra twist bones are skipped).',
    'mixamo': 'Mixamo-style names (Hips, Spine, Spine1, Spine2, LeftArm...): use the mixamo map in retarget_animation.gd.',
    'unity_humanoid': 'Unity Humanoid assets only work in Unity unless an FBX is shipped; check the format list before use.',
    'reallusion': 'Reallusion/CC rig: map bones by name with the humanoid map; verify the rest pose (A vs T).',
    'metahuman': 'Authored for MetaHuman: apply directly through the Unreal MetaHuman IK retargeter or export through the pipeline.',
    'paragon': 'Paragon characters have their own rigs; the Manny-retargeted set is applied like a UE5 mannequin pack.',
    'unspecified': 'Rig not stated: inspect the FBX/uasset skeleton (retarget_animation.gd --inspect) before applying.',
    'creature': 'Own rig (Pelvis/Spine naming): apply to the mesh shipped with the pack.',
}


def plain(html):
    t = re.sub(r'<[^>]+>', ' ', html or '')
    t = re.sub(r'&nbsp;|&amp;|&#\d+;|&[a-z]+;', ' ', t)
    return re.sub(r'\s+', ' ', t).strip()


def norm(s):
    return ''.join(c for c in s.lower() if c.isalnum())


def classify(text, fab_category=None, title=None):
    """Keyword typing. Title hits count triple; a Fab 'Variety' pack only gets a specific type on a strong signal (generic mixes mention many words)."""
    scores = {}
    for name, (_, rx) in TYPES.items():
        n = (len(re.findall(rx, text, re.I)) + (3 * len(re.findall(rx, title, re.I)) if title else 0)) * WEIGHT.get(name, 1.0)
        if n >= 0.5:
            scores[name] = n
    types = [t for t in PRIORITY if t in scores]
    hint = FAB_CATEGORY_HINT.get(fab_category)
    if hint and hint not in types:
        types.append(hint)
        scores[hint] = 1
    if not types:
        return GENERIC, [GENERIC]
    best = max(types, key=lambda t: (scores[t], -PRIORITY.index(t)))
    if fab_category == 'Variety' and scores[best] < 4:
        return GENERIC, [GENERIC] + [t for t in types if scores[t] >= 2]
    return best, types


def rigs(text):
    found = [name for name, rx in RIG_PATTERNS if re.search(rx, text, re.I)]
    return found or ['unspecified']


def clip_count(text):
    nums = [int(m.replace(',', '')) for m in re.findall(r'(\d[\d,]*)\+?\s*(?:unique\s+|different\s+|mocap\s+|game\s*ready\s+)?(?:animations?|anims|motions?|clips|poses|moves)\b', text, re.I)]
    nums = [n for n in nums if 0 < n < 20000]
    return max(nums) if nums else None


def skeleton_evidence(path):
    """What bone naming does this FBX/GLB use? Reads names out of the file bytes; no FBX SDK needed."""
    try:
        blob = open(path, 'rb').read(3_000_000)
    except OSError:
        return 'unreadable'
    names = {n.decode() for n in set(re.findall(rb'[A-Za-z][A-Za-z0-9_:\.]{2,40}', blob))}
    if any(n.startswith('mixamorig') for n in names):
        return 'mixamo (mixamorig: prefix)'
    if {'spine_01', 'upperarm_l', 'pelvis'} <= names:
        return 'ue5_mannequin (spine_01/upperarm_l/pelvis)'
    if any(n.startswith('Bip0') for n in names):
        return '3dsmax_biped (Bip0x)'
    if {'Hips', 'Spine', 'Spine1', 'Spine2'} <= names or ({'Hips', 'Spine1', 'Spine2'} <= names):
        return 'mixamo_style (Hips/Spine/Spine1/Spine2, no prefix)'
    if {'Pelvis', 'Spine', 'Spine1'} <= names:
        return 'pelvis_spine (Pelvis/Spine/Spine1)'
    return 'unknown'


def parse_owner_list(path):
    rows = []
    for line in pathlib.Path(path).read_text().splitlines():
        if not line.strip():
            continue
        parts = line.split('|')
        rows.append({'title': '|'.join(parts[:-2]).strip(), 'publisher': parts[-2].strip(), 'disk': parts[-1].strip()})
    return rows


def fab_disk_index():
    idx = {}
    if FAB_DISK.is_dir():
        for p in FAB_DISK.iterdir():
            m = re.search(r'-([0-9a-f]{8})$', p.name)
            if m and p.is_dir():
                idx[m.group(1)] = p
    return idx


def dir_size(p):
    return sum(f.stat().st_size for f in p.rglob('*') if f.is_file())


SCHEMA = '''
PRAGMA journal_mode=DELETE;
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE types(type TEXT PRIMARY KEY, description TEXT, pack_count INTEGER, clip_count INTEGER);
CREATE TABLE packs(
  id TEXT PRIMARY KEY, listing_uid TEXT, title TEXT NOT NULL, publisher TEXT,
  source TEXT, kind TEXT, fab_category TEXT, primary_type TEXT, rig_claims TEXT, formats TEXT, engine_versions TEXT,
  clip_count_claim INTEGER, is_free INTEGER, price TEXT, license TEXT, url TEXT, description TEXT,
  in_owner_list INTEGER, fab_on_disk TEXT, server_path TEXT, server_bytes INTEGER, skeleton_evidence TEXT,
  apply_notes TEXT, notes TEXT, retarget_library TEXT, retarget_clips INTEGER, retarget_skipped INTEGER);
CREATE TABLE pack_types(pack_id TEXT, type TEXT, PRIMARY KEY(pack_id, type));
CREATE TABLE clips(
  id INTEGER PRIMARY KEY, pack_id TEXT, name TEXT, type TEXT, path TEXT, format TEXT, bytes INTEGER);
CREATE TABLE recipes(id TEXT PRIMARY KEY, applies_to TEXT, target TEXT, status TEXT, steps TEXT, caveats TEXT);
CREATE VIEW v_packs_by_type AS
  SELECT t.type, p.title, p.publisher, p.kind, p.rig_claims, p.formats, p.clip_count_claim, p.is_free,
         CASE WHEN p.server_path IS NOT NULL THEN 'yes' ELSE 'no' END AS on_server, p.url
  FROM pack_types t JOIN packs p ON p.id = t.pack_id ORDER BY t.type, p.title;
CREATE VIEW v_clips_by_type AS
  SELECT c.type, c.name, p.title AS pack, p.rig_claims, p.skeleton_evidence, c.path
  FROM clips c JOIN packs p ON p.id = c.pack_id ORDER BY c.type, c.name;
'''

RECIPES = [
    ('ue5-direct', 'packs whose skeleton uses UE5 mannequin names (Sport/Gym, Lyra, Manny-retargeted Paragon, most Unreal packs once exported to FBX)', 'godot (MetaHuman body skeleton)', 'implemented',
     '1) Download the pack (owner approval per asset, watoom-fab-owned-assets). 2) Import its FBX/GLB into the Godot project. 3) Run retarget_animation.gd --source <fbx> --character res://metahuman/<Name>/<Name>.tscn --map identity: it reads each clip, converts bone rotations to character-space deltas and writes them onto the MetaHuman body skeleton as an Animation in an AnimationLibrary. 4) Play it with the character\'s AnimationPlayer; the head follows because it copies the body pose.',
     'Hip translation is scaled by the height ratio; root motion is dropped unless --keep-root is given. Facial animation is not carried (no RigLogic in Godot).'),
    ('mixamo-style', 'packs with Mixamo-style bone names (Hips/Spine/Spine1/Spine2/LeftArm..., e.g. Motifect, Mocap.in, many FBX mocap packs)', 'godot (MetaHuman body skeleton)', 'implemented',
     'Same as ue5-direct with --map mixamo. The map pairs Hips->pelvis, Spine/Spine1/Spine2->spine_01/02/03, Neck/Head->neck_01/head, shoulders and limbs by side, fingers by name.',
     'Spine-chain counts differ (Mixamo has 3, MetaHuman 5): the extra MetaHuman spine bones keep their rest pose and the rotation is shared across the mapped ones. Check feet for sliding on first use.'),
    ('unreal-uasset', 'Unreal-format animation sequences (.uasset)', 'unreal (MetaHuman) / godot via export', 'documented, not run here',
     'In Unreal 5.8: open the pack and the MetaHuman body skeleton, create an IK Retargeter (source: pack IK rig, target: MetaHuman IK rig), batch-retarget the sequences, then play them on the MetaHuman Blueprint or export FBX/glTF for Godot and use ue5-direct.',
     'The MetaHuman plugin must be enabled in the project (see watoom-metahuman copy-to-project). Headless export of animation sequences is not wired in the unreal-export pipeline yet.'),
    ('unity-only', 'packs whose only format is Unity (.anim/.unitypackage)', 'none', 'blocked',
     'Unity-only animation clips cannot be read by Godot or Unreal. Check the listing for an FBX; otherwise use the pack only inside Unity.', 'Brawler Animations, Martial Art Animations Sample and Free Pack - Basic Motions are Unity-only listings.'),
    ('creature-rig', 'zombie/creature/animal packs with their own skeleton', 'same-rig meshes only', 'documented',
     'Apply to the mesh that ships with the pack (or any mesh skinned to the same skeleton). They do not retarget onto a human MetaHuman.', 'Use for zombies/animals already in the game projects.'),
    ('sims-package', 'Sims 4 .package animation files in /data/ai/assets/animations', 'none', 'not usable',
     'These are Sims 4 community packages (game-specific binary resources); they cannot be imported to Godot or Unreal by this pipeline.', 'Kept only so the inventory is complete.'),
]


def build(args):
    raw = json.load(open(args.raw))
    listings = json.load(open(args.listings)) if args.listings and os.path.exists(args.listings) else []
    owner = parse_owner_list(args.owner_list)
    owner_by = {norm(r['title']): r for r in owner}
    disk = fab_disk_index()
    rt_path = pathlib.Path('/data/ai/assets/catalog/sources/retarget-results.json')
    rt = json.loads(rt_path.read_text()) if rt_path.exists() else {}
    packs = {}
    ANIM_KW = re.compile(r'\banim(ation|ations)?\b|mocap|motion pack|animset|anims\b', re.I)

    for x in raw:
        r = x['raw']
        text = x['title'] + ' ' + plain(r.get('description'))
        cats = [c['name'] for c in r.get('categories') or []]
        lt = r.get('listingType')
        explicit = bool(re.search(r'(\d[\d,]*)\+?\s*(?:unique\s+)?(?:animations?|anims|motions?|clips)\b', text, re.I)) or bool(re.search(r'with animations|animations? (included|pack|set)', text, re.I))
        if lt == 'Animations':
            kind = 'animation_pack'
        elif x['type'] == 'CODE_PLUGIN' and ANIM_KW.search(x['title']):
            kind = 'tool'
        elif lt in ('3D', 'Game Templates', 'Game Systems', 'Legacy') and re.search(r'\banimat(ed|ion|ions)\b|\banims\b|with animations|animset', x['title'], re.I) and not re.search(r'tree|grass|foliage|water|sprite|font|logo', x['title'], re.I):
            kind = 'bundled'
        else:
            continue
        lu = ((r.get('customAttributes') or [{}])[0] or {}).get('ListingIdentifier')
        versions = sorted({v for pv in r.get('projectVersions', []) for v in pv.get('engineVersions', [])})
        packs[x['id']] = dict(id=x['id'], listing_uid=lu, title=x['title'], publisher=(r.get('seller') or {}).get('name') if isinstance(r.get('seller'), dict) else None,
                              source='fab-ue-library', kind=kind, fab_category=cats[0] if cats else None, formats=['unreal'], engine_versions=versions,
                              url=r.get('url'), description=plain(r.get('description')), text=text, price=None, license=None)

    for e in listings:
        if 'listing' not in e:
            continue
        l = e['listing']
        cat = l.get('category') or {}
        desc = plain(l.get('description'))
        fmts = [f['code'] for f in e.get('formats', []) if f.get('code')]
        engines = sorted({v for f in e.get('formats', []) for fl in f.get('files', []) for v in (fl.get('engineVersions') or [])})
        price = (l.get('startingPrice') or {})
        packs['uid:' + e['uid']] = dict(id='uid:' + e['uid'], listing_uid=e['uid'], title=l.get('title') or e['title'], publisher=(l.get('user') or {}).get('sellerName'),
                                        source='fab-library-extra', kind='animation_pack', fab_category=cat.get('name') if isinstance(cat, dict) else None, formats=fmts,
                                        engine_versions=engines, url='https://www.fab.com/listings/' + e['uid'], description=desc, text=(l.get('title') or '') + ' ' + desc + ' ' + ' '.join(t.get('name', '') for t in l.get('tags', [])),
                                        price='%s %s' % (price.get('price'), price.get('currencyCode')) if price else None,
                                        license=', '.join(sorted({lc.get('group', '') for lc in l.get('licenses', [])})) or None)
    # owner-listed titles nobody could resolve are still owned: keep them with what the owner gave
    have = {norm(p['title']) for p in packs.values()}
    for o in owner:
        if norm(o['title']) not in have:
            packs['owner:' + norm(o['title'])[:24]] = dict(id='owner:' + norm(o['title'])[:24], listing_uid=None, title=o['title'], publisher=o['publisher'], source='owner-list-only',
                                                          kind='animation_pack', fab_category=None, formats=[], engine_versions=[], url=None, description='', text=o['title'], price=None, license=None,
                                                          notes='Owned per the Fab library page; Fab search could not resolve this listing, so only the title is known.')

    if args.db.exists():
        args.db.unlink()
    db = sqlite3.connect(args.db)
    db.executescript(SCHEMA)
    clip_total = 0
    for p in packs.values():
        o = owner_by.get(norm(p['title']))
        if o and not p.get('publisher'):
            p['publisher'] = o['publisher']
        primary, types = classify(p['text'], p.get('fab_category'), p['title'])
        if p['kind'] == 'tool':
            primary, types = 'tools', ['tools']
        elif re.search(r'logo reveal|background and logo', p['title'], re.I):
            primary, types = 'not_character_animation', ['not_character_animation']
        rig = rigs(p['text'])
        if p['formats'] == ['fbx'] or (p['formats'] and set(p['formats']) <= {'unity'}):
            pass
        sid = None
        server_path = None
        for key in filter(None, [p['id'][:8] if not p['id'].startswith(('uid:', 'owner:')) else None, (p.get('listing_uid') or '')[:8]]):
            if key in disk:
                server_path = disk[key]
                break
        server_bytes = dir_size(server_path) if server_path else None
        evidence = None
        clips = []
        if server_path:
            files = [f for f in server_path.rglob('*') if f.suffix.lower() in ('.fbx', '.glb', '.gltf', '.bvh') and 'metadata' not in f.name]
            # Unreal packs: animation sequences are .uasset files named A_/AS_/AM_/Anim..., or sitting in an Animations folder
            files += [f for f in server_path.rglob('*.uasset') if re.match(r'(A_|AS_|AM_|AN_|Anim)', f.name, re.I) or re.search(r'/anim\w*(/|$)', str(f.parent), re.I) and not re.match(r'(SK_|SKM_|M_|MI_|T_|BP_|ABP_|BS_|PA_|SM_)', f.name)]
            anim_files = [f for f in files if re.search(r'animations?|/anim|motion', str(f.parent), re.I) or len(files) >= 1]
            # character meshes bundled with animations (joined/rig files) are not clips
            anim_files = [f for f in anim_files if not re.search(r'joined|rig-fbx|_mesh|model', f.name, re.I)] or anim_files
            fbx_files = [f for f in anim_files if f.suffix.lower() in ('.fbx', '.glb', '.gltf')]
            if fbx_files:
                evidence = skeleton_evidence(fbx_files[0])
            for f in sorted(anim_files):
                nm = f.stem.replace('_', ' ').replace('AS ', '')
                ctype, _ = classify(nm, None, nm)
                if ctype == GENERIC:
                    ctype = primary
                clips.append((nm, ctype, str(f), f.suffix.lower().lstrip('.'), f.stat().st_size))
        if evidence:
            for key, tag in (('mixamo', 'mixamo'), ('ue5_mannequin', 'ue5_mannequin'), ('pelvis_spine', 'creature')):
                if evidence.startswith(key) and tag not in rig:
                    rig = [r for r in rig if r != 'unspecified'] + [tag]
        if p['formats'] and set(p['formats']) <= {'unity'}:
            notes = TARGET_NOTES['unity_humanoid']
        elif evidence and evidence.startswith('ue5_mannequin'):
            notes = 'Verified from the files: ' + TARGET_NOTES['ue5_mannequin']
        elif evidence and evidence.startswith('mixamo'):
            notes = 'Verified from the files: ' + TARGET_NOTES['mixamo']
        elif evidence and evidence.startswith('pelvis_spine'):
            notes = TARGET_NOTES['creature']
        elif primary == 'creature_zombie':
            notes = 'Creature/zombie rig: use on the mesh shipped with the pack or one skinned to the same skeleton.'
        elif p['kind'] == 'tool':
            notes = 'Tool/plugin, not an animation set: see its listing for use.'
        else:
            notes = 'Listing claims: ' + ', '.join(rig) + '. Not yet verified against the files (download, then run retarget_animation.gd --inspect). ' + TARGET_NOTES[rig[0]]
        if 'unreal' in p['formats'] and not (set(p['formats']) - {'unreal'}):
            notes += ' Unreal-format only: apply in Unreal (IK Retargeter) or export to FBX first.'
        is_free = 1 if re.search(r'\bfree\b', p['title'], re.I) or (p.get('price') or '').startswith('0 ') else (None if not p.get('price') else 0)
        db.execute('INSERT INTO packs VALUES (%s)' % ','.join('?' * 27), (
            p['id'], p.get('listing_uid'), p['title'], p.get('publisher'), p['source'], p['kind'], p.get('fab_category'), primary, json.dumps(rig), json.dumps(p['formats']),
            json.dumps(p['engine_versions']), clip_count(p['text']), is_free, p.get('price'), p.get('license'), p.get('url'), p['description'][:1500],
            1 if o else 0, (o or {}).get('disk') or None, str(server_path) if server_path else None, server_bytes, evidence, notes, p.get('notes'),
            (rt.get(server_path.name) or {}).get('library') if server_path else None, (rt.get(server_path.name) or {}).get('clips') if server_path and server_path.name in rt else None, (rt.get(server_path.name) or {}).get('skipped_files') if server_path and server_path.name in rt else None))
        for t in types:
            db.execute('INSERT OR IGNORE INTO pack_types VALUES (?,?)', (p['id'], t))
        for c in clips:
            db.execute('INSERT INTO clips(pack_id,name,type,path,format,bytes) VALUES (?,?,?,?,?,?)', (p['id'],) + c)
            clip_total += 1
    # Sims packages sitting in the animations folder: inventory only
    for f in sorted(glob.glob('/data/ai/assets/animations/*.package')):
        n = os.path.basename(f)
        db.execute('INSERT INTO packs VALUES (%s)' % ','.join('?' * 27), (
            'sims:' + n, None, n, None, 'local-sims-package', 'other_format', None, 'unusable_format', json.dumps(['sims4']), json.dumps(['package']), '[]', None, None, None, None, None, '', 0, None, f,
            os.path.getsize(f), None, 'Sims 4 package: not usable by the Godot/Unreal pipeline.', None, None, None, None))
        db.execute('INSERT OR IGNORE INTO pack_types VALUES (?,?)', ('sims:' + n, 'unusable_format'))
    for rid, applies, target, status, steps, cav in RECIPES:
        db.execute('INSERT INTO recipes VALUES (?,?,?,?,?,?)', (rid, applies, target, status, steps, cav))
    for t, (d, _) in list(TYPES.items()) + [(GENERIC, ('Mixed or unspecified animation sets', '')), ('tools', ('Animation tools and plugins, not clip sets', '')), ('not_character_animation', ('Motion graphics or non-character animation', '')), ('unusable_format', ('Formats the pipeline cannot read (Sims 4 packages)', ''))]:
        db.execute('INSERT INTO types VALUES (?,?,?,?)', (t, d, db.execute('select count(*) from pack_types where type=?', (t,)).fetchone()[0], db.execute('select count(*) from clips where type=?', (t,)).fetchone()[0]))
    n_packs = db.execute('select count(*) from packs').fetchone()[0]
    for k, v in {'built_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'packs': str(n_packs), 'clips': str(clip_total), 'owner_list_titles': str(len(owner)),
                 'note': 'Owned animation titles per the owner-provided Fab library page; types are keyword-based and should be reviewed; clips are listed only for packs downloaded to the server.'}.items():
        db.execute('INSERT INTO meta VALUES (?,?)', (k, v))
    db.commit()
    export(db, args.db.with_suffix('.json'))
    if getattr(args, 'doc', True):
        write_doc(db, DOC_PATH)
    return db


def export(db, path):
    db.row_factory = sqlite3.Row
    out = {'meta': dict(db.execute('select key,value from meta').fetchall()),
           'types': [dict(r) for r in db.execute('select * from types order by pack_count desc')],
           'packs': [dict(r) for r in db.execute('select * from packs order by primary_type,title')],
           'pack_types': [dict(r) for r in db.execute('select * from pack_types')],
           'clips': [dict(r) for r in db.execute('select * from clips order by type,name')],
           'recipes': [dict(r) for r in db.execute('select * from recipes')]}
    pathlib.Path(path).write_text(json.dumps(out, indent=1))


TYPE_ORDER = ['fighting', 'weapons_firearms', 'weapons_melee', 'locomotion', 'traversal', 'reactions', 'emotes_social', 'poses_hands', 'daily_life', 'sport_fitness',
              'magic_fantasy', 'creature_zombie', 'general_variety', 'tools', 'not_character_animation', 'unusable_format']


def write_doc(db, path):
    """docs/guide/animation-library.md: generated from the database so the page cannot drift from it."""
    db.row_factory = sqlite3.Row
    meta = dict(db.execute('select key,value from meta').fetchall())
    packs = [dict(r) for r in db.execute('select * from packs')]
    owner_total = sum(1 for p in packs if p['in_owner_list'])
    fab_visible = sum(1 for p in packs if p['in_owner_list'] and p['source'] == 'fab-ue-library')
    on_server = [p for p in packs if p['server_path'] and p['kind'] != 'other_format']
    L = ['---', 'title: Owned animation library', 'nav: Animation library',
         'summary: Every animation pack owned on Fab, grouped by type (fighting, weapons, locomotion and so on), with rig and format facts and how to apply a pack to a MetaHuman.', '---', '',
         '## What this is', '',
         'A SQLite catalogue of the animation packs owned on the Fab account, grouped by what the animations are for, plus a tested path for applying a pack to a MetaHuman in Godot. '
         'The database is `/data/ai/assets/catalog/animations.db` (a JSON copy sits beside it). Query it with any SQLite client, for example '
         '`select type, title, rig_claims, formats from v_packs_by_type` or `select * from v_clips_by_type where type = \'fighting\'`. '
         'Tables: `packs`, `pack_types`, `clips`, `types`, `recipes`; views `v_packs_by_type` and `v_clips_by_type`.', '',
         'Built by `tools/fab/animation_catalog.py` (`refresh` re-reads the account; `build` rebuilds from saved inputs). The catalogue lists what is owned; it does not download anything. '
         'Any download still needs the owner\'s per-asset approval through the owned-assets skill.', '',
         '## Where the list comes from', '',
         'Fab\'s API only lists items that have an Unreal-format download, so animation packs that ship only as FBX, glTF or Unity files are invisible to it (the same gap that hid the MetaHuman packs). '
         'The My Library > Animations page is the complete list (%d packs); the API shows %d of them. The rest are resolved one by one through Fab\'s per-listing endpoints using the titles from that page. '
         'The owner-provided page copy is kept at `/data/ai/assets/catalog/sources/` and must be refreshed when new packs are added. %s' % (owner_total, fab_visible,
         'One owned title could not be resolved by search and is recorded with its title only.' if any(p['source'] == 'owner-list-only' for p in packs) else ''), '',
         '## Reading the types and rigs', '',
         'Types are assigned by keywords in the title and description (a title match counts triple) plus Fab\'s own category, and a pack can belong to several types; the sections below list each pack once, under its primary type; "any match" in the table counts every type a pack touches. '
         'Treat the grouping as a first pass to review, not a verdict. `rig_claims` is what the listing says about its skeleton. `skeleton_evidence` is what the files prove, and is only available for packs downloaded to the server; '
         'prefer it. Two packs that claim a UE mannequin rig can still be Mixamo-style in the files, so check before relying on a claim.', '',
         '## Packs by type', '', '| Type | Primary | Any match | What it covers |', '|---|---|---|---|']
    types = {r['type']: dict(r) for r in db.execute('select * from types')}
    for t in TYPE_ORDER:
        if t in types and types[t]['pack_count']:
            L.append('| %s | %d | %d | %s |' % (t, sum(1 for p in packs if p['primary_type'] == t), types[t]['pack_count'], types[t]['description']))
    L.append('')
    for t in TYPE_ORDER:
        rows = [p for p in packs if p['primary_type'] == t]
        if not rows:
            continue
        L += ['### %s' % t.replace('_', ' ').capitalize(), '']
        for p in sorted(rows, key=lambda r: r['title'].lower()):
            fm = ', '.join(json.loads(p['formats'])) or 'unknown'
            extra = []
            if p['clip_count_claim']:
                extra.append('~%d clips' % p['clip_count_claim'])
            if p['server_path']:
                extra.append('on server')
            if p['is_free']:
                extra.append('free')
            others = [r['type'] for r in db.execute('select type from pack_types where pack_id=? and type!=?', (p['id'], t))]
            if others and p['kind'] != 'other_format':
                extra.append('also: ' + ', '.join(o.replace('_', ' ') for o in others))
            L.append('- **%s**%s, %s%s' % (p['title'].replace('|', '/'), ' (%s)' % p['publisher'] if p['publisher'] else '', fm, '; ' + '; '.join(extra) if extra else ''))
        L.append('')
    L += ['## On the server', '']
    if on_server:
        L.append('Downloaded packs, with their clips listed in the `clips` table: ' + '; '.join('%s (%s)' % (p['title'], (p['skeleton_evidence'] or 'skeleton not checked').split(' (')[0]) for p in sorted(on_server, key=lambda r: r['title'])) + '.')
    L.append('')
    L += ['The Fab library page also marks two Kingboars packs as on disk (Paragon animations retargeted to Manny, 9.91 GB; Pistol and Rifle Locomotion Animations 1700, 2.35 GB). '
          'Those copies are on the owner\'s own machine, not on the server, so they are not in `clips`.', '',
          '## Applying a pack to a MetaHuman', '',
          'The converted MetaHuman body uses Unreal mannequin bone names, so most packs reduce to a bone-name mapping. `retarget_animation.gd` (installed with the `watoom-metahuman` skill) converts every clip in an FBX/glTF onto the body skeleton and saves an animation library.', '']
    for r in db.execute('select * from recipes'):
        L += ['### %s' % r['id'], '', '- **Applies to:** %s' % r['applies_to'], '- **Target:** %s (status: %s)' % (r['target'], r['status']), '- **Steps:** %s' % r['steps'], '- **Caveats:** %s' % r['caveats'], '']
    L += ['### Command', '',
          '```bash',
          'godot --headless --path <project> --import   # import the FBX first',
          'godot --headless --path <project> -s res://metahuman/MHC_Base_Female/retarget_animation.gd -- \\',
          '    --source res://anims/pack/jab_right.fbx --character res://metahuman/MHC_Base_Female/MHC_Base_Female.tscn',
          '# add --inspect (no --character) to print a source\'s bones and clips; --map identity|mixamo to override detection; --keep-root to keep hip travel',
          '```', '',
          'The result is written to `<character folder>/animations/<file>.res`. The character script adds every library in that folder to its `IdleAnimation` player automatically: a one-clip library becomes an animation named after the file (`jab_right`), '
          'a multi-clip library keeps its clips under `<file>/<clip>`. Play one with `player.play("jab_right")`.', '',
          '### What was verified', '',
          'Retargeted onto the Base_Female MetaHuman and rendered on Bazzite: three Motifect combat clips (jab, mid block, hook-uppercut combo) and one Sport/Gym clip (kettlebell windmill) with the delta solver; '
          'and from the Mocap.in packs a slow gun-carry walk, a punch guard, a dodge, a crouch, plus the single-file "Cutting the throat" and "hit by a bullet" clips. Stances, guard hands, an extended jab, a raised arm and a full-body fall all read correctly with the character facing the camera. '
          'Not verified: foot contact (sliding), long root-motion clips, finger detail, limb roll (elbow/knee bend direction) on the pose solver, and Unreal-format packs.', '',
          '### Two solvers', '',
          'Most Mixamo-style mocap files bake their first frame in as the skeleton\'s "rest" pose, so there is no neutral T-pose to measure motion against. The retargeter checks the source\'s rest pose and chooses: the **delta** solver (rotation change from a neutral rest, best fidelity) or the **pose** solver '
          '(rebuilds each bone from the source joint positions: limbs aim where the source limbs aim, torso twist follows the hip and shoulder lines, hips travel scales by leg length). Force one with `--solver delta|pose`; the log prints `SOLVER` for each run.', '',
          '### Unreal-format packs', '',
          'The ten Unreal-format packs (RamsterZ, AK-47, FPS AKS74U, First Person Rifle, Free Animation Pack, M4A1, Weapon Pack 03, Sword + Animation, Knife FPS, Mega Spear) were exported to FBX with the unreal-export pipeline (`export_pack.py --classes AnimSequence --request-extra \'{"anim_format":"fbx"}\'`, run headless on Bazzite; 587 sequences, none failed) and then retargeted like any other FBX. The originals under `/data/ai/assets/fab` are untouched; the FBX copies are in `/data/ai/artifacts/unreal-export/anims-fbx/`.', '']
    L += ['### Retargeted libraries', '',
          'Every FBX pack on the server has been retargeted onto the Base_Female MetaHuman, one animation library per pack (`animation-packs/<pack>.res`; copy one into the character\'s `animations/` folder to load it, and its clips then play as `<pack>/<clip>`). '
          'Weapon and equipment rigs (spear IK, barbell, dumbbell, revolver, AK fire/reload) animate the prop\'s own skeleton and are skipped on purpose. First-person packs (arms-only rigs) and per-bone helper clips retarget but only move part of the body, so review them before use.', '',
          '| Pack | Clips retargeted | Files skipped |', '|---|---|---|']
    for p in sorted([p for p in packs if p.get('retarget_clips')], key=lambda r: r['title'].lower()):
        L.append('| %s | %d | %d |' % (p['title'].replace('|', '/'), p['retarget_clips'], p['retarget_skipped'] or 0))
    L.append('')
    L += [
          '## Limits', '',
          '- Rotation retargeting only; no facial animation (Godot does not run RigLogic), no retargeting of props or weapons.',
          '- Hip travel is dropped unless `--keep-root` is given, so locomotion clips play in place by default.',
          '- Creature and zombie packs use their own skeletons and do not apply to a human MetaHuman.',
          '- Sims 4 `.package` files in `/data/ai/assets/animations` are listed for completeness only; this pipeline cannot read them.', '']
    pathlib.Path(path).write_text('\n'.join(L))


def refresh(args):
    tmp = pathlib.Path(tempfile.mkdtemp(prefix='fab-anim-'))
    raw = tmp / 'raw.json'
    subprocess.run(['bun', 'run', str(HERE / 'fab-library-dump.ts'), str(raw)], check=True)
    d = json.load(open(raw))
    have = {norm(x['title']) for x in d}
    missing = [r['title'] for r in parse_owner_list(args.owner_list) if norm(r['title']) not in have]
    (tmp / 'missing.json').write_text(json.dumps(missing))
    subprocess.run(['bun', 'run', str(HERE / 'fab-listing-detail.ts'), str(tmp / 'missing.json'), str(tmp / 'listings.json')], check=True)
    args.raw, args.listings = raw, tmp / 'listings.json'
    return build(args)


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest='cmd', required=True)
    for name in ('build', 'refresh'):
        p = sp.add_parser(name)
        p.add_argument('--owner-list', type=pathlib.Path, default=OWNER_LIST)
        p.add_argument('--db', type=pathlib.Path, default=DEFAULT_DB)
        if name == 'build':
            p.add_argument('--raw', required=True)
            p.add_argument('--listings')
    a = ap.parse_args()
    db = build(a) if a.cmd == 'build' else refresh(a)
    for r in db.execute('select primary_type,count(*) from packs group by 1 order by 2 desc'):
        print(r[0], r[1])
    print('packs', db.execute('select count(*) from packs').fetchone()[0], 'clips', db.execute('select count(*) from clips').fetchone()[0])


if __name__ == '__main__':
    main()
