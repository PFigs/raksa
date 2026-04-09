"""Read premis invoice exports from the hive-structured directory."""
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class Invoice(BaseModel):
    id: str = ""
    invoice_number: str | None = None
    seller: str | None = None
    accounting_date: str | None = None
    due_date: str | None = None
    amount: float | None = None
    currency: str | None = None
    payment_status: str | None = None
    bank_account: str | None = None
    reject_comment: str | None = None
    pdf_path: Path | None = None

    model_config = {"arbitrary_types_allowed": True}


def load_invoices(invoices_dir: Path) -> list[Invoice]:
    """Load all invoices from a premis invoices directory.

    Expects structure: year=*/month=*/*.yaml (with matching .pdf files).
    """
    invoices = []
    for meta_path in sorted(invoices_dir.rglob("*.yaml")):
        raw = yaml.safe_load(meta_path.read_text())
        if raw is None:
            continue
        pdf_path = meta_path.with_suffix(".pdf")
        invoice = Invoice(
            **raw,
            pdf_path=pdf_path if pdf_path.exists() else None,
        )
        invoices.append(invoice)
    return invoices


def load_invoices_by_seller(invoices_dir: Path) -> dict[str, list[Invoice]]:
    """Group invoices by seller name."""
    by_seller: dict[str, list[Invoice]] = {}
    for invoice in load_invoices(invoices_dir):
        seller = invoice.seller or "Unknown"
        by_seller.setdefault(seller, []).append(invoice)
    return by_seller


def load_invoices_by_year(invoices_dir: Path) -> dict[str, list[Invoice]]:
    """Group invoices by year."""
    by_year: dict[str, list[Invoice]] = {}
    for invoice in load_invoices(invoices_dir):
        year = (invoice.accounting_date or "")[:4] or "unknown"
        by_year.setdefault(year, []).append(invoice)
    return by_year
