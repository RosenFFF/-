"""Owned 5433/6380/8003 only; never signals the shared services or 8002."""
import asyncio,json,os,secrets,signal,socket,subprocess,time
from pathlib import Path
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import create_async_engine
import asyncpg,httpx
from recovery_support import BudgetTransport
from tests.conftest import PASSWORDS

ROOT=Path(__file__).resolve().parent
D=ROOT/'drill-harness'; PG=ROOT/'private-pg'; SOCK=ROOT/'private-pg-socket'
BIN=Path('/workspace/competition/m3-demo-env/postgres/bin')
REDIS='/workspace/competition/m3-demo-env/src/redis-stable/src/redis-server'
PY='/workspace/competition/live-deepseek-71311f4-src/backend/.venv/bin/python'
results={'target':'dedicated c75f877 API8003, PG5433, Redis6380; 8002 untouched during faults','shared_service_restarts':0,'faults':[]}
children={};stage='initial'

def save(): (ROOT/'timings.json').write_text(json.dumps(results,indent=2)+'\n')
async def ctl(*args):
 r=await asyncio.to_thread(subprocess.run,list(map(str,args)),capture_output=True)
 if r.returncode:raise RuntimeError('dedicated service command failed; private output withheld')
def spawn(name,args,env=None):
 log=(ROOT/(name+'.redacted.log')).open('a')
 process=subprocess.Popen(args,stdout=log,stderr=subprocess.STDOUT,env=env)
 children[name]=process;return process
async def port(port,timeout=30):
 start=time.monotonic()
 while time.monotonic()-start<timeout:
  try:
   reader,writer=await asyncio.open_connection('127.0.0.1',port);writer.close();await writer.wait_closed();return
  except OSError:await asyncio.sleep(.1)
 raise RuntimeError('owned loopback listener did not start')
def redis_start():
 return spawn('redis-private',[REDIS,'--bind','127.0.0.1','--port','6380','--protected-mode','yes','--dir',str(ROOT/'private-redis'),'--save','60','1','--appendonly','no'])
def proxy_start():return spawn('proxy',[PY,str(ROOT/'connect_proxy.py')])
async def stop_child(name):
 p=children[name]
 if p.poll() is None:p.terminate();await asyncio.to_thread(p.wait,10)

def safe_response(r):
 out={'http_status':r.status_code}
 if r.status_code>=400:
  try:out['error_body']={k:v for k,v in r.json().items() if k in ('type','title','status','code','detail','errors')}
  except ValueError:out['error_body']={'code':'NON_JSON_WITHHELD'}
 return out

async def main():
 global stage
 key=next(l.split('=',1)[1].strip().strip('"\'') for l in Path('/workspace/competition/secrets/deepseek.env').read_text().splitlines() if l.startswith('DEEPSEEK_API_KEY='))
 try:
  for n in (5433,6380,8003,8899):
   with socket.socket() as s:
    if s.connect_ex(('127.0.0.1',n))==0:raise RuntimeError('drill port already occupied; refusing interference')
  stage='dedicated initdb'
  PG.mkdir(mode=0o700);SOCK.mkdir(mode=0o700);(ROOT/'private-redis').mkdir(mode=0o700)
  await ctl(BIN/'initdb','-D',PG,'--no-locale','--encoding=UTF8','--auth-local=trust','--auth-host=scram-sha-256')
  pg_options=f'-h 127.0.0.1 -p 5433 -k {SOCK} -c log_min_error_statement=panic'
  await ctl(BIN/'pg_ctl','-D',PG,'-l',ROOT/'postgres-private.redacted.log','-o',pg_options,'start','-w')
  stage='dedicated roles'
  owner_pw,runtime_pw=secrets.token_hex(24),secrets.token_hex(24)
  conn=await asyncpg.connect(host=str(SOCK),port=5433,user='box',database='postgres')
  await conn.execute(f"CREATE ROLE m3_migration LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD '{owner_pw}'")
  await conn.execute(f"CREATE ROLE m3_runtime LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD '{runtime_pw}'")
  await conn.execute('CREATE DATABASE st143_m2_test_recovery OWNER m3_migration');await conn.close()
  def url(user,password):return URL.create('postgresql+asyncpg',username=user,password=password,host='127.0.0.1',port=5433,database='st143_m2_test_recovery').render_as_string(hide_password=False)
  config={'TEST_POSTGRES_DISPOSABLE':'1','TEST_POSTGRES_URL':url('m3_migration',owner_pw),'TEST_POSTGRES_APP_URL':url('m3_runtime',runtime_pw)}
  stage='canonical cloud model discovery'
  async with httpx.AsyncClient(transport=BudgetTransport(ROOT/'model-call-counts.json','model-discovery'),timeout=10,trust_env=False) as c:
   response=await c.get('https://api.deepseek.com/v1/models',headers={'Authorization':'Bearer '+key});response.raise_for_status()
   model=response.json()['data'][0]['id']
  results['drill_cloud_model']=model;results['model_selection']='actual listed canonical ID; health GET needs no paid alias inference; 8002 keeps original configured alias'
  stage='dedicated servers'
  redis_start();proxy_start();await port(6380);await port(8899)
  env=os.environ.copy();env['DRILL_PRIVATE_JSON']=json.dumps(config);env['DRILL_MODEL']=model
  spawn('api-launcher',[PY,str(D/'launch_redacted.py')],env)
  await port(8003,60)
  pid=int((D/'runtime/server.pid').read_text());start_identity=Path(f'/proc/{pid}/stat').read_text().split()[21]
  results['api_pid']=pid
  ids=json.loads((D/'seed-ids.json').read_text());proof=json.loads((D/'environment-proof.json').read_text());schema=proof['schema']
  engine=create_async_engine(config['TEST_POSTGRES_APP_URL'],pool_pre_ping=True,connect_args={'server_settings':{'search_path':schema}})
  async def rls():
   try:
    async with engine.begin() as c:
     attrs=(await c.execute(text('SELECT rolsuper,rolbypassrls,rolcreaterole,rolcreatedb FROM pg_roles WHERE rolname=current_user'))).one()
     tables=(await c.execute(text("SELECT c.relname,c.relrowsecurity,c.relforcerowsecurity,pg_has_role(current_user,c.relowner,'MEMBER') FROM pg_class c WHERE c.relnamespace=current_schema()::regnamespace AND c.relname IN ('documents','users','tenants','reviews')"))).all()
     unscoped=await c.scalar(text('SELECT count(*) FROM documents'))
    scoped={}
    for label in ('a','b'):
     async with engine.begin() as c:
      await c.execute(text("SELECT set_config('app.current_org_id',:t,true),set_config('app.current_user_id',:u,true),set_config('app.current_role','admin',true)"),{'t':ids[label]['tenant'],'u':ids[label]['user']})
      docs=list((await c.execute(text('SELECT id FROM documents'))).scalars())
      scoped[label]={'visible_count':len(docs),'own_visible':ids[label]['document'] in docs,'other_visible':ids['b' if label=='a' else 'a']['document'] in docs}
    result={'database_available':True,'runtime_role':'m3_runtime','unsafe_role_attributes':any(attrs),'force_rls_all_four':len(tables)==4 and all(r[1] and r[2] and not r[3] for r in tables),'unscoped_visible_count':unscoped,'tenant_checks':scoped}
    result['passed']=not any(attrs) and result['force_rls_all_four'] and unscoped==0 and all(v['own_visible'] and not v['other_visible'] and v['visible_count']==1 for v in scoped.values())
    return result
   except Exception as exc:return {'database_available':False,'exception_class':type(exc).__name__,'passed':None}
  async with httpx.AsyncClient(base_url='http://127.0.0.1:8003',headers={'Origin':'https://localhost:5173'},timeout=12,trust_env=False) as client:
   cookies={};csrf={}
   async def login(label,store=False):
    r=await client.post('/api/v1/auth/login',json={'username':'drill-'+label,'password':PASSWORDS['reviewer']},headers={'Cookie':''})
    if store and r.status_code==200:
     cookies[label]='; '.join(f'{c.name}={c.value}' for c in r.cookies.jar)
     csrf[label]=next(c.value for c in r.cookies.jar if c.name=='csrf_token')
    return safe_response(r)
   for label in ('a','b'):
    value=await login(label,True)
    if value['http_status']!=200:raise RuntimeError('dedicated seed login failed')
   async def snapshot(name):
    snap={'name':name,'same_pid':Path(f'/proc/{pid}/stat').exists() and Path(f'/proc/{pid}/stat').read_text().split()[21]==start_identity}
    ready=await client.get('/api/v1/readyz',headers={'Cookie':''})
    snap['readyz']={**safe_response(ready),'body':ready.json()}
    snap['logins']={label:await login(label) for label in ('a','b')}
    models=await client.get('/api/v1/system/models',headers={'Cookie':cookies['a']})
    snap['models']=safe_response(models)
    if models.status_code==200:
     body=models.json();snap['models'].update(degrade_level=body['degrade_level'],llm=[{k:m[k] for k in ('provider','model','healthy','circuit_open')} for m in body['models'] if m['category']=='llm'])
    snap['reads']={}
    for label in ('a','b'):
     head={'Cookie':cookies[label]}
     own=await client.get('/api/v1/documents/'+ids[label]['document'],headers=head)
     cross=await client.get('/api/v1/documents/'+ids['b' if label=='a' else 'a']['document'],headers=head)
     snap['reads'][label]={'own':safe_response(own),'cross':safe_response(cross)}
    head={'Cookie':cookies['a'],'X-CSRF-Token':csrf['a']}
    upload=await client.post('/api/v1/documents/upload',files={'file':('invalid.txt',b'fixture','text/plain')},headers=head)
    review=await client.post('/api/v1/reviews',json={'document_ids':[],'destination_country':'VN'},headers=head)
    snap['invalid_upload_no_inference']=safe_response(upload);snap['invalid_review_no_inference']=safe_response(review)
    snap['direct_rls']=await rls()
    return snap
   stage='baseline'
   results['baseline']=await snapshot('baseline');save()
   for fault in ['redis','postgres','deepseek_relay']:
    stage=fault
    if fault=='redis':await stop_child('redis-private')
    elif fault=='postgres':await ctl(BIN/'pg_ctl','-D',PG,'stop','-m','fast','-w')
    else:
     await stop_child('proxy');await asyncio.sleep(16)
    during=await snapshot(fault+'-during');entry={'fault':fault,'during':during};results['faults'].append(entry);save()
    removed=time.monotonic()
    if fault=='redis':redis_start();await port(6380)
    elif fault=='postgres':await ctl(BIN/'pg_ctl','-D',PG,'-l',ROOT/'postgres-private.redacted.log','-o',pg_options,'start','-w')
    else:proxy_start();await port(8899)
    recovered=False;polls=[]
    while time.monotonic()-removed<45:
     ready=await client.get('/api/v1/readyz',headers={'Cookie':''})
     polls.append({'elapsed_ms':round((time.monotonic()-removed)*1000),'http_status':ready.status_code,'degrade_level':ready.json().get('degrade_level')})
     if ready.status_code==200 and ready.json().get('degrade_level')=='L0':recovered=True;break
     await asyncio.sleep(1)
    entry['ready_recovery_seconds']=round(time.monotonic()-removed,3);entry['recovery_polls']=polls
    entry['after']=await snapshot(fault+'-after');entry['full_observation_seconds']=round(time.monotonic()-removed,3)
    entry['automatic_recovery_without_api_restart']=recovered and entry['after']['same_pid'];save()
   await engine.dispose()
  results['completed']=True;save();print('dedicated live drill completed; values withheld',flush=True)
 finally:
  # Cleanup only owned drill resources, AFTER all recovery observations. Never 8002.
  if (D/'runtime/server.pid').exists():
   pid=int((D/'runtime/server.pid').read_text())
   if Path(f'/proc/{pid}/cmdline').exists():
    cmd=Path(f'/proc/{pid}/cmdline').read_bytes()
    if b'uvicorn' in cmd and b'8003' in cmd:os.kill(pid,signal.SIGTERM)
  for name in ['proxy','redis-private']:
   if name in children:await stop_child(name)
  if (PG/'postmaster.pid').exists():await ctl(BIN/'pg_ctl','-D',PG,'stop','-m','fast','-w')
  results['owned_drill_services_cleaned_up']=True;save()

try:asyncio.run(main())
except Exception as exc:
 results.update(completed=False,failure_stage=stage,failure_class=type(exc).__name__);save()
 print('drill stopped safely:',stage,type(exc).__name__,flush=True)
 raise SystemExit(1)
