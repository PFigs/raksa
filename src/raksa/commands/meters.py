from pathlib import Path
from typing import Annotated

import typer

from raksa.client import EstateAppClient, EstateAppError
from raksa.config import resolve_token, resolve_condo_id, resolve_base_url, RaksaConfigError
from raksa.meters.zaptec import read_all_reports, read_usage_report
from raksa.meters.readings import load_readings
from raksa.meters.estateapp import ensure_meters_exist, submit_readings, get_consumption_summary

app = typer.Typer(help="Consumption meter management", no_args_is_help=True)


def _get_client() -> EstateAppClient:
    try:
        token = resolve_token()
    except RaksaConfigError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    return EstateAppClient(token=token, base_url=resolve_base_url())


def _get_condo_id(condo_id: str | None) -> str:
    resolved = condo_id or resolve_condo_id()
    if not resolved:
        typer.echo("Error: --condo-id required (or set RAKSA_CONDO_ID)", err=True)
        raise typer.Exit(1)
    return resolved


@app.command("import-zaptec")
def import_zaptec(
    path: Annotated[Path, typer.Argument(help="Zaptec Excel file or directory of files")],
    condo_id: Annotated[str | None, typer.Option("--condo-id", help="Condominium ID")] = None,
    submit: Annotated[bool, typer.Option("--submit", help="Actually submit (default is dry-run)")] = False,
):
    """Import EV charger consumption from Zaptec Excel exports."""
    cid = _get_condo_id(condo_id)

    if path.is_dir():
        zaptec_readings = read_all_reports(path)
    elif path.suffix == ".xlsx":
        zaptec_readings = read_usage_report(path)
    else:
        typer.echo(f"Error: {path} is not an xlsx file or directory", err=True)
        raise typer.Exit(1)

    if not zaptec_readings:
        typer.echo("No readings found.")
        return

    typer.echo(f"Found {len(zaptec_readings)} reading(s):\n")
    for r in zaptec_readings:
        typer.echo(f"  {r.charger:8s}  {r.period_start} - {r.period_end}  {r.energy_kwh:>10.2f} kWh  ({r.sessions} sessions)")

    charger_labels = sorted({r.charger for r in zaptec_readings})
    typer.echo(f"\nMeters: {', '.join(charger_labels)}")

    if not submit:
        typer.echo("\nDry-run mode. Pass --submit to actually import.")
        return

    client = _get_client()

    typer.echo("\nEnsuring meters exist...")
    label_to_key = ensure_meters_exist(client, cid, charger_labels, category="electricity")
    for label, key in label_to_key.items():
        typer.echo(f"  {label} -> {key}")

    typer.echo("\nSubmitting consumption data...")
    api_readings = [
        {
            "category": "electricity",
            "specification": label_to_key[r.charger],
            "readingDate": r.period_end,
            "value": r.energy_kwh,
            "type": "usual",
        }
        for r in zaptec_readings
    ]
    submit_readings(client, cid, api_readings)
    typer.echo(f"  Submitted {len(api_readings)} reading(s)")

    typer.echo("\nVerifying...")
    summary = get_consumption_summary(client, cid)
    for s in summary:
        if s["category"] == "electricity":
            for y in s.get("years", []):
                typer.echo(f"  {y['year']}: {y['value']:.2f} kWh")


UTILITY_TO_CATEGORY = {
    "electricity": "electricity",
    "heat": "heat",
    "water": "water",
}

UTILITY_TO_LABEL = {
    "electricity": "Common electricity",
    "heat": "District heating",
    "water": "Water",
}


@app.command("import-readings")
def import_readings(
    readings_dir: Annotated[Path, typer.Argument(help="Directory of consumption reading YAML files")],
    condo_id: Annotated[str | None, typer.Option("--condo-id", help="Condominium ID")] = None,
    submit: Annotated[bool, typer.Option("--submit", help="Actually submit (default is dry-run)")] = False,
):
    """Import consumption readings from YAML files into EstateApp meters."""
    cid = _get_condo_id(condo_id)
    readings = load_readings(readings_dir)

    if not readings:
        typer.echo("No readings found.")
        return

    by_utility: dict[str, list] = {}
    for r in readings:
        by_utility.setdefault(r.utility, []).append(r)

    for utility, utility_readings in sorted(by_utility.items()):
        typer.echo(f"\n{utility} ({len(utility_readings)} readings):")
        for r in utility_readings:
            cost_total = sum(c.amount_eur for c in r.costs)
            cost_str = f"  {cost_total:.2f} EUR" if r.costs else ""
            typer.echo(f"  {r.period_start} - {r.period_end}  {r.consumption:>10.3f} {r.unit}{cost_str}")

    if not submit:
        typer.echo("\nDry-run mode. Pass --submit to actually import.")
        return

    client = _get_client()

    # Group by meter label (not utility) so multiple meters of same utility work
    by_label: dict[str, list] = {}
    for r in readings:
        by_label.setdefault(r.meter_label, []).append(r)

    for label, label_readings in sorted(by_label.items()):
        category = UTILITY_TO_CATEGORY.get(label_readings[0].utility, label_readings[0].utility)

        typer.echo(f"\nEnsuring meter exists: {label}...")
        label_to_key = ensure_meters_exist(client, cid, [label], category=category)
        key = label_to_key[label]
        typer.echo(f"  {label} -> {key}")

        typer.echo("Submitting readings...")
        api_readings = [
            {
                "category": category,
                "specification": key,
                "readingDate": r.reading_date,
                "value": r.consumption,
                "type": "usual",
            }
            for r in label_readings
        ]
        submit_readings(client, cid, api_readings)
        typer.echo(f"  Submitted {len(api_readings)} reading(s)")

    typer.echo("\nVerifying...")
    summary_data = get_consumption_summary(client, cid)
    for s in summary_data:
        typer.echo(f"\n{s['category']}:")
        for y in s.get("years", []):
            typer.echo(f"  {y['year']}: {y['value']:.2f}")


@app.command("summary")
def summary(
    condo_id: Annotated[str | None, typer.Option("--condo-id", help="Condominium ID")] = None,
):
    """Show consumption summary for a condominium."""
    client = _get_client()
    cid = _get_condo_id(condo_id)

    data = get_consumption_summary(client, cid)
    if not data:
        typer.echo("No consumption data found.")
        return

    for category_data in data:
        cat = category_data["category"]
        typer.echo(f"\n{cat}:")
        for y in category_data.get("years", []):
            typer.echo(f"  {y['year']}: {y['value']:.2f}")
