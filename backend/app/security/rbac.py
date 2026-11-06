"""角色与权限。reviewer = 合规员，auditor = 安全管理员。服务端每个接口都显式声明所需权限。"""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    admin = "admin"
    reviewer = "reviewer"
    auditor = "auditor"


class Perm(StrEnum):
    user_manage = "user:manage"
    document_upload = "document:upload"
    document_read = "document:read"
    document_edit = "document:edit"
    document_delete = "document:delete"
    review_create = "review:create"
    review_read = "review:read"
    chat_write = "chat:write"
    audit_read_own_case = "audit:read_own_case"
    audit_read_all = "audit:read_all"


ROLE_PERMS: dict[Role, frozenset[Perm]] = {
    Role.admin: frozenset(Perm),
    Role.reviewer: frozenset(
        {
            Perm.document_upload,
            Perm.document_read,
            Perm.document_edit,
            Perm.document_delete,
            Perm.review_create,
            Perm.review_read,
            Perm.chat_write,
            Perm.audit_read_own_case,
        }
    ),
    Role.auditor: frozenset(
        {
            Perm.document_read,
            Perm.review_read,
            Perm.audit_read_own_case,
            Perm.audit_read_all,
        }
    ),
}


def perms_of(role: str) -> frozenset[Perm]:
    try:
        return ROLE_PERMS[Role(role)]
    except ValueError:
        return frozenset()
