from pathlib import Path

import yaml

from raksa.premis.invoices import load_invoices, load_invoices_by_seller, load_invoices_by_year


def _write_invoice(tmp_path, year, month, seller, amount, invoice_num="123"):
    dir_path = tmp_path / f"year={year}" / f"month={month}"
    dir_path.mkdir(parents=True, exist_ok=True)
    safe_seller = seller.replace(" ", "_")
    base = f"{year}-{month:02d}-01_{safe_seller}_{invoice_num}"
    meta = {
        "id": f"inv-{invoice_num}",
        "invoice_number": invoice_num,
        "seller": seller,
        "accounting_date": f"{year}-{month:02d}-01T00:00:00",
        "due_date": f"{year}-{month:02d}-15T00:00:00",
        "amount": amount,
        "currency": "EUR",
        "payment_status": "Maksettu",
        "bank_account": "FI123",
        "reject_comment": None,
    }
    meta_path = dir_path / f"{base}.yaml"
    meta_path.write_text(yaml.dump(meta))
    pdf_path = dir_path / f"{base}.pdf"
    pdf_path.write_bytes(b"%PDF-fake")
    return meta_path


def test_load_invoices(tmp_path):
    _write_invoice(tmp_path, 2024, 1, "Builder Oy", 1000.0)
    _write_invoice(tmp_path, 2024, 6, "Plumber Ltd", 500.0, "456")

    invoices = load_invoices(tmp_path)
    assert len(invoices) == 2
    assert invoices[0].seller == "Builder Oy"
    assert invoices[0].amount == 1000.0
    assert invoices[0].pdf_path is not None
    assert invoices[0].pdf_path.exists()


def test_load_invoices_by_seller(tmp_path):
    _write_invoice(tmp_path, 2024, 1, "Builder Oy", 1000.0)
    _write_invoice(tmp_path, 2024, 3, "Builder Oy", 2000.0, "789")
    _write_invoice(tmp_path, 2024, 6, "Plumber Ltd", 500.0, "456")

    by_seller = load_invoices_by_seller(tmp_path)
    assert len(by_seller) == 2
    assert len(by_seller["Builder Oy"]) == 2
    assert len(by_seller["Plumber Ltd"]) == 1


def test_load_invoices_by_year(tmp_path):
    _write_invoice(tmp_path, 2023, 12, "Builder Oy", 800.0, "001")
    _write_invoice(tmp_path, 2024, 1, "Builder Oy", 1000.0)

    by_year = load_invoices_by_year(tmp_path)
    assert "2023" in by_year
    assert "2024" in by_year
    assert len(by_year["2023"]) == 1
    assert len(by_year["2024"]) == 1


def test_load_real_invoices():
    invoices_dir = Path("/home/silva/home projects/premis/invoices")
    if not invoices_dir.exists():
        return
    invoices = load_invoices(invoices_dir)
    assert len(invoices) > 0
    for inv in invoices[:5]:
        assert inv.seller
        assert inv.amount is not None
