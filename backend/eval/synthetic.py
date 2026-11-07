"""Deterministic synthetic commercial invoices; no real entities or legal labels."""

LABELS = {
    "invoice_no": "INVOICE NO",
    "total_amount": "TOTAL",
    "currency": "CURRENCY",
    "hs_code": "HS CODE",
    "origin_country": "ORIGIN COUNTRY",
    "quantity": "QUANTITY",
    "unit_price": "UNIT PRICE",
    "goods_description": "GOODS",
    "consignee": "CONSIGNEE",
}


def samples():
    result = []
    kinds = ["clean"] * 8 + ["missing"] * 3 + ["hs"] * 3 + ["amount"] * 3 + ["restricted"] * 3
    for i, kind in enumerate(kinds, 1):
        fields = dict(
            invoice_no=f"SYN-{i:03d}",
            total_amount=f"{100 + i}.00",
            currency="USD",
            hs_code="610910",
            origin_country="CN",
            quantity="1",
            unit_price=f"{100 + i}.00",
            goods_description="COTTON SHIRTS",
            consignee="SYNTHETIC BUYER",
        )
        expected = ["SYN-REVIEW"]
        if kind == "missing":
            fields["origin_country"] = None
            expected += ["SYN-REQUIRED"]
        elif kind == "hs":
            fields["hs_code"] = "12345"
            expected += ["SYN-HS"]
        elif kind == "amount":
            fields["quantity"] = "2"
            expected += ["SYN-AMOUNT"]
        elif kind == "restricted":
            fields["goods_description"] = "DEMO-RESTRICTED"
            expected += ["SYN-RESTRICTED"]
        result.append(
            dict(
                id=i,
                kind=kind,
                synthetic=True,
                fields=fields,
                expected_rules=expected,
                lines=["COMMERCIAL INVOICE"] + [f"{LABELS[k]}: {v}" for k, v in fields.items() if v is not None],
            )
        )
    return result
