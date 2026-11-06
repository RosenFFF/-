from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator
from openapi_spec_validator import validate

from app.main import create_app

from .conftest import make_settings

SPEC = Path(__file__).resolve().parents[2] / "docs" / "api.yaml"
METHODS = {"get", "post", "patch", "delete", "put"}
AUDIT_PATHS = ["/audit/logs", "/audit/stats", "/audit/verify", "/reviews/{review_id}/audit"]


def normalize_refs(schema):
    if isinstance(schema, dict):
        return {k: normalize_refs(v) for k, v in schema.items() if k != "title"}
    if isinstance(schema, list):
        return [normalize_refs(v) for v in schema]
    return schema.replace("AuditLogOut", "AuditLog") if isinstance(schema, str) else schema


def test_entire_openapi_valid_route_method_parity_and_write_rate_contract(tmp_path):
    documented = yaml.safe_load(SPEC.read_text())
    generated = create_app(make_settings(tmp_path)).openapi()
    validate(documented)
    validate(generated)
    declared = {(p, m) for p, v in documented["paths"].items() for m in v if m in METHODS}
    implemented = {(p.removeprefix("/api/v1"), m) for p, v in generated["paths"].items() for m in v if m in METHODS}
    assert declared == implemented
    for path, method in declared:
        if method in {"post", "patch", "delete", "put"}:
            assert {"429", "503"} <= set(documented["paths"][path][method]["responses"])
            assert {"429", "503"} <= set(generated["paths"]["/api/v1" + path][method]["responses"])
    for path in AUDIT_PATHS:
        declared_op = documented["paths"][path]["get"]
        actual = generated["paths"]["/api/v1" + path]["get"]
        assert normalize_refs(declared_op.get("parameters", [])) == normalize_refs(actual.get("parameters", []))
        assert normalize_refs(declared_op["responses"]["200"]) == normalize_refs(actual["responses"]["200"])
    for name in (
        "AuditLogOut",
        "AuditPage",
        "AuditVerify",
        "SecurityStats",
        "SecurityTotals",
        "SecurityBucket",
        "DeniedActor",
    ):
        assert normalize_refs(generated["components"]["schemas"][name]) == normalize_refs(
            documented["components"]["schemas"][name.replace("AuditLogOut", "AuditLog")]
        )


@pytest.mark.parametrize(
    "endpoint,schema", [("logs", "AuditPage"), ("stats", "SecurityStats"), ("verify", "AuditVerify")]
)
async def test_actual_audit_json_conforms_to_published_schema(api, endpoint, schema):
    c = await api.login("auditor")
    response = await c.get("/api/v1/audit/" + endpoint)
    assert response.status_code == 200
    documented = yaml.safe_load(SPEC.read_text())
    Draft202012Validator({"$ref": "#/components/schemas/" + schema, "components": documented["components"]}).validate(
        response.json()
    )


def test_production_has_no_demo_routes_even_if_demo_flag_misconfigured(tmp_path):
    app = create_app(make_settings(tmp_path, env="prod", demo_mode=True))
    assert all("/demo/" not in path for path in app.openapi()["paths"])
    assert app.docs_url is None and app.openapi_url is None
