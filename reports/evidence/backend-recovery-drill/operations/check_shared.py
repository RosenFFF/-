import asyncio,json,re
from collections import Counter
from pathlib import Path
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from redis.asyncio import Redis
root=Path(__file__).resolve().parent
async def main():
 config=json.loads(Path('/workspace/competition/m3-demo-env/runtime/test-environment.json').read_text())
 engine=create_async_engine(config['TEST_POSTGRES_URL'])
 async with engine.connect() as c:
  rows=(await c.execute(text('SELECT usename,datname,application_name,query FROM pg_stat_activity WHERE datname IS NOT NULL AND pid<>pg_backend_pid()'))).all()
  grouped=Counter((r[0],r[1],r[2] or '<unnamed>') for r in rows)
  schemas=Counter(s for r in rows for s in re.findall(r'st143_[a-z0-9_]+',r[3] or ''))
 await engine.dispose()
 redis=Redis.from_url('redis://127.0.0.1:6379/12',decode_responses=True)
 clients=await redis.client_list();await redis.aclose()
 proof={'pg_client_count':len(rows),'pg_groups':[{'usename':k[0],'datname':k[1],'application_name':k[2],'count':v} for k,v in grouped.items()],'query_schema_markers_only':dict(schemas),'redis_client_count':len(clients),'redis_groups':[{'db':k[0],'name':k[1] or '<unnamed>','count':v} for k,v in Counter((c.get('db'),c.get('name')) for c in clients).items()],'unattributed_clients_present':bool(rows) or any(not c.get('name') for c in clients),'decision':'DO NOT restart shared services; conservative attribution; dedicated 5433/6380/8003 only','shared_service_restarts':0}
 (root/'shared-client-check.json').write_text(json.dumps(proof,indent=2)+'\n')
 print(json.dumps({k:proof[k] for k in ['pg_client_count','redis_client_count','decision']}))
asyncio.run(main())
