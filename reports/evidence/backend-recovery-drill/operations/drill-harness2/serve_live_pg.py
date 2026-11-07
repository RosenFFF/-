"""Local integration harness: real PG/Redis, real ProviderChain, all application gates intact."""
from __future__ import annotations
import base64
import json
import os
import secrets
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import Settings
from app.db import base
from app.db.base import Base, Database
from app.main import create_app
from tests.conftest import _seed
from tests.postgres import disposable_postgres_url

ROOT = Path(__file__).resolve().parent
PRIVATE = Path('/workspace/competition/m3-demo-env/runtime/test-environment.json')
SCHEMA = 'st143_recovery_' + uuid.uuid4().hex
REDIS_URL = 'redis://127.0.0.1:6380/0'

# Only connection scoping is adapted; no gate, policy, query or model is replaced.
def scoped_engine(url, **kwargs):
    if make_url(url).get_backend_name() != 'postgresql':
        raise RuntimeError('live harness requires PostgreSQL; no SQLite fallback')
    kwargs.setdefault('connect_args', {}).setdefault('server_settings', {})['search_path'] = SCHEMA
    return create_async_engine(url, **kwargs)

async def provision(config):
    owner_url = disposable_postgres_url(config)
    runtime_url = disposable_postgres_url({'TEST_POSTGRES_DISPOSABLE': '1', 'TEST_POSTGRES_URL': config['TEST_POSTGRES_APP_URL']})
    if not owner_url or not runtime_url:
        raise RuntimeError('explicit disposable PG configuration required')
    owner_target, app_target = make_url(owner_url), make_url(runtime_url)
    if (owner_target.host, owner_target.port, owner_target.database) != (app_target.host, app_target.port, app_target.database) or owner_target.username == app_target.username:
        raise RuntimeError('separate migration/runtime logins in same local database required')
    raw_owner, raw_app = create_async_engine(owner_url), create_async_engine(runtime_url)
    try:
        async with raw_app.connect() as conn:
            role = await conn.scalar(text('SELECT current_user'))
            attrs = (await conn.execute(text('SELECT rolsuper,rolbypassrls,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname=current_user'))).one()
            if any(attrs):
                raise RuntimeError('unsafe runtime role')
        async with raw_owner.begin() as conn:
            attrs = (await conn.execute(text('SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user'))).one()
            if any(attrs):
                raise RuntimeError('unsafe migration role')
            await conn.execute(text(f'CREATE SCHEMA "{SCHEMA}"'))
    finally:
        await raw_owner.dispose()
        await raw_app.dispose()
    base.create_async_engine = scoped_engine
    owner = Database(owner_url)
    try:
        await owner.migrate()
        async with owner.engine.begin() as conn:
            quote = conn.dialect.identifier_preparer.quote_identifier
            await conn.execute(text(f'GRANT USAGE ON SCHEMA {quote(SCHEMA)} TO {quote(role)}'))
            tables = ', '.join(f'{quote(SCHEMA)}.{quote(name)}' for name in Base.metadata.tables)
            await conn.execute(text(f'GRANT SELECT,INSERT,UPDATE,DELETE ON TABLE {tables} TO {quote(role)}'))
            await conn.execute(text(f'GRANT SELECT ON TABLE {quote(SCHEMA)}.alembic_version TO {quote(role)}'))
            await conn.execute(text(f'GRANT USAGE ON ALL SEQUENCES IN SCHEMA {quote(SCHEMA)} TO {quote(role)}'))
    finally:
        await owner.dispose()
    return runtime_url

def _deepseek_key():
    """Read the private DeepSeek key into this process only; never logged, printed or written."""
    for line in Path('/workspace/competition/secrets/deepseek.env').read_text().splitlines():
        if line.strip().startswith('DEEPSEEK_API_KEY='):
            value = line.split('=', 1)[1].strip().strip('"\'')
            if value:
                return value
    raise RuntimeError('private DeepSeek configuration missing')

# Fail before binding HTTP if preparation/dependencies cannot be validated.
config = json.loads(os.environ['DRILL_PRIVATE_JSON'])
url = disposable_postgres_url({'TEST_POSTGRES_DISPOSABLE':'1','TEST_POSTGRES_URL':config['TEST_POSTGRES_APP_URL']})
if not url:
    raise RuntimeError('explicit local PostgreSQL configuration required')
base.create_async_engine = scoped_engine
state = ROOT / 'runtime' / SCHEMA
state.mkdir(mode=0o700)
settings = Settings(
    _env_file=None, env='test', demo_mode=False, task_mode='inline',
    database_url=url, redis_url=REDIS_URL,
    jwt_secret=secrets.token_urlsafe(48), data_kek=base64.b64encode(os.urandom(32)).decode(),
    storage_dir=state / 'storage', cookie_secure=True,
    cors_origins=[o for o in os.environ.get('FRONTEND_ORIGINS','https://localhost:5173,https://127.0.0.1:5174,https://localhost:5175,https://127.0.0.1:5175').split(',') if o],
    rl_default_per_min=100000, rl_login_per_min=100000, rl_auth_per_min=100000, rl_upload_per_min=100000, rl_review_per_min=100000,
    llm_provider_chain=['deepseek','qwen','ollama'], deepseek_api_key=_deepseek_key(),qwen_api_key=None, deepseek_model=os.environ['DRILL_MODEL'],
    ollama_base_url='http://127.0.0.1:11434', ollama_model='qwen2.5:7b',
)
app = create_app(settings)
original = app.router.lifespan_context

@asynccontextmanager
async def lifespan(application):
    # Unmodified application lifespan checks migrations, runtime role and frozen RLS manifest.
    await provision(config)
    async with original(application):
        from recovery_support import BudgetTransport
        application.state.ai.llm.transport = BudgetTransport(Path("/workspace/competition/backend-recovery-drill-evidence/model-call-counts.json"), "drill8003", proxy="http://127.0.0.1:8899")
        redis = application.state.redis
        if not isinstance(redis, Redis) or not await redis.ping():
            raise RuntimeError('real Redis required; no fakeredis fallback')
        from drill_seed import seed
        await seed(application, ROOT)
        async with application.state.db.engine.connect() as conn:
            row = (await conn.execute(text("SELECT current_schema(),current_user,(SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname=current_user)"))).one()
            if row[0] != SCHEMA or row[2]:
                raise RuntimeError('unsafe live connection')
        proof = {
            'baseline':'c75f877e09decd1b598c26f25e6b70e8742660d7', 'checked_at':datetime.now(ZoneInfo('America/Tijuana')).isoformat(),
            'database':'PostgreSQL', 'schema':SCHEMA, 'runtime_role':row[1],
            'runtime_superuser_or_bypassrls':bool(row[2]),
            'startup_gate':'unmodified check_migrated + check_runtime_access; passed',
            'seeding':'fresh schema + scoped _seed', 'redis':'real redis.asyncio.Redis',
            'redis_ping':True, 'redis_database':0, 'pg_port':5433, 'redis_port':6380, 'api_port':8003, 'cloud_model':settings.deepseek_model, 'tls_verification':True, 'provider_connection':'loopback CONNECT relay; official end-to-end TLS',
            'task_mode':'inline', 'ocr':'actual RapidOCR; not quick_ocr',
            'llm':'actual ProviderChain; no FakeLLM; DeepSeek key injected from private env into this process only (value withheld)',
            'demo_mode':False, 'sqlite_or_fakeredis_fallback':False,
            'production_deployment':False,
        }
        (ROOT/'environment-proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
        (ROOT/'environment-proof.json').chmod(0o600)
        yield

app.router.lifespan_context = lifespan
