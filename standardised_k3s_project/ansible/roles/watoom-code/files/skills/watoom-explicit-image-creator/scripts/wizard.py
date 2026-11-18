"""CPU-only shared image prompt wizard. Returns plans; never contacts a renderer."""
import argparse, copy, hashlib, json, math, os, pathlib, re, tempfile, uuid
ROOT = pathlib.Path(__file__).resolve().parents[1]
FIELDS = json.loads((ROOT / 'assets/fields.json').read_text())
PROFILES = json.loads((ROOT / 'assets/model-profiles.json').read_text())
DEFAULTS = json.loads((ROOT / 'assets/preferences.json').read_text())
SCORE = re.compile(r'\bscore_[0-9]+(?:_up)?\b')


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def preferences(overrides=None):
    result = copy.deepcopy(DEFAULTS)
    for key, value in (overrides or {}).items():
        if key not in result: raise ValueError('Unknown preference: ' + key)
        result[key] = copy.deepcopy(value)
    if not isinstance(result['default_human_appearance'], str): raise ValueError('Appearance preference must be text')
    return result


def profile(model):
    evidence = (model or {}).get('prompt_profile', {})
    family = evidence.get('family', 'unknown')
    verified = bool(evidence.get('verified') is True and evidence.get('revision') == (model or {}).get('revision') and evidence.get('source'))
    if family not in PROFILES or not verified: family = 'unknown'
    return copy.deepcopy(PROFILES[family])


def clean_tags(tags):
    if not isinstance(tags, list) or any(not isinstance(t, str) for t in tags): raise ValueError('Tags must be a list of text values')
    return list(dict.fromkeys(t.strip() for t in tags if t.strip()))


def settings(values=None):
    result = dict(width=1024, height=1024, steps=30, guidance=7.0, scheduler='euler', seed=0)
    for key, value in (values or {}).items():
        if key not in result: raise ValueError('Setting not exposed by the current image tool: ' + key)
        result[key] = value
    for key, low, high in [('width',256,1024), ('height',256,1024), ('steps',1,50), ('seed',0,4294967295)]:
        v=result[key]
        if type(v) is not int or not low <= v <= high: raise ValueError('Invalid '+key)
    if result['width']%8 or result['height']%8: raise ValueError('Dimensions must be multiples of eight')
    if type(result['guidance']) not in (int,float) or not math.isfinite(result['guidance']) or not 0<=result['guidance']<=20: raise ValueError('Invalid guidance')
    if result['scheduler'] not in ['euler','dpm']: raise ValueError('Unsupported scheduler')
    return result


def new(idea, analysis=None, model=None, prefs=None, positive=None, negative=None):
    if not isinstance(idea,str) or not idea.strip(): raise ValueError('Describe the image you want to create.')
    analysis=analysis or {}; pref=preferences(prefs)
    details={group:{field:'' for field in fields} for group,fields in FIELDS.items()}
    for group,values in analysis.get('details',{}).items():
        if group not in details or set(values)-set(details[group]): raise ValueError('Unknown detail field')
        details[group].update(values)
    for group in ['camera','lighting']:
        for field,value in pref[group].items():
            if field not in details[group]:raise ValueError('Unknown preference detail field')
            if not details[group][field]:details[group][field]=value
    human=details['subject']
    if analysis.get('human'):
        if not human['age']: human['age']='adult'
        established=bool(analysis.get('appearance_specified') or analysis.get('character_identity') or analysis.get('reference') or human['appearance'] or human['facial_features'])
        if not established and pref['default_human_appearance']:
            human['appearance']=('Caucasian/European facial characteristics; varied individual features' if pref['default_human_appearance']=='caucasian_european' else pref['default_human_appearance'])
    state=dict(version=1,draft_id=uuid.uuid4().hex,revision=1,phase='POSITIVE_REVIEW',idea=idea,
               positive=positive or dict(description=analysis.get('description',idea.strip()),tags=analysis.get('tags',[])),negative=negative,
               negative_supplied=negative is not None,details=details,model=copy.deepcopy(model),settings=settings(pref.get('generation_settings')),
               settings_provenance='Verified image-worker limits/defaults; checkpoint recommendations unverified unless separately recorded',
               style_preset=analysis.get('style_preset',pref['style_preset']),explicit_settings=[],preferences=pref,history=[],receipts=[],positive_approved=False,negative_approved=False)
    state['positive']['tags']=clean_tags(state['positive'].get('tags',[])+(pref['positive_tags'] if positive is None else []))
    return state


def positive_prompt(state):
    parts=[state['positive']['description'].strip()]
    for group,values in state['details'].items():
        text='; '.join(key.replace('_',' ')+': '+str(value).strip() for key,value in values.items() if str(value).strip())
        if text: parts.append(group.replace('_',' ').title()+': '+text)
    quality=profile(state['model']).get('positive_quality',[]) if state['preferences']['pony_quality_tags'] else []
    tags=clean_tags(state['positive'].get('tags',[]))
    if quality: parts.append('Model-specific quality tags: '+', '.join(quality))
    if tags: parts.append('Descriptive tags: '+', '.join(tags))
    return '\n\n'.join(parts)


def suggest_negative(state):
    # Suggestions are reviewed; an existing user negative block is never rewritten.
    quality=profile(state['model']).get('negative_quality',[]) if state['preferences']['pony_quality_tags'] else []
    values=quality+list(state['preferences']['negative_tags'])
    return ', '.join(dict.fromkeys(values))


def preview(state):
    if state['phase'] not in ['FINAL_REVIEW','PLAN_READY','SAVED']: raise ValueError('Complete positive, negative and optional detail review first')
    value=dict(positive_prompt=positive_prompt(state),negative_prompt=state['negative'],model=state['model'],
               style_preset=state['style_preset'],settings=state['settings'],settings_provenance=state['settings_provenance'],
               aspect_ratio=f"{state['settings']['width']//math.gcd(state['settings']['width'],state['settings']['height'])}:{state['settings']['height']//math.gcd(state['settings']['width'],state['settings']['height'])}",
               lora_settings='Strength/base overrides are not exposed by the current MCP tool',
               reference_conditioning='Not exposed by current MCP; text continuity only, not exact image identity')
    value['preview_id']=fingerprint(value)
    return value


def transition(original,action,data=None):
    state=copy.deepcopy(original); data=data or {}; phase=state['phase']
    if phase in ['PLAN_READY','SAVED'] and action in ['edit_positive','edit_negative','edit_settings','select_model','apply_preset']:
        state['history'].append(preview(state));state['revision']+=1;state.pop('request_plan',None)
    if action=='edit_positive':
        if 'description' in data: state['positive']['description']=data['description']
        if 'tags' in data: state['positive']['tags']=clean_tags(data['tags'])
        state.update(phase='POSITIVE_REVIEW',positive_approved=False,negative_approved=False)
    elif action=='approve_positive':
        if phase!='POSITIVE_REVIEW': raise ValueError('Positive review is not active')
        if not state['positive']['description'].strip(): raise ValueError('Positive description cannot be empty')
        state.update(positive_approved=True,phase='NEGATIVE_REVIEW')
        if state['negative'] is None: state['negative']=suggest_negative(state)
    elif action=='edit_negative':
        if phase not in ['NEGATIVE_REVIEW','DETAILS','FINAL_REVIEW','PLAN_READY','SAVED']: raise ValueError('Review positive first')
        if not isinstance(data.get('text'),str): raise ValueError('Negative prompt must be text')
        state.update(negative=data['text'],negative_supplied=True,negative_approved=False,phase='NEGATIVE_REVIEW')
    elif action=='approve_negative':
        if phase!='NEGATIVE_REVIEW': raise ValueError('Negative review is not active')
        state.update(negative_approved=True,phase='DETAILS')
    elif action=='details':
        if phase not in ['DETAILS','FINAL_REVIEW']: raise ValueError('Review both initial prompts before additional details')
        for group,values in data.items():
            if group not in FIELDS or not isinstance(values,dict) or set(values)-set(FIELDS[group]): raise ValueError('Unknown detail field')
            if any(not isinstance(v,str) for v in values.values()): raise ValueError('Detail values must be text')
            state['details'][group].update(values)
        state['phase']='DETAILS'
    elif action=='continue':
        if phase!='DETAILS': raise ValueError('Additional details are not active')
        state['phase']='FINAL_REVIEW'
    elif action=='edit_settings':
        state['settings']=settings({**state['settings'],**data});state['explicit_settings']=sorted(set(state.get('explicit_settings',[]))|set(data));state['phase']='FINAL_REVIEW' if state['positive_approved'] and state['negative_approved'] else phase
    elif action=='select_model':
        state['model']=copy.deepcopy(data);state.update(phase='POSITIVE_REVIEW',positive_approved=False,negative_approved=False)
        if not state['negative_supplied']:state['negative']=None
    elif action=='apply_preset':
        preset=state['preferences']['presets'].get(data.get('name'))
        if not isinstance(preset,dict):raise ValueError('Unknown preset')
        allowed={'default_human_appearance','style_preset','positive_tags','negative_tags','camera','lighting','generation_settings'}
        if set(preset)-allowed:raise ValueError('Unsupported preset fields')
        state['preferences']=preferences({**state['preferences'],**preset})
        for group in ['camera','lighting']:
            for field,value in preset.get(group,{}).items():
                if field not in FIELDS[group]:raise ValueError('Unknown preset detail field')
                if not state['details'][group][field]:state['details'][group][field]=value
        if 'style_preset' in preset:state['style_preset']=preset['style_preset']
        state['positive']['tags']=clean_tags(state['positive']['tags']+preset.get('positive_tags',[]))
        state['settings']=settings({**state['settings'],**{k:v for k,v in preset.get('generation_settings',{}).items() if k not in state.get('explicit_settings',[])}})
        if not state['negative_supplied']:state['negative']=None
        state.update(phase='POSITIVE_REVIEW',positive_approved=False,negative_approved=False)
    elif action=='record_receipt':
        if phase!='PLAN_READY' or data.get('request_id')!=state.get('request_plan',{}).get('request_id') or not re.fullmatch('[a-f0-9]{64}',data.get('job_id','')):raise ValueError('Receipt identity mismatch')
        state['receipts'].append(copy.deepcopy(data))
    elif action=='save_prompts':
        preview(state);state['phase']='SAVED'
    elif action=='generate':
        shown=preview(state)
        if not state['positive_approved'] or not state['negative_approved'] or data.get('preview_id')!=shown['preview_id']:raise ValueError('Approve the exact current final preview by selecting Generate')
        model=state['model'] or {};current=data.get('current_model') or {}
        if not re.fullmatch('[a-f0-9]{64}',model.get('id','')) or not re.fullmatch('[a-f0-9]{40,64}',model.get('revision','')):raise ValueError('Select an installed, pinned image model')
        if current.get('id')!=model['id'] or current.get('revision')!=model['revision'] or current.get('registered') is not True or current.get('kind') not in ['diffusion-pipeline','diffusion-checkpoint','lora']:raise ValueError('Installed model is missing, incompatible or changed; refresh catalog')
        if (SCORE.search(shown['positive_prompt']) or SCORE.search(shown['negative_prompt'])) and not profile(model).get('pony_compatible'):raise ValueError('Pony score tags require verified revision-scoped compatibility; edit and reapprove')
        if max(len(shown['positive_prompt']),len(shown['negative_prompt']))>4096:raise ValueError('Prompt exceeds native 4096-character limit; edit and reapprove')
        state['request_plan']=dict(request_id='prompt-'+state['draft_id']+'-'+str(state['revision']),installation_id=model['id'],revision=model['revision'],prompt=shown['positive_prompt'],negative_prompt=shown['negative_prompt'],settings=state['settings'])
        state['phase']='PLAN_READY'
    elif action=='refine':
        if phase not in ['PLAN_READY','SAVED','FINAL_REVIEW']:raise ValueError('No reviewed image version to refine')
        state['history'].append(preview(state));state['revision']+=1;state.pop('request_plan',None)
        if 'description' in data:state['positive']['description']=data['description']
        if 'tags' in data:state['positive']['tags']=clean_tags(data['tags'])
        state.update(phase='POSITIVE_REVIEW',positive_approved=False,negative_approved=False)
    else: raise ValueError('Unknown wizard action')
    return state


def save_json(path,value):
    path=pathlib.Path(path)
    if path.is_symlink() or path.parent.resolve()!=path.parent: raise ValueError('Canonical storage path required')
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.image-draft-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as f:os.fchmod(f.fileno(),0o600);json.dump(value,f,indent=2,ensure_ascii=False);f.write('\n');f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def save_preset(path,name,values):
    if not re.fullmatch('[A-Za-z0-9_-]{1,64}',name):raise ValueError('Invalid preset name')
    path=pathlib.Path(path);value=json.loads(path.read_text()) if path.exists() else preferences()
    value=preferences(value);value['presets'][name]=copy.deepcopy(values);save_json(path,value)
    return value


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['new','show','apply','preview','preset']);p.add_argument('--state',type=pathlib.Path);p.add_argument('--input',type=pathlib.Path);p.add_argument('--preferences',type=pathlib.Path);p.add_argument('--name');a=p.parse_args()
    data=json.loads(a.input.read_text()) if a.input else {}
    if a.action=='preset':
        if not a.preferences:p.error('--preferences required')
        value=save_preset(a.preferences,a.name,data)
    else:
        if not a.state:p.error('--state required')
        if a.action=='new':
            if a.state.exists():raise ValueError('Draft already exists; select a new draft path')
            if a.preferences and a.preferences.exists():data['prefs']=json.loads(a.preferences.read_text())
            value=new(**data);save_json(a.state,value)
        else:
            value=json.loads(a.state.read_text())
            if a.action=='apply':value=transition(value,data['action'],data.get('data'));save_json(a.state,value)
            elif a.action=='preview':value=preview(value)
    print(json.dumps(value,indent=2,ensure_ascii=False))

if __name__=='__main__':main()
