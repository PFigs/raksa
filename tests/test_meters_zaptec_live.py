import datetime
from urllib.parse import parse_qs, urlparse

from typer.testing import CliRunner

from raksa.cli import app
from raksa.commands import meters as meters_cmd
from raksa.meters.estateapp import reading_date_to_iso
from raksa.meters.zaptec_live import (
    ZaptecSession,
    _build_archived_sessions_path,
    normalize_archived_sessions,
)

runner = CliRunner()


def _session(
    session_id: str,
    charger_label: str,
    ended_at: str,
    energy_kwh: float,
) -> ZaptecSession:
    return ZaptecSession(
        session_id=session_id,
        charger_label=charger_label,
        ended_at=datetime.datetime.fromisoformat(ended_at),
        energy_kwh=energy_kwh,
    )


def _reading(specification: str, reading_date, value: float) -> dict:
    return {"specification": specification, "readingDate": reading_date, "value": value}


def _stub_sync(monkeypatch, sessions, existing=(), submit_result=None) -> dict:
    """Stub Zaptec fetch plus EstateApp read/write for the sync command."""
    monkeypatch.setenv("RAKSA_ZAPTEC_USERNAME", "zap-user")
    monkeypatch.setenv("RAKSA_ZAPTEC_PASSWORD", "zap-pass")
    monkeypatch.setenv("RAKSA_ZAPTEC_INSTALLATION_ID", "inst-1")

    calls: dict = {"submitted": None, "window": None}

    def _get_consumptions(_client, _condo_id, start_date, end_date, **_kwargs):
        calls["window"] = (start_date, end_date)
        return list(existing)

    def _submit_readings(_client, _condo_id, readings):
        calls["submitted"] = readings
        return submit_result or {"inserted": len(readings), "refused": 0}

    monkeypatch.setattr(meters_cmd, "fetch_archived_sessions", lambda **_: list(sessions))
    monkeypatch.setattr(meters_cmd, "_get_client", lambda: object())
    monkeypatch.setattr(meters_cmd, "get_consumptions", _get_consumptions)
    monkeypatch.setattr(
        meters_cmd,
        "ensure_meters_exist",
        lambda _client, _cid, labels, **_kwargs: {
            label: meters_cmd.label_to_key(label) for label in labels
        },
    )
    monkeypatch.setattr(meters_cmd, "submit_readings", _submit_readings)
    return calls


def _run(*extra_args):
    return runner.invoke(app, ["meters", "sync-zaptec", "--condo-id", "condo-1", *extra_args])


def test_build_archived_sessions_path_uses_required_installation_scope_and_time_range():
    path = _build_archived_sessions_path(
        from_datetime=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc),
        to_datetime=datetime.datetime(2026, 8, 1, tzinfo=datetime.timezone.utc),
        page_size=100,
        installation_id="inst-1",
        cursor="next-cursor",
        include_disabled=False,
    )

    parsed = urlparse(path)
    query = parse_qs(parsed.query)
    assert parsed.path == "sessions/archived"
    assert query["From"] == ["2026-01-01T00:00:00+00:00"]
    assert query["To"] == ["2026-08-01T00:00:00+00:00"]
    assert query["InstallationId"] == ["inst-1"]
    assert query["PageSize"] == ["100"]
    assert query["Cursor"] == ["next-cursor"]


def test_normalize_archived_sessions_filters_and_maps():
    data = [
        {
            "Id": "s1",
            "ChargerId": "c1",
            "EndDateTime": "2026-08-01T10:00:00Z",
            "Energy": 11.25,
        },
        {
            "Id": "s2",
            "ChargerName": "AP 02",
            "EndedAt": "2026-08-01T11:00:00+00:00",
            "ConsumedEnergyKwh": "5.1",
        },
        {
            "id": "s3",
            "chargerId": "c3",
            "endDateTime": "2026-08-01T12:00:00+00:00",
            "energy": 3.75,
            "deviceName": "AP 03",
        },
        {
            "Id": "s1",
            "ChargerId": "c1",
            "EndDateTime": "2026-08-01T10:00:00Z",
            "Energy": 11.25,
        },
        {
            "Id": "missing-energy",
            "EndDateTime": "2026-08-01T12:00:00Z",
        },
    ]

    sessions = normalize_archived_sessions(data, {"c1": "AP 01"})

    assert [session.session_id for session in sessions] == ["s1", "s2", "s3"]
    assert sessions[0].charger_label == "AP 01"
    assert sessions[0].energy_kwh == 11.25
    assert sessions[1].charger_label == "AP 02"
    assert sessions[1].energy_kwh == 5.1
    assert sessions[2].charger_label == "AP 03"
    assert sessions[2].energy_kwh == 3.75


def test_reading_date_to_iso_accepts_epoch_millis_and_iso_strings():
    epoch_ms = int(datetime.datetime(2026, 8, 2, tzinfo=datetime.timezone.utc).timestamp() * 1000)

    assert reading_date_to_iso(epoch_ms) == "2026-08-02"
    assert reading_date_to_iso(str(epoch_ms)) == "2026-08-02"
    assert reading_date_to_iso("2026-08-02") == "2026-08-02"
    assert reading_date_to_iso("2026-08-02T11:00:00Z") == "2026-08-02"
    assert reading_date_to_iso(None) is None
    assert reading_date_to_iso("not-a-date") is None


def test_sync_zaptec_skips_sessions_already_in_estateapp(monkeypatch):
    calls = _stub_sync(
        monkeypatch,
        sessions=[
            _session("s1", "AP 01", "2026-08-02T10:00:00+00:00", 7.5),
            _session("s2", "AP 02", "2026-08-03T11:00:00+00:00", 3.25),
        ],
        existing=[_reading("ap_01", "2026-08-02", 7.5)],
    )

    result = _run("--submit")

    assert result.exit_code == 0
    assert calls["window"] == ("2026-08-02", "2026-08-03")
    assert [reading["specification"] for reading in calls["submitted"]] == ["ap_02"]


def test_sync_zaptec_imports_repeat_session_not_yet_in_estateapp(monkeypatch):
    calls = _stub_sync(
        monkeypatch,
        sessions=[
            _session("s1", "AP 01", "2026-08-02T10:00:00+00:00", 7.5),
            _session("s2", "AP 01", "2026-08-02T18:00:00+00:00", 7.5),
        ],
        existing=[_reading("ap_01", "2026-08-02", 7.5)],
    )

    result = _run("--submit")

    assert result.exit_code == 0
    assert calls["submitted"] == [
        {
            "category": "electricity",
            "specification": "ap_01",
            "readingDate": "2026-08-02",
            "value": 7.5,
            "type": "usual",
        }
    ]


def test_sync_zaptec_reports_nothing_when_all_sessions_already_imported(monkeypatch):
    epoch_ms = int(datetime.datetime(2026, 8, 2, tzinfo=datetime.timezone.utc).timestamp() * 1000)
    calls = _stub_sync(
        monkeypatch,
        sessions=[_session("s1", "AP 01", "2026-08-02T10:00:00+00:00", 7.5)],
        existing=[_reading("ap_01", epoch_ms, 7.5)],
    )

    result = _run("--submit")

    assert result.exit_code == 0
    assert "No new sessions found." in result.output
    assert calls["submitted"] is None


def test_sync_zaptec_writes_dry_run_csv(tmp_path, monkeypatch):
    csv_file = tmp_path / "dry-run.csv"
    calls = _stub_sync(
        monkeypatch,
        sessions=[
            _session("s1", "AP 01", "2026-08-02T10:00:00+00:00", 7.5),
            _session("s2", "AP 02", "2026-08-02T11:00:00+00:00", 3.25),
        ],
    )

    result = _run("--dry-run-csv", str(csv_file))

    assert result.exit_code == 0
    assert "Wrote dry-run CSV:" in result.output
    assert calls["submitted"] is None
    assert csv_file.read_text().splitlines() == [
        "date,meter,kwh",
        "2026-08-02,AP 01,7.500",
        "2026-08-02,AP 02,3.250",
    ]


def test_sync_zaptec_writes_empty_dry_run_csv_for_no_sessions(tmp_path, monkeypatch):
    csv_file = tmp_path / "dry-run.csv"
    calls = _stub_sync(monkeypatch, sessions=[])

    result = _run("--dry-run-csv", str(csv_file))

    assert result.exit_code == 0
    assert "No new sessions found." in result.output
    assert calls["window"] is None
    assert csv_file.read_text().splitlines() == ["date,meter,kwh"]


def test_sync_zaptec_submit_sends_all_new_sessions(monkeypatch):
    calls = _stub_sync(
        monkeypatch,
        sessions=[
            _session("s1", "AP 01", "2026-08-02T10:00:00+00:00", 7.5),
            _session("s2", "AP 02", "2026-08-02T11:00:00+00:00", 3.25),
        ],
    )

    result = _run("--submit")

    assert result.exit_code == 0
    assert len(calls["submitted"]) == 2
    assert calls["submitted"][0]["readingDate"] == "2026-08-02"


def test_sync_zaptec_refused_readings_fail_the_run(monkeypatch):
    _stub_sync(
        monkeypatch,
        sessions=[_session("s1", "AP 01", "2026-08-02T10:00:00+00:00", 7.5)],
        submit_result={"inserted": 0, "refused": 1},
    )

    result = _run("--submit")

    assert result.exit_code == 1
    assert "refused" in result.output


def test_sync_zaptec_requires_installation_id(monkeypatch):
    monkeypatch.setenv("RAKSA_ZAPTEC_USERNAME", "zap-user")
    monkeypatch.setenv("RAKSA_ZAPTEC_PASSWORD", "zap-pass")
    monkeypatch.delenv("RAKSA_ZAPTEC_INSTALLATION_ID", raising=False)
    monkeypatch.delenv("ZAPTEC_INSTALLATION_ID", raising=False)

    result = _run()

    assert result.exit_code == 1
    assert "pass --installation-id" in result.output
