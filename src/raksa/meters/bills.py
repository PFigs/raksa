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
    # The real consumption of the whole period, from a water balancing bill.
    balancing: bool = False


def _text_lines(page: str) -> list[str]:
    page = re.sub(r"(?is)<(script|style).*?</\1>", "", page)
    page = re.sub(r"(?i)</(tr|p|div|br|td|th)[^>]*>", "\n", page)
    text = html.unescape(re.sub(r"<[^>]+>", "", page))
    lines = (re.sub(r"\s+", " ", line).strip() for line in text.split("\n"))
    return [line for line in lines if line]


def _quantity(line: str) -> tuple[float, str] | None:
    match = QUANTITY_LINE.fullmatch(line)
    return (float(match[1].replace(" ", "").replace(",", ".")), match[2]) if match else None


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
    balancing = kind == "TASAUSLASKU"
    if balancing:
        # The other quantity rows of a balancing bill split the period by price.
        quantities = {_quantity(lines[i + 1]) for i, line in enumerate(lines[:-1]) if line == "Kulutus:"}
        # Only the water balancing bill carries a meter reading; the others stay skipped.
        if not any(quantity and quantity[1] == "m3" for quantity in quantities):
            return []
    else:
        quantities = {quantity for line in lines[index + 1:] if (quantity := _quantity(line))}
    if len(quantities) != 1 or None in quantities:
        raise BillParseError(f"expected one consumption after '{period[0]}', found {sorted(quantities, key=str)}")
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
            balancing=balancing,
        )
        for label in labels
    ]
