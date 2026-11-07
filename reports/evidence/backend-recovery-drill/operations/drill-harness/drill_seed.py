import uuid,json
from datetime import datetime,timedelta,timezone
from app.db.models import Tenant,User,Document
from app.db.tenant import TenantScope
from app.security.passwords import hash_password
from tests.conftest import PASSWORDS
async def seed(application,root):
 ids={}
 for label in ['a','b']:
  tenant,user,doc=[str(uuid.uuid4()) for _ in range(3)]
  async with application.state.db.tenant_session(TenantScope(tenant,user,'admin')) as session:
   session.add(Tenant(id=tenant,name='recovery-'+label));await session.flush()
   session.add(User(id=user,tenant_id=tenant,username='drill-'+label,role='admin',password_hash=hash_password(PASSWORDS['reviewer'])));await session.flush()
   _,wrapped=application.state.store.new_wrapped_dek(doc)
   session.add(Document(id=doc,tenant_id=tenant,owner_id=user,filename='synthetic-drill.png',mime='image/png',size_bytes=0,pages=1,sha256='0'*64,wrapped_dek=wrapped,status='ready',expire_at=datetime.now(timezone.utc)+timedelta(days=1)))
   await session.commit()
  ids[label]={'tenant':tenant,'user':user,'document':doc}
 (root/'seed-ids.json').write_text(json.dumps(ids,indent=2)+'\n')
