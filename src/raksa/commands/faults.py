from pathlib import Path
from typing import Annotated

import typer

from raksa.client import EstateAppClient, EstateAppError
from raksa.config import resolve_token, resolve_condo_id, resolve_base_url, RaksaConfigError
from raksa.premis.cases import load_fault_cases, get_chat_path

app = typer.Typer(help="Fault notification management", no_args_is_help=True)


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


@app.command("list")
def list_faults(
    condo_id: Annotated[str | None, typer.Option("--condo-id", help="Condominium ID")] = None,
):
    """List fault notifications for a condominium."""
    client = _get_client()
    resolved_condo_id = _get_condo_id(condo_id)
    try:
        faults = client.list_faults(resolved_condo_id)
    except EstateAppError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    if not faults:
        typer.echo("No faults found.")
        return

    typer.echo(f"{'ID':<26} {'Description':<50} {'Created'}")
    typer.echo("-" * 90)
    for f in faults:
        desc = (f.fault_description or "")[:48]
        typer.echo(f"{f.id or '':<26} {desc:<50} {f.created_at or ''}")


@app.command("get")
def get_fault(
    fault_id: Annotated[str, typer.Argument(help="Fault notification ID")],
):
    """Get details of a fault notification."""
    client = _get_client()
    try:
        f = client.get_fault(fault_id)
    except EstateAppError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    typer.echo(f"ID:          {f.id}")
    typer.echo(f"Created:     {f.created_at}")
    typer.echo(f"Address:     {f.street_address}")
    typer.echo(f"Space:       {f.space}")
    typer.echo(f"Apartment:   {f.apartment}")
    typer.echo(f"Description: {f.fault_description}")
    typer.echo(f"Contact:     {f.contact_name} / {f.contact_phone}")
    typer.echo(f"Additional:  {f.additional_information}")
    typer.echo(f"Completed:   {f.completed_at}")


@app.command("import")
def import_faults(
    yaml_dir: Annotated[Path, typer.Argument(help="Directory containing YAML case files")],
    condo_id: Annotated[str | None, typer.Option("--condo-id", help="Condominium ID")] = None,
    submit: Annotated[bool, typer.Option("--submit", help="Actually submit (default is dry-run)")] = False,
):
    """Import fault cases from YAML files into EstateApp."""
    resolved_condo_id = _get_condo_id(condo_id)
    entries = load_fault_cases(yaml_dir)

    if not entries:
        typer.echo("No fault cases found.")
        return

    typer.echo(f"Found {len(entries)} fault case(s):")
    for case, path in entries:
        space = case.space.name if case.space else "?"
        desc = (case.description or "")[:50]
        typer.echo(f"  {case.title}  {space:6s}  {desc}")

    if not submit:
        typer.echo("\nDry-run mode. Pass --submit to actually import.")
        return

    client = _get_client()
    success = 0
    for case, path in entries:
        try:
            fault_input = case.to_fault_input()
            fault_id = client.create_fault(resolved_condo_id, fault_input)

            # Mark as completed (historical)
            client._gql("""
            mutation completeFaultNotification($faultNotificationId: ID!) {
                completeFaultNotification(faultNotificationId: $faultNotificationId)
            }
            """, {"faultNotificationId": fault_id})

            # Upload YAML files
            client.upload_file(path, fault_id, "faultNotification")
            chat = get_chat_path(path)
            if chat:
                client.upload_file(chat, fault_id, "faultNotification")

            typer.echo(f"  OK  [{case.title}] -> {fault_id} (completed, files uploaded)")
            success += 1
        except (EstateAppError, Exception) as e:
            typer.echo(f"  FAIL [{case.title}]: {e}", err=True)

    typer.echo(f"\nImported {success}/{len(entries)} fault case(s).")
