"""管理命令：创建用户（密码交互输入，不出现在命令行历史里）。

python -m app.cli create-user --username reviewer1 --role reviewer
"""

from __future__ import annotations

import argparse
import asyncio
import getpass

from sqlalchemy import select

from app.core.config import get_settings
from app.db.base import Database
from app.db.models import Tenant, User
from app.security.passwords import hash_password
from app.security.rbac import Role


async def create_user(username: str, role: str) -> None:
    pw = getpass.getpass("密码（≥12 位）: ")
    if len(pw) < 12 or pw != getpass.getpass("再输一次: "):
        raise SystemExit("密码太短或两次不一致")
    db = Database(get_settings().database_url)
    await db.check_migrated()
    async with db.maintenance_sessionmaker() as s:
        t = (await s.execute(select(Tenant).limit(1))).scalar_one_or_none()
        if t is None:
            t = Tenant(name="default")
            s.add(t)
            await s.flush()
        s.add(User(tenant_id=t.id, username=username, password_hash=hash_password(pw), role=role))
        await s.commit()
    await db.dispose()
    print(f"已创建 {username}（{role}）")


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create-user")
    c.add_argument("--username", required=True)
    c.add_argument("--role", required=True, choices=[r.value for r in Role])
    sub.add_parser("adopt-legacy-schema", help="备份后验证完整旧 schema，匹配才 stamp；不修改业务表")
    a = p.parse_args()
    if a.cmd == "adopt-legacy-schema":

        async def adopt():
            db = Database(get_settings().database_url)
            try:
                await db.adopt_legacy_schema()
            finally:
                await db.dispose()

        asyncio.run(adopt())
    else:
        asyncio.run(create_user(a.username, a.role))


if __name__ == "__main__":
    main()
