from pathlib import Path
from typing import Annotated

import typer
import yaml

from raksa.client import EstateAppClient, EstateAppError
from raksa.config import resolve_token, resolve_condo_id, resolve_base_url, RaksaConfigError
from raksa.models import YAMLCase

app = typer.Typer(help="Shareholder renovation management", no_args_is_help=True)


def _get_client() -> EstateAppClient:
    try:
        token = resolve_token()
    except RaksaConfigError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    base_url = resolve_base_url()
    return EstateAppClient(token=token, base_url=base_url)


def _get_condo_id(condo_id: str | None) -> str:
    resolved = condo_id or resolve_condo_id()
    if not resolved:
        typer.echo(
            "Error: condo ID required. Pass --condo-id or set RAKSA_CONDO_ID.", err=True
        )
        raise typer.Exit(1)
    return resolved


def load_renovation_cases(yaml_dir: Path) -> list[YAMLCase]:
    cases = []
    for path in yaml_dir.rglob("*.yaml"):
        if path.stem.endswith("_chat"):
            continue
        raw = yaml.safe_load(path.read_text())
        if raw is None:
            continue
        case = YAMLCase.model_validate(raw)
        if case.is_renovation:
            cases.append(case)
    return cases


@app.command("list")
def list_renovations(
    condo_id: Annotated[str | None, typer.Option("--condo-id", help="Condominium ID")] = None,
):
    """List shareholder renovation gigs for a condominium."""
    client = _get_client()
    resolved_condo_id = _get_condo_id(condo_id)
    try:
        renovations = client.list_renovations(resolved_condo_id)
    except EstateAppError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    if not renovations:
        typer.echo("No renovations found.")
        return

    typer.echo(f"{'ID':<26} {'Title':<40} {'Status':<20} {'Created'}")
    typer.echo("-" * 100)
    for r in renovations:
        typer.echo(f"{r.id or '':<26} {(r.title or ''):<40} {(r.status or ''):<20} {r.created_at or ''}")


@app.command("get")
def get_renovation(
    gig_id: Annotated[str, typer.Argument(help="Renovation gig ID")],
):
    """Get details of a shareholder renovation gig."""
    client = _get_client()
    try:
        r = client.get_renovation(gig_id)
    except EstateAppError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    typer.echo(f"ID:          {r.id}")
    typer.echo(f"Title:       {r.title}")
    typer.echo(f"Status:      {r.status}")
    typer.echo(f"Created:     {r.created_at}")
    typer.echo(f"Start date:  {r.start_date}")
    typer.echo(f"End date:    {r.end_date}")
    typer.echo(f"Description: {r.description}")
    if r.shareholder_renovation_work:
        work = r.shareholder_renovation_work
        typer.echo(f"Address:     {work.apartment_address}")
        if work.informant:
            typer.echo(f"Informant:   {work.informant.name}")
        if work.contractors:
            typer.echo(f"Contractors: {', '.join(c.company_name or '' for c in work.contractors)}")


@app.command("import")
def import_renovations(
    yaml_dir: Annotated[Path, typer.Argument(help="Directory containing YAML case files")],
    condo_id: Annotated[str | None, typer.Option("--condo-id", help="Condominium ID")] = None,
    submit: Annotated[bool, typer.Option("--submit", help="Actually submit (default is dry-run)")] = False,
):
    """Import renovation cases from YAML files into EstateApp."""
    resolved_condo_id = _get_condo_id(condo_id)
    cases = load_renovation_cases(yaml_dir)

    if not cases:
        typer.echo("No renovation cases found.")
        return

    typer.echo(f"Found {len(cases)} renovation case(s):")
    for case in cases:
        typer.echo(f"  {case.title}")

    if not submit:
        typer.echo("\nDry-run mode. Pass --submit to actually import.")
        return

    client = _get_client()
    success = 0
    for case in cases:
        gig_input = case.to_renovation_input(resolved_condo_id)
        try:
            gig_id = client.create_renovation(gig_input)
            typer.echo(f"  Created: {gig_id} ({case.title})")
            success += 1
        except EstateAppError as e:
            typer.echo(f"  Failed {case.title}: {e}", err=True)

    typer.echo(f"\nImported {success}/{len(cases)} renovation case(s).")
