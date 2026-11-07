"""Loopback backend smoke only; never persist credentials, cookies or auth response."""
import asyncio,json,os,time,stat
from pathlib import Path
import httpx
from tests.conftest import PASSWORDS
root=Path(__file__).resolve().parent
async def main():
    started=time.perf_counter()
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8002',headers={'Origin':'https://localhost:5173'},timeout=30,trust_env=False) as client:
        ready=await client.get('/api/v1/readyz')
        root.joinpath('readyz.json').write_text(json.dumps({'http_status':ready.status_code,'response':ready.json()},indent=2)+'\n')
        login=await client.post('/api/v1/auth/login',json={'username':'reviewer','password':PASSWORDS['reviewer']})
        if login.status_code!=200:raise RuntimeError('login failed; response withheld')
        # Backend-internal HTTP hop, analogous to the TLS frontend proxy; server Secure
        # cookies remain configured. Cookie values stay in this client process only.
        cookie='; '.join(f'{c.name}={c.value}' for c in login.cookies.jar)
        models=await client.get('/api/v1/system/models',headers={'Cookie':cookie})
        body=models.json()
        root.joinpath('system-models.json').write_text(json.dumps({'http_status':models.status_code,'response':body},indent=2)+'\n')
        deepseek=next(m for m in body['models'] if m['category']=='llm' and m['provider']=='deepseek')
        smoke={'source_commit':'c75f877e09decd1b598c26f25e6b70e8742660d7','new_pid':int(root.joinpath('runtime/server.pid').read_text()),'bind_host':'127.0.0.1','port':8002,'readyz_status':ready.status_code,'login_status':login.status_code,'models_status':models.status_code,'degrade_level':body['degrade_level'],'deepseek_healthy':deepseek['healthy'],'origin':'https://localhost:5173','cookie_secure_config_preserved':all(c.secure for c in login.cookies.jar),'environment_proof_mode':oct(stat.S_IMODE(root.joinpath('environment-proof.json').stat().st_mode)),'probe_scope':'health probe only; readiness and models share the 15-second health cache','reviews':0,'chat_calls':0,'elapsed_ms':round((time.perf_counter()-started)*1000),'browser_e2e':False}
        root.joinpath('smoke.json').write_text(json.dumps(smoke,indent=2)+'\n')
        print(json.dumps(smoke))
        if ready.status_code!=200 or models.status_code!=200 or body['degrade_level']!='L0' or not deepseek['healthy']:raise RuntimeError('smoke acceptance failed')
asyncio.run(main())
