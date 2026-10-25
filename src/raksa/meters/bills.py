"""Read heat, electricity and water consumption from the HTML e-invoices on Huoneistotieto."""
import datetime
import html
import re

from pydantic import BaseModel

from raksa.meters.datahub import DATAHUB_METER_LABEL

PERIOD_LINE = re.compile(r"(KULUTUSLASKU|ARVIOLASKU|TASAUSLASKU) (\d{1,2}\.\d{1,2}\.\d{4}) - (\d{1,2}\.\d{1,2}\.\d{4})")
QUANTITY_LINE = re.compile(r"(\d[\d ]*,\d+) (kWh|MWh|m3)")

# The unit of the consumption decides the utility, the line that holds the meter ID, and the meter labels.
UTILITIES = {
    "kWh": ("electricity", "Käyttöpaikkatunnus:", [DATAHUB_METER_LABEL]),
    "MWh": ("heat", "Mittarin numero:", ["Kaukolämpö ({meter_id})"]),
    "m3": ("water", "Mittarin numero:", ["Vesi ({meter_id})", "Jätevesi ({meter_id})"]),
}


class BillParseError(Exception):
    pass


class BillReading(BaseModel):
    label: str
    utility: str
    meter_id: str
    period_start: str
    period_end: str
    consumption: float
    unit: str


def _text_lines(page: str) -> list[str]:
    page = re.sub(r"(?is)<(script|style).*?</\1>", "", page)
    page = re.sub(r"(?i)</(tr|p|div|br|td|th)[^>]*>", "\n", page)
    text = html.unescape(re.sub(r"<[^>]+>", "", page))
    lines = (re.sub(r"\s+", " ", line).strip() for line in text.split("\n"))
    return [line for line in lines if line]


def _iso_date(finnish_date: str) -> str:
    return datetime.datetime.strptime(finnish_date, "%d.%m.%Y").date().isoformat()


def parse_bill(page: str) -> list[BillReading]:
    """Return the readings of a consumption or estimate bill, and none for any other bill."""
    lines = _text_lines(page)
    periods = [(index, match) for index, line in enumerate(lines) if (match := PERIOD_LINE.fullmatch(line))]
    if not periods:
        return []
    if len(periods) > 1:
        raise BillParseError(f"expected one billing period, found {[match[0] for _, match in periods]}")
    index, period = periods[0]
    kind, start, end = period.groups()
    # Balancing bills cover periods that the water estimates already hold.
    if kind == "TASAUSLASKU":
        return []

    quantities = {
        (float(match[1].replace(" ", "").replace(",", ".")), match[2])
        for line in lines[index + 1:]
        if (match := QUANTITY_LINE.fullmatch(line))
    }
    if len(quantities) != 1:
        raise BillParseError(f"expected one consumption after '{period[0]}', found {sorted(quantities)}")
    consumption, unit = quantities.pop()
    utility, meter_line, labels = UTILITIES[unit]

    meter_ids = {lines[i + 1] for i, line in enumerate(lines[:-1]) if line == meter_line}
    if len(meter_ids) != 1:
        raise BillParseError(f"expected one value after '{meter_line}', found {sorted(meter_ids)}")
    meter_id = meter_ids.pop()

    return [
        BillReading(
            label=label.format(meter_id=meter_id),
            utility=utility,
            meter_id=meter_id,
            period_start=_iso_date(start),
            period_end=_iso_date(end),
            consumption=consumption,
            unit=unit,
        )
        for label in labels
    ]
