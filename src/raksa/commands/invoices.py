"""Upload Premis invoice exports to huoneistotieto.fi."""
from collections import defaultdict
from pathlib import Path
from typing import Annotated

import typer

from raksa.config import HuoneistotietoConfig, RaksaConfigError, resolve_ht_config
from raksa.huoneistotieto.client import HuoneistotietoClient

app = typer.Typer(help="Invoice management", no_args_is_help=True)


def _collect_invoice_pairs(
    invoices_dir: Path,
) -> dict[str, dict[str, list[tuple[Path, Path]]]]:
    """Scan hive directory and return {year: {month: [(pdf, yaml), ...]}} pairs."""
    by_year_month: dict[str, dict[str, list[tuple[Path, Path]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for yaml_path in sorted(invoices_dir.rglob("*.yaml")):
        pdf_path = yaml_path.with_suffix(".pdf")
        if not pdf_path.exists():
            continue
        year = month = None
        for part in yaml_path.parts:
            if part.startswith("year="):
                year = part.split("=")[1]
            elif part.startswith("month="):
                month = part.split("=")[1]
        if year and month:
            by_year_month[year][month].append((pdf_path, yaml_path))
    return {y: dict(months) for y, months in by_year_month.items()}


def _get_ht_client(
    parent_folder_id: str | None = None,
    require_parent_folder: bool = True,
) -> tuple[HuoneistotietoClient, HuoneistotietoConfig]:
    try:
        ht_config = resolve_ht_config(
            parent_folder_id_override=parent_folder_id,
            require_parent_folder=require_parent_folder,
        )
    except RaksaConfigError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    return HuoneistotietoClient(
        token=ht_config.token,
        user_id=ht_config.user_id,
        office_id=ht_config.office_id,
        condominium_id=ht_config.condominium_id,
        condominium_number=ht_config.condominium_number,
    ), ht_config


@app.command("folders")
def folders():
    """List document folders on huoneistotieto.fi."""
    client, _ = _get_ht_client(require_parent_folder=False)
    result = client.list_folders()

    def print_tree(items: list[dict], indent: int = 0):
        for item in items:
            if item.get("type") != "folder":
                continue
            label = item.get("label", "?")
            key = item.get("key", "?")
            prefix = "  " * indent
            typer.echo(f"{prefix}{label}  [{key}]")
            for child in item.get("children", []):
                if child.get("type") == "folder":
                    print_tree([child], indent + 1)

    print_tree(result)


@app.command("upload")
def upload(
    invoices_dir: Annotated[Path, typer.Argument(help="Path to premis invoices hive directory")],
    submit: Annotated[bool, typer.Option("--submit", help="Actually upload (default is dry-run)")] = False,
    years: Annotated[str | None, typer.Option("--years", help="Comma-separated years to upload (default: all)")] = None,
    months: Annotated[str | None, typer.Option("--months", help="Comma-separated months to upload (default: all)")] = None,
    parent_folder_id: Annotated[str | None, typer.Option("--parent-folder-id", help="Override parent folder ID")] = None,
):
    """Upload Premis invoice exports to huoneistotieto.fi."""
    if not invoices_dir.is_dir():
        typer.echo(f"Error: {invoices_dir} is not a directory", err=True)
        raise typer.Exit(1)

    all_data = _collect_invoice_pairs(invoices_dir)
    if not all_data:
        typer.echo("No invoice pairs (PDF + YAML) found.")
        return

    # Filter years
    if years:
        requested_years = {y.strip() for y in years.split(",")}
        all_data = {y: m for y, m in all_data.items() if y in requested_years}

    # Filter months
    if months:
        requested_months = {m.strip() for m in months.split(",")}
        all_data = {
            y: {m: pairs for m, pairs in by_month.items() if m in requested_months}
            for y, by_month in all_data.items()
        }
        all_data = {y: m for y, m in all_data.items() if m}

    if not all_data:
        typer.echo("No invoices match the requested filters.")
        return

    typer.echo(f"Found invoices in {len(all_data)} year(s):\n")
    total = 0
    for year in sorted(all_data):
        by_month = all_data[year]
        year_total = sum(len(pairs) for pairs in by_month.values())
        total += year_total
        typer.echo(f"  year={year}: {year_total} invoices")
        for month in sorted(by_month, key=int):
            typer.echo(f"    month={month}: {len(by_month[month])} invoices")

    typer.echo(f"\nTotal: {total} invoices ({total * 2} files)")

    if not submit:
        typer.echo("\nDry-run mode. Pass --submit to actually upload.")
        return

    client, ht_config = _get_ht_client(parent_folder_id=parent_folder_id)

    batch_size = 20
    errors = []

    for year in sorted(all_data):
        by_month = all_data[year]
        typer.echo(f"\nCreating folder year={year}...")
        try:
            year_folder_id = client.create_folder(
                name=f"year={year}",
                parent_id=ht_config.parent_folder_id,
            )
        except Exception as e:
            typer.echo(f"  Error creating folder: {e}", err=True)
            errors.append(f"year={year}: folder creation failed")
            continue
        typer.echo(f"  Created: {year_folder_id}")

        for month in sorted(by_month, key=int):
            pairs = by_month[month]
            typer.echo(f"  Creating folder month={month}...")
            try:
                month_folder_id = client.create_folder(
                    name=f"month={month}",
                    parent_id=year_folder_id,
                )
            except Exception as e:
                typer.echo(f"    Error creating folder: {e}", err=True)
                errors.append(f"year={year}/month={month}: folder creation failed")
                continue
            typer.echo(f"    Created: {month_folder_id}")

            files = []
            for pdf_path, yaml_path in pairs:
                files.append(pdf_path)
                files.append(yaml_path)

            for i in range(0, len(files), batch_size):
                batch = files[i : i + batch_size]
                typer.echo(f"    Uploading batch {i // batch_size + 1} ({len(batch)} files)...")
                try:
                    client.upload_files(folder_id=month_folder_id, files=batch)
                except Exception as e:
                    typer.echo(f"    Error uploading batch: {e}", err=True)
                    errors.append(f"year={year}/month={month} batch {i // batch_size + 1}: upload failed")
                    continue

            typer.echo(f"    Uploaded {len(pairs)} invoices")

    if errors:
        typer.echo(f"\nDone with {len(errors)} error(s):")
        for err in errors:
            typer.echo(f"  - {err}")
    else:
        typer.echo("\nDone.")
