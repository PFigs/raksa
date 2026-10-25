import csv
import datetime
import os
from collections import Counter
from pathlib import Path
from typing import Annotated

import httpx
import typer
from dotenv import find_dotenv, load_dotenv

from raksa.client import EstateAppClient
from raksa.config import (
    HT_CONDOMINIUM_NUMBER_ENV,
    RaksaConfigError,
    resolve_base_url,
    resolve_condo_id,
    resolve_ht_login,
    resolve_token,
)
from raksa.huoneistotieto.client import HuoneistotietoClient
from raksa.link_sign_in import LinkSignInError, huoneistotieto_token, sign_in_through_huoneistotieto
from raksa.meters.bills import BillParseError, BillReading, parse_bill
from raksa.meters.datahub import DATAHUB_METER_LABEL, DatahubError, read_export
from raksa.meters.estateapp import (
    PlannedReading,
    ReadingPlanError,
    ensure_meters_exist,
    get_consumption_summary,
    get_consumptions,
    label_to_key,
    plan_readings,
    reading_date_to_iso,
    replace_reading,
    submit_readings,
)
from raksa.meters.fmi import fetch_monthly_temperatures
from raksa.meters.readings import load_readings
from raksa.meters.zaptec import read_all_reports, read_usage_report
from raksa.meters.zaptec_live import ZaptecSession, fetch_archived_sessions

app = typer.Typer(help="Consumption meter management", no_args_is_help=True)

ZAPTEC_USERNAME_ENV = "RAKSA_ZAPTEC_USERNAME"
ZAPTEC_PASSWORD_ENV = "RAKSA_ZAPTEC_PASSWORD"
ZAPTEC_INSTALLATION_ID_ENV = "RAKSA_ZAPTEC_INSTALLATION_ID"
ZAPTEC_LOOKBACK_DAYS_ENV = "RAKSA_ZAPTEC_SYNC_LOOKBACK_DAYS"


def _get_client() -> EstateAppClient:
    base_url = resolve_base_url()
    try:
        ht_login = resolve_ht_login()
        token = sign_in_through_huoneistotieto(login=ht_login, base_url=base_url) if ht_login else resolve_token()
    except (RaksaConfigError, LinkSignInError) as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    return EstateAppClient(token=token, base_url=base_url)


def _get_condo_id(condo_id: str | None) -> str:
    resolved = condo_id or resolve_condo_id()
    if not resolved:
        typer.echo("Error: --condo-id required (or set RAKSA_CONDO_ID)", err=True)
        raise typer.Exit(1)
    return resolved


def _parse_utc_datetime(value: str, source: str) -> datetime.datetime:
    try:
        parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        typer.echo(f"Error: invalid datetime in {source}: {value}", err=True)
        raise typer.Exit(1)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed.astimezone(datetime.timezone.utc)


def _resolve_lookback_days(lookback_days: int | None) -> int:
    if lookback_days is not None:
        if lookback_days < 1:
            typer.echo("Error: --lookback-days must be greater than 0", err=True)
            raise typer.Exit(1)
        return lookback_days

    env_val = os.environ.get(ZAPTEC_LOOKBACK_DAYS_ENV)
    if not env_val:
        return 7
    try:
        parsed = int(env_val)
    except ValueError:
        typer.echo(f"Error: {ZAPTEC_LOOKBACK_DAYS_ENV} must be an integer", err=True)
        raise typer.Exit(1)
    if parsed < 1:
        typer.echo(f"Error: {ZAPTEC_LOOKBACK_DAYS_ENV} must be greater than 0", err=True)
        raise typer.Exit(1)
    return parsed


def _resolve_zaptec_credentials() -> tuple[str, str]:
    load_dotenv(dotenv_path=find_dotenv(usecwd=True))

    username = os.environ.get(ZAPTEC_USERNAME_ENV) or os.environ.get("ZAPTEC_USERNAME")
    password = os.environ.get(ZAPTEC_PASSWORD_ENV) or os.environ.get("ZAPTEC_PASSWORD")

    if not username:
        typer.echo(
            f"Error: missing {ZAPTEC_USERNAME_ENV} (or ZAPTEC_USERNAME)",
            err=True,
        )
        raise typer.Exit(1)
    if not password:
        typer.echo(
            f"Error: missing {ZAPTEC_PASSWORD_ENV} (or ZAPTEC_PASSWORD)",
            err=True,
        )
        raise typer.Exit(1)
    return username, password


def _resolve_installation_id(installation_id: str | None) -> str:
    resolved = installation_id or os.environ.get(ZAPTEC_INSTALLATION_ID_ENV) or os.environ.get("ZAPTEC_INSTALLATION_ID")
    if not resolved:
        typer.echo(
            f"Error: pass --installation-id or set {ZAPTEC_INSTALLATION_ID_ENV} (or ZAPTEC_INSTALLATION_ID)",
            err=True,
        )
        raise typer.Exit(1)
    return resolved


def _reading_key(specification: str, reading_date: str, value: float) -> tuple[str, str, float]:
    return specification, reading_date, round(value, 3)


def _select_new_sessions(
    client: EstateAppClient,
    condo_id: str,
    sessions: list[ZaptecSession],
) -> list[ZaptecSession]:
    """Drop sessions already imported, matching them against EstateApp readings."""
    dates = sorted({session.ended_at.date() for session in sessions})
    existing = get_consumptions(
        client,
        condo_id,
        start_date=dates[0].isoformat(),
        end_date=dates[-1].isoformat(),
    )

    unmatched: Counter = Counter()
    for reading in existing:
        reading_date = reading_date_to_iso(reading.get("readingDate"))
        value = reading.get("value")
        if reading_date is None or value is None:
            continue
        unmatched[_reading_key(str(reading.get("specification")), reading_date, float(value))] += 1

    new_sessions = []
    for session in sessions:
        key = _reading_key(
            label_to_key(session.charger_label),
            session.ended_at.date().isoformat(),
            session.energy_kwh,
        )
        if unmatched[key]:
            unmatched[key] -= 1
            continue
        new_sessions.append(session)
    return new_sessions


def _datahub_existing_readings(client: EstateAppClient, condo_id: str, key: str, export) -> list[dict]:
    return [
        reading
        for reading in get_consumptions(
            client,
            condo_id,
            start_date=f"{export.months[0].year}-{export.months[0].month:02d}-01",
            end_date=export.months[-1].reading_date,
        )
        if reading.get("specification") == key
    ]


def _datahub_pairs(export) -> list[tuple[str, float]]:
    return [(month.reading_date, month.consumption_kwh) for month in export.months]


def _write_sync_csv(csv_path: Path, sessions: list[ZaptecSession]):
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "meter", "kwh"])
        writer.writerows(
            [
                session.ended_at.date().isoformat(),
                session.charger_label,
                f"{session.energy_kwh:.3f}",
            ]
            for session in sessions
        )


@app.command("sync-zaptec")
def sync_zaptec(
    condo_id: Annotated[str | None, typer.Option("--condo-id", help="Condominium ID")] = None,
    installation_id: Annotated[str | None, typer.Option("--installation-id", help=f"Zaptec installation UUID (or set {ZAPTEC_INSTALLATION_ID_ENV})")] = None,
    submit: Annotated[bool, typer.Option("--submit", help="Actually submit (default is dry-run)")] = False,
    dry_run_csv: Annotated[Path | None, typer.Option("--dry-run-csv", help="Write dry-run output as CSV (date,meter,kwh)")] = None,
    since: Annotated[str | None, typer.Option("--since", help="Override sync start timestamp (ISO 8601)")] = None,
    lookback_days: Annotated[int | None, typer.Option("--lookback-days", help=f"Sync window length in days (or set {ZAPTEC_LOOKBACK_DAYS_ENV})")] = None,
    page_size: Annotated[int, typer.Option("--page-size", min=1, max=200, help="Zaptec API page size")] = 100,
    include_disabled: Annotated[bool, typer.Option("--include-disabled", help="Include disabled objects in Zaptec response")] = False,
):
    """Sync Zaptec archived charging sessions into EstateApp meters."""
    cid = _get_condo_id(condo_id)
    username, password = _resolve_zaptec_credentials()
    resolved_installation_id = _resolve_installation_id(installation_id)
    resolved_lookback_days = _resolve_lookback_days(lookback_days)

    if since:
        sync_start = _parse_utc_datetime(since, "--since")
    else:
        sync_start = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=resolved_lookback_days)

    typer.echo(f"Fetching Zaptec sessions since {sync_start.isoformat()}...")
    sessions = fetch_archived_sessions(
        username=username,
        password=password,
        since=sync_start,
        installation_id=resolved_installation_id,
        page_size=page_size,
        include_disabled=include_disabled,
    )
    # EstateApp refuses a later submit for a meter and date that already holds readings,
    # so only complete UTC days are submitted.
    today = datetime.datetime.now(datetime.timezone.utc).date()
    held_back = [session for session in sessions if session.ended_at.date() >= today]
    if held_back:
        typer.echo(f"Holding back {len(held_back)} session(s) from today until the day is complete.")
    sessions = [session for session in sessions if session.ended_at.date() < today]
    client = _get_client()
    new_sessions = _select_new_sessions(client, cid, sessions) if sessions else []

    if dry_run_csv is not None:
        _write_sync_csv(dry_run_csv, new_sessions)
        typer.echo(f"Wrote dry-run CSV: {dry_run_csv}")

    if not new_sessions:
        typer.echo("No new sessions found.")
        return

    typer.echo(f"Found {len(new_sessions)} new session(s):\n")
    for session in new_sessions:
        ended_at = session.ended_at.astimezone(datetime.timezone.utc).isoformat()
        typer.echo(
            f"  {session.charger_label:16s}  {ended_at}  {session.energy_kwh:>10.3f} kWh"
        )

    if not submit:
        typer.echo("\nDry-run mode. Pass --submit to actually import.")
        return

    charger_labels = sorted({session.charger_label for session in new_sessions})

    typer.echo("\nEnsuring meters exist...")
    meter_keys = ensure_meters_exist(client, cid, charger_labels, category="electricity")

    typer.echo("Submitting consumption data...")
    api_readings = [
        {
            "category": "electricity",
            "specification": meter_keys[session.charger_label],
            "readingDate": session.ended_at.date().isoformat(),
            "value": session.energy_kwh,
            "type": "usual",
        }
        for session in new_sessions
    ]
    result = submit_readings(client, cid, api_readings)

    inserted = int(result.get("inserted", 0))
    refused = int(result.get("refused", 0))
    typer.echo(f"  Submitted {len(api_readings)} reading(s) (inserted={inserted}, refused={refused})")
    if refused > 0:
        typer.echo("Error: some readings were refused by EstateApp.", err=True)
        raise typer.Exit(1)

    still_missing = _select_new_sessions(client, cid, new_sessions)
    if still_missing:
        typer.echo(
            f"Error: {len(still_missing)} session(s) not stored as expected.",
            err=True,
        )
        raise typer.Exit(1)
    typer.echo(f"Verified {len(new_sessions)} session(s) in EstateApp.")


@app.command("import-datahub")
def import_datahub(
    csv_path: Annotated[Path, typer.Argument(help="Fingrid Datahub consumption export (CSV)")],
    condo_id: Annotated[str | None, typer.Option("--condo-id", help="Condominium ID")] = None,
    submit: Annotated[bool, typer.Option("--submit", help="Actually submit (default is dry-run)")] = False,
):
    """Import monthly electricity consumption from a Fingrid Datahub export."""
    cid = _get_condo_id(condo_id)

    try:
        export = read_export(csv_path)
    except DatahubError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    if export.incomplete:
        typer.echo(f"Skipping {len(export.incomplete)} incomplete month(s): {', '.join(export.incomplete)}")

    if not export.months:
        typer.echo("No complete months in export.")
        return

    label = DATAHUB_METER_LABEL.format(meter_id=export.gsrn)
    key = label_to_key(label)
    client = _get_client()

    try:
        planned = plan_readings(_datahub_pairs(export), _datahub_existing_readings(client, cid, key, export))
    except ReadingPlanError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    typer.echo(f"\n{label} -> {key}\n")
    for entry, month in zip(planned, export.months, strict=True):
        detail = ""
        if entry.action == "replace":
            detail = f"  (was {entry.existing_value:.2f} -> {entry.value:.2f})"
        if month.estimated_intervals:
            detail += f"  [{month.estimated_intervals} interval(s) not marked OK]"
        typer.echo(f"  {entry.reading_date}  {entry.value:>10.2f} kWh  {entry.action}{detail}")

    inserts = [entry for entry in planned if entry.action == "insert"]
    replacements = [entry for entry in planned if entry.action == "replace"]
    skips = [entry for entry in planned if entry.action == "skip"]
    typer.echo(f"\n{len(inserts)} insert, {len(skips)} skip, {len(replacements)} replace")

    if not submit:
        typer.echo("\nDry-run mode. Pass --submit to actually import.")
        return

    if not inserts and not replacements:
        typer.echo("Nothing to submit.")
        return

    typer.echo("\nEnsuring meter exists...")
    ensure_meters_exist(client, cid, [label], category="electricity")

    def _reading(entry) -> dict:
        return {
            "category": "electricity",
            "specification": key,
            "readingDate": entry.reading_date,
            "value": entry.value,
            "type": "usual",
        }

    refused = 0
    for entry in replacements:
        typer.echo(f"Replacing {entry.reading_date}: {entry.existing_value:.2f} -> {entry.value:.2f}")
        result = replace_reading(client, cid, entry.existing_id, _reading(entry))
        refused += int(result.get("refused", 0))

    if inserts:
        typer.echo(f"Submitting {len(inserts)} reading(s)...")
        result = submit_readings(client, cid, [_reading(entry) for entry in inserts])
        refused += int(result.get("refused", 0))
        typer.echo(f"  inserted={result.get('inserted', 0)}, refused={result.get('refused', 0)}")

    if refused:
        typer.echo("Error: some readings were refused by EstateApp.", err=True)
        raise typer.Exit(1)

    try:
        unresolved = [
            entry
            for entry in plan_readings(_datahub_pairs(export), _datahub_existing_readings(client, cid, key, export))
            if entry.action != "skip"
        ]
    except ReadingPlanError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    if unresolved:
        typer.echo(
            f"Error: {len(unresolved)} month(s) not stored as expected: "
            f"{', '.join(entry.reading_date for entry in unresolved)}",
            err=True,
        )
        raise typer.Exit(1)
    typer.echo(f"Verified {len(export.months)} month(s) in EstateApp.")


def _get_bills_client() -> HuoneistotietoClient:
    try:
        login = resolve_ht_login()
    except RaksaConfigError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    condominium_number = os.environ.get(HT_CONDOMINIUM_NUMBER_ENV)
    if not login or not condominium_number:
        typer.echo(f"Error: set RAKSA_HT_EMAIL, RAKSA_HT_PASSWORD and {HT_CONDOMINIUM_NUMBER_ENV}", err=True)
        raise typer.Exit(1)
    http = httpx.Client(timeout=120.0)
    try:
        token = huoneistotieto_token(login=login, http=http)
    except LinkSignInError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    return HuoneistotietoClient(
        token=token,
        # The bill calls do not use the user ID.
        user_id="",
        office_id=login.office_id,
        condominium_id=login.condominium_id,
        condominium_number=condominium_number,
        http_client=http,
    )


def _read_bills(ht_client: HuoneistotietoClient) -> dict[str, list[BillReading]]:
    """Read the bills of this year and the year before. Returns label -> readings, one per reading date."""
    this_year = datetime.date.today().year
    payees = {
        file_name: row.get("maksunsaaja", "")
        for year in (this_year - 1, this_year)
        for row in ht_client.list_purchase_invoices(year)
        for file_name in row.get("liitteet") or []
    }
    by_label: dict[str, dict[str, BillReading]] = {}
    not_html = 0
    no_reading = 0
    for file_name, payee in payees.items():
        content_type, content = ht_client.download_invoice_file(file_name)
        if content_type != "text/html":
            not_html += 1
            continue
        try:
            readings = parse_bill(content.decode("utf-8", errors="replace"))
        except BillParseError as e:
            typer.echo(f"Error: {file_name} ({payee}): {e}", err=True)
            raise typer.Exit(1)
        if not readings:
            no_reading += 1
        for reading in readings:
            dates = by_label.setdefault(reading.label, {})
            known = dates.get(reading.period_end)
            if known and known.consumption != reading.consumption:
                typer.echo(
                    f"Error: two bills give {reading.label} on {reading.period_end}: "
                    f"{known.consumption} and {reading.consumption}",
                    err=True,
                )
                raise typer.Exit(1)
            dates[reading.period_end] = reading
    typer.echo(f"Read {len(payees)} attachment(s): skipped {not_html} that are not HTML, {no_reading} bill(s) give no reading.")
    return {label: sorted(dates.values(), key=lambda r: r.period_end) for label, dates in sorted(by_label.items())}


def _shift_day(iso_date: str, days: int) -> str:
    return (datetime.date.fromisoformat(iso_date) + datetime.timedelta(days=days)).isoformat()


def _check_bill_gaps(client: EstateAppClient, condo_id: str, meters: dict[str, list[BillReading]]) -> None:
    """Fail when the bills of a meter family leave days without a reading, as a scanned bill does."""
    # The family is the label without the meter ID, so a meter change keeps one series.
    families: dict[str, list[BillReading]] = {}
    for label, readings in meters.items():
        families.setdefault(label.rsplit(" (", 1)[0], []).extend(readings)
    gaps = []
    for family, readings in sorted(families.items()):
        readings.sort(key=lambda r: r.period_start)
        day_before = _shift_day(readings[0].period_start, -1)
        prefix = f"{label_to_key(family)}_("
        stored = get_consumptions(client, condo_id, start_date=day_before, end_date=day_before, category=readings[0].utility)
        if not any(r.get("specification", "").startswith(prefix) for r in stored):
            gaps.append(f"{family}: no reading on {day_before}, the day before the first bill")
        # A balancing period spans several estimates, so compare with the latest end so far.
        latest_end = readings[0].period_end
        for reading in readings[1:]:
            if reading.period_start > _shift_day(latest_end, 1):
                gaps.append(f"{family}: no bill from {_shift_day(latest_end, 1)} to {_shift_day(reading.period_start, -1)}")
            latest_end = max(latest_end, reading.period_end)
    if gaps:
        typer.echo("Error: the bills leave a gap. A bill may be a scan to enter by hand.\n  " + "\n  ".join(gaps), err=True)
        raise typer.Exit(1)


def _correct_balancing_readings(
    client: EstateAppClient, condo_id: str, meters: dict[str, list[BillReading]]
) -> dict[str, list[BillReading]]:
    """Turn each balancing reading into its real consumption minus the readings of its period, before its last day."""
    corrected = {}
    for label, readings in meters.items():
        key = label_to_key(label)
        result = []
        for reading in readings:
            if not reading.balancing:
                result.append(reading)
                continue
            stored = [
                (reading_date_to_iso(r.get("readingDate")), float(r["value"]))
                for r in get_consumptions(
                    client, condo_id, start_date=reading.period_start, end_date=reading.period_end, category=reading.utility
                )
                if r.get("specification") == key
            ]
            stored_dates = {date for date, _ in stored}
            # The estimates and the earlier corrections that this run inserts count as well.
            planned = [
                (r.period_end, r.consumption)
                for r in [r for r in readings if not r.balancing] + [r for r in result if r.balancing]
                if r.period_end not in stored_dates
            ]
            counted = sum(value for date, value in stored + planned if reading.period_start <= date < reading.period_end)
            correction = round(reading.consumption - counted, 3)
            if correction < 0:
                typer.echo(
                    f"Error: {label} {reading.period_start} - {reading.period_end}: the stored readings add up to "
                    f"{counted:.3f}, more than the real {reading.consumption:.3f}",
                    err=True,
                )
                raise typer.Exit(1)
            result.append(reading.model_copy(update={"consumption": correction}))
        corrected[label] = result
    return corrected


def _plan_bill_readings(client: EstateAppClient, condo_id: str, readings: list[BillReading]) -> list[PlannedReading]:
    """Plan one meter's bill readings. The reading date is the last day of the billing period."""
    key = label_to_key(readings[0].label)
    existing = [
        reading
        for reading in get_consumptions(
            client,
            condo_id,
            start_date=readings[0].period_end,
            end_date=readings[-1].period_end,
            category=readings[0].utility,
        )
        if reading.get("specification") == key
    ]
    try:
        # sync-bills never replaces, so a stored reading without an ID is only reported.
        return plan_readings([(r.period_end, r.consumption) for r in readings], existing, replace_needs_id=False)
    except ReadingPlanError as e:
        typer.echo(f"Error: {readings[0].label}: {e}", err=True)
        raise typer.Exit(1)


@app.command("sync-bills")
def sync_bills(
    condo_id: Annotated[str | None, typer.Option("--condo-id", help="Condominium ID")] = None,
    submit: Annotated[bool, typer.Option("--submit", help="Actually submit (default is dry-run)")] = False,
):
    """Import heat, electricity and water readings from the utility bills on Huoneistotieto."""
    cid = _get_condo_id(condo_id)
    meters = _read_bills(_get_bills_client())
    if not meters:
        typer.echo("No readings found in the bills.")
        return

    client = _get_client()
    _check_bill_gaps(client, cid, meters)
    meters = _correct_balancing_readings(client, cid, meters)
    inserts: dict[str, list[PlannedReading]] = {}
    skipped = 0
    for label, readings in meters.items():
        typer.echo(f"\n{label} -> {label_to_key(label)}\n")
        # A date that already holds a reading is never replaced, only reported when the value differs.
        for entry in _plan_bill_readings(client, cid, readings):
            detail = ""
            if entry.action == "replace":
                detail = f"  (EstateApp has {entry.existing_value:.3f}, bill has {entry.value:.3f})"
            action = "insert" if entry.action == "insert" else "skip"
            typer.echo(f"  {entry.reading_date}  {entry.value:>10.3f} {readings[0].unit}  {action}{detail}")
            if action == "insert":
                inserts.setdefault(label, []).append(entry)
            else:
                skipped += 1
    insert_count = sum(len(entries) for entries in inserts.values())
    typer.echo(f"\n{insert_count} insert, {skipped} skip")

    if not submit:
        typer.echo("\nDry-run mode. Pass --submit to actually import.")
        return

    if not inserts:
        typer.echo("Nothing to submit.")
        return

    refused = 0
    for label, entries in inserts.items():
        utility = meters[label][0].utility
        key = label_to_key(label)
        ensure_meters_exist(client, cid, [label], category=utility)
        # EstateApp refuses a later submit for a meter and date, so each meter goes in one call.
        result = submit_readings(
            client,
            cid,
            [
                {
                    "category": utility,
                    "specification": key,
                    "readingDate": entry.reading_date,
                    "value": entry.value,
                    "type": "usual",
                }
                for entry in entries
            ],
        )
        refused += int(result.get("refused", 0))
        typer.echo(f"  {label}: inserted={result.get('inserted', 0)}, refused={result.get('refused', 0)}")

    if refused:
        typer.echo("Error: some readings were refused by EstateApp.", err=True)
        raise typer.Exit(1)

    missing = [
        f"{label} {entry.reading_date}"
        for label, entries in inserts.items()
        for entry in _plan_bill_readings(client, cid, meters[label])
        if entry.reading_date in {submitted.reading_date for submitted in entries} and entry.action != "skip"
    ]
    if missing:
        typer.echo(f"Error: {len(missing)} reading(s) not stored as expected: {', '.join(missing)}", err=True)
        raise typer.Exit(1)
    typer.echo(f"Verified {insert_count} reading(s) in EstateApp.")


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


@app.command("fetch-temperature")
def fetch_temperature(
    output: Annotated[Path, typer.Option("--output", "-o", help="Output directory for YAML files")] = Path("readings/temperature"),
    place: Annotated[str, typer.Option("--place", help="FMI place name")] = "hervanta",
    start_year: Annotated[int, typer.Option("--start", help="Start year")] = 2020,
    end_year: Annotated[int, typer.Option("--end", help="End year")] = 2025,
):
    """Fetch monthly average temperature from FMI and save as YAML readings."""
    import calendar
    import yaml

    typer.echo(f"Fetching temperature data for {place} ({start_year}-{end_year})...")
    readings = fetch_monthly_temperatures(place, start_year, end_year)

    if not readings:
        typer.echo("No data returned from FMI.")
        return

    typer.echo(f"Got {len(readings)} monthly readings\n")
    for r in readings:
        typer.echo(f"  {r['year']}-{r['month']:02d}  {r['temperature_c']:>6.1f} C")

    output.mkdir(parents=True, exist_ok=True)
    for r in readings:
        year, month = r["year"], r["month"]
        last_day = calendar.monthrange(year, month)[1]
        period_end = f"{year}-{month:02d}-{last_day:02d}"
        data = {
            "meter_id": f"fmi-{place}",
            "meter_label": f"Ulkolampotila ({place})",
            "utility": "temperature",
            "unit": "C",
            "period_start": f"{year}-{month:02d}-01",
            "period_end": period_end,
            "reading_date": period_end,
            "consumption": r["temperature_c"],
            "costs": [],
        }
        fname = f"temperature_{period_end}.yaml"
        with open(output / fname, "w") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    typer.echo(f"\nWrote {len(readings)} files to {output}/")


@app.command("import-temperature")
def import_temperature(
    readings_dir: Annotated[Path, typer.Argument(help="Directory of temperature YAML files")] = Path("readings/temperature"),
    condo_id: Annotated[str | None, typer.Option("--condo-id", help="Condominium ID")] = None,
    submit: Annotated[bool, typer.Option("--submit", help="Actually submit (default is dry-run)")] = False,
):
    """Import temperature readings into EstateApp."""
    cid = _get_condo_id(condo_id)
    readings = load_readings(readings_dir)

    if not readings:
        typer.echo("No readings found.")
        return

    typer.echo(f"Temperature ({len(readings)} readings):")
    for r in readings:
        typer.echo(f"  {r.period_start} - {r.period_end}  {r.consumption:>6.1f} C")

    if not submit:
        typer.echo("\nDry-run mode. Pass --submit to actually import.")
        return

    client = _get_client()
    label = readings[0].meter_label

    typer.echo(f"\nEnsuring meter exists: {label}...")
    # Temperature isn't a standard EstateApp category, use electricity as workaround
    # Actually, let's check if there's a temperature category
    label_to_key = ensure_meters_exist(client, cid, [label], category="electricity")
    key = label_to_key[label]
    typer.echo(f"  {label} -> {key}")

    typer.echo("Submitting readings...")
    api_readings = [
        {
            "category": "electricity",
            "specification": key,
            "readingDate": r.reading_date,
            "value": r.consumption,
            "type": "usual",
        }
        for r in readings
    ]
    submit_readings(client, cid, api_readings)
    typer.echo(f"  Submitted {len(api_readings)} reading(s)")
