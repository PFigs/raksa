from pathlib import Path

import yaml
from typer.testing import CliRunner

from raksa.cli import app

runner = CliRunner()


def _write_invoice(base: Path, year: int, month: int, seller: str, invoice_num: str):
    dir_path = base / f"year={year}" / f"month={month}"
    dir_path.mkdir(parents=True, exist_ok=True)
    safe_seller = seller.replace(" ", "_")
    stem = f"{year}-{month:02d}-01_{safe_seller}_{invoice_num}"
    meta = {
        "id": f"inv-{invoice_num}",
        "invoice_number": invoice_num,
        "seller": seller,
        "accounting_date": f"{year}-{month:02d}-01T00:00:00",
        "amount": 100.0,
        "currency": "EUR",
        "payment_status": "Maksettu",
    }
    (dir_path / f"{stem}.yaml").write_text(yaml.dump(meta))
    (dir_path / f"{stem}.pdf").write_bytes(b"%PDF-fake")


def test_upload_dry_run(tmp_path):
    _write_invoice(tmp_path, 2023, 6, "Builder Oy", "001")
    _write_invoice(tmp_path, 2024, 1, "Plumber Ltd", "002")
    _write_invoice(tmp_path, 2024, 3, "Builder Oy", "003")

    result = runner.invoke(app, ["invoices", "upload", str(tmp_path)])
    assert result.exit_code == 0
    assert "year=2023" in result.output
    assert "year=2024" in result.output
    assert "month=6" in result.output
    assert "month=1" in result.output
    assert "month=3" in result.output
    assert "Dry-run" in result.output


def test_upload_dry_run_filter_years(tmp_path):
    _write_invoice(tmp_path, 2023, 6, "Builder Oy", "001")
    _write_invoice(tmp_path, 2024, 1, "Plumber Ltd", "002")

    result = runner.invoke(app, ["invoices", "upload", str(tmp_path), "--years", "2024"])
    assert result.exit_code == 0
    assert "year=2024" in result.output
    assert "year=2023" not in result.output


def test_upload_dry_run_filter_months(tmp_path):
    _write_invoice(tmp_path, 2024, 1, "Builder Oy", "001")
    _write_invoice(tmp_path, 2024, 3, "Plumber Ltd", "002")
    _write_invoice(tmp_path, 2024, 6, "Builder Oy", "003")

    result = runner.invoke(app, ["invoices", "upload", str(tmp_path), "--months", "3"])
    assert result.exit_code == 0
    assert "month=3" in result.output
    assert "month=1" not in result.output
    assert "month=6" not in result.output
