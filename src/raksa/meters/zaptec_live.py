"""Live Zaptec session fetch and normalization."""

import asyncio
import datetime
from urllib.parse import urlencode

from pydantic import BaseModel
from pyzaptec import Zaptec


class ZaptecSession(BaseModel):
    session_id: str
    charger_label: str
    ended_at: datetime.datetime
    energy_kwh: float


def _to_utc(value: datetime.datetime) -> datetime.datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime.timezone.utc)
    return value.astimezone(datetime.timezone.utc)


def _parse_datetime(value: str) -> datetime.datetime:
    parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    return _to_utc(parsed)


def _pick(item: dict, keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _pick_float(item: dict, keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = item.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def normalize_archived_sessions(
    data: list[dict],
    charger_names_by_id: dict[str, str],
) -> list[ZaptecSession]:
    sessions: list[ZaptecSession] = []
    for item in data:
        session_id = _pick(item, ("Id", "id", "SessionId", "sessionId"))
        ended_raw = _pick(item, ("EndDateTime", "endDateTime", "EndedAt", "endedAt"))
        if not session_id or not ended_raw:
            continue

        charger_id = _pick(item, ("ChargerId", "chargerId"))
        charger_label = _pick(item, ("ChargerName", "chargerName", "DeviceName", "deviceName"))
        if not charger_label and charger_id:
            charger_label = charger_names_by_id.get(charger_id)
        if not charger_label:
            charger_label = charger_id or "Unknown charger"

        energy_kwh = _pick_float(
            item,
            (
                "Energy",
                "energy",
                "EnergyKwh",
                "ConsumedEnergyKwh",
                "TotalChargePowerSession",
                "totalChargePowerSession",
            ),
        )
        if energy_kwh is None:
            continue

        try:
            ended_at = _parse_datetime(ended_raw)
        except ValueError:
            continue

        sessions.append(
            ZaptecSession(
                session_id=session_id,
                charger_label=charger_label,
                ended_at=ended_at,
                energy_kwh=energy_kwh,
            )
        )

    deduped: dict[str, ZaptecSession] = {}
    for session in sessions:
        deduped[session.session_id] = session
    return sorted(
        deduped.values(),
        key=lambda item: (item.ended_at, item.session_id),
    )


def _build_archived_sessions_path(
    from_datetime: datetime.datetime,
    to_datetime: datetime.datetime,
    page_size: int,
    installation_id: str,
    cursor: str | None,
    include_disabled: bool,
) -> str:
    query = {
        "From": _to_utc(from_datetime).isoformat(),
        "To": _to_utc(to_datetime).isoformat(),
        "InstallationId": installation_id,
        "PageSize": page_size,
    }
    if cursor:
        query["Cursor"] = cursor
    if include_disabled:
        query["IncludeDisabled"] = "true"
    return f"sessions/archived?{urlencode(query)}"


async def _fetch_archived_sessions(
    username: str,
    password: str,
    since: datetime.datetime,
    installation_id: str,
    page_size: int,
    include_disabled: bool,
) -> list[ZaptecSession]:
    all_sessions: list[ZaptecSession] = []
    from_datetime = _to_utc(since)
    to_datetime = datetime.datetime.now(datetime.timezone.utc)
    if to_datetime <= from_datetime:
        to_datetime = from_datetime + datetime.timedelta(seconds=1)

    async with Zaptec(username=username, password=password) as zaptec:
        await zaptec.login()
        await zaptec.build()
        charger_names_by_id = {
            charger.id: str(charger.get("Name") or charger.id)
            for charger in zaptec.chargers
        }

        cursor: str | None = None
        while True:
            response = await zaptec.request(
                _build_archived_sessions_path(
                    from_datetime=from_datetime,
                    to_datetime=to_datetime,
                    page_size=page_size,
                    installation_id=installation_id,
                    cursor=cursor,
                    include_disabled=include_disabled,
                )
            )
            page_data = (
                response.get("sessions")
                or response.get("Sessions")
                or response.get("Data")
                or response.get("data")
                or []
            )
            if not page_data:
                break

            sessions = normalize_archived_sessions(page_data, charger_names_by_id)
            all_sessions.extend(
                [
                    session
                    for session in sessions
                    if from_datetime <= session.ended_at < to_datetime
                ]
            )

            has_more = bool(response.get("hasMore") or response.get("HasMore"))
            if not has_more:
                break

            cursor = response.get("cursor") or response.get("Cursor")
            if not cursor:
                break

    deduped: dict[str, ZaptecSession] = {}
    for session in all_sessions:
        deduped[session.session_id] = session
    return sorted(deduped.values(), key=lambda item: (item.ended_at, item.session_id))


def fetch_archived_sessions(
    username: str,
    password: str,
    since: datetime.datetime,
    installation_id: str,
    page_size: int = 100,
    include_disabled: bool = False,
) -> list[ZaptecSession]:
    return asyncio.run(
        _fetch_archived_sessions(
            username=username,
            password=password,
            since=_to_utc(since),
            installation_id=installation_id,
            page_size=page_size,
            include_disabled=include_disabled,
        )
    )