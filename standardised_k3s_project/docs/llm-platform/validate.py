"""Offline documentation reference and example checks. No network or infrastructure mutations."""
import hashlib,json,pathlib,re,sys
ROOT=pathlib.Path(__file__).parent

def resolve(document,ref):
    if not ref.startswith("#/"):raise ValueError("Unexpected external schema reference")
    value=document
    for key in ref[2:].split("/"):value=value[key.replace("~1","/").replace("~0","~")]
    return value

def check_document(path):
    doc=json.loads(path.read_text());assert doc['openapi']=='3.1.0'
    ids=[];refs=[]
    def walk(value):
        if isinstance(value,dict):
            if '$ref' in value:refs.append(value['$ref']);resolve(doc,value['$ref'])
            for child in value.values():walk(child)
        elif isinstance(value,list):
            for child in value:walk(child)
    walk(doc)
    for path_,methods in doc['paths'].items():
        assert path_.startswith('/')
        for method,op in methods.items():
            if method not in ('get','post','put','patch','delete','head','options'):continue
            ids.append(op['operationId']);assert op['responses']
    assert len(ids)==len(set(ids)), 'Duplicate operation IDs'
    return doc,{'paths':len(doc['paths']),'operations':len(ids),'local_references':len(refs)}

def validate_example(value,schema,doc):
    if '$ref' in schema:return validate_example(value,resolve(doc,schema['$ref']),doc)
    if 'anyOf' in schema:
        for option in schema['anyOf']:
            try:validate_example(value,option,doc);return
            except (AssertionError,KeyError,TypeError):pass
        raise AssertionError('Example matches no schema alternative')
    kind=schema.get('type')
    if kind=='null':assert value is None
    if kind=='string':
        assert isinstance(value,str)
        if 'pattern' in schema:assert re.search(schema['pattern'],value)
    if kind=='boolean':assert type(value) is bool
    if kind=='object':
        assert isinstance(value,dict);assert set(schema.get('required',[]))<=set(value)
        props=schema.get('properties',{})
        if schema.get('additionalProperties') is False:assert set(value)<=set(props)
        for key,item in value.items():
            if key in props:validate_example(item,props[key],doc)
    if kind=='array':
        assert isinstance(value,list)
        for item in value:validate_example(item,schema['items'],doc)
    if 'enum' in schema:assert value in schema['enum']

def main():
    metadata=json.loads((ROOT/'verification.json').read_text())
    native,stats=check_document(ROOT/'api/watoom-code.openapi.json')
    assert hashlib.sha256((ROOT/'api/watoom-code.openapi.json').read_bytes()).hexdigest()==metadata['native_openapi_sha256']
    assert stats['paths']==metadata['native_openapi_paths']
    router,rstats=check_document(ROOT/'api/router.openapi.json')
    sys.path.insert(0,str(ROOT/'examples'));from watoom_client import NativeClient
    client=NativeClient('https://example.invalid','fixture-only')
    client.request=lambda method,path,body=None:body
    examples=[('/api/session',client.create_session('/example/project','Review fixture')),
              ('/api/session/{sessionID}/prompt',client.prompt('ses_fixture','Fixture input','msg_fixture'))]
    for endpoint,body in examples:
        schema=native['paths'][endpoint]['post']['requestBody']['content']['application/json']['schema']
        validate_example(body,schema,native)
    print(json.dumps({'result':'PASS','native':stats,'router':rstats,'example_request_shapes':len(examples),
        'scope':'JSON structure/local refs, immutable hash, unique operation IDs and reference-client request shapes; not a full OpenAPI semantic validator'}))
if __name__=='__main__':main()
