"""Read heat, electricity and water consumption from utility bills: HTML e-invoices and PDF bills."""
import datetime
import html
import io
import logging
import re

import pypdf
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


# The PDF bills that sync-bills reads, by supplier: the patterns of the meter ID and of the consumption with its unit.
# A supplier without patterns sends readings in PDFs that no pattern reads yet.
PDF_SUPPLIERS: dict[str, tuple[str, str] | None] = {
    "Tampereen Energia Oy": (r"Mittarin numero: (\d+)", r"Laskutettu määrä: (\d[\d ]*,\d+) (MWh)"),
    "Tampereen Energia Sähköverkko Oy": (r"Käyttöpaikka (\d{18})", r"KULUTUSLASKU \S+ - \S+ \( (\d[\d ]*,\d+) (kWh) \)"),
    "Tampereen Vesi Oy": None,
}
PDF_PERIOD = r"(?:KULUTUSLASKU|ARVIOLASKU) (\d{1,2}\.\d{1,2}\.\d{4}) - (\d{1,2}\.\d{1,2}\.\d{4})"

# pypdf warns about every font it cannot fully decode; the text it reads is still complete.
logging.getLogger("pypdf").setLevel(logging.ERROR)


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
    meter_line = UTILITIES[unit][1]

    meter_ids = {lines[i + 1] for i, line in enumerate(lines[:-1]) if line == meter_line}
    if len(meter_ids) != 1:
        raise BillParseError(f"expected one value after '{meter_line}', found {sorted(meter_ids)}")
    return _readings(
        meter_id=meter_ids.pop(),
        start=start,
        end=end,
        consumption=consumption,
        unit=unit,
        balancing=balancing,
    )


def _readings(meter_id: str, start: str, end: str, consumption: float, unit: str, balancing: bool) -> list[BillReading]:
    utility, _, labels = UTILITIES[unit]
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


def pdf_text(content: bytes) -> str:
    return " ".join(page.extract_text() for page in pypdf.PdfReader(io.BytesIO(content)).pages)


def _one_match(pattern: str, text: str, what: str):
    matches = set(re.findall(pattern, text))
    if len(matches) != 1:
        raise BillParseError(f"expected one {what}, found {sorted(matches)}")
    return matches.pop()


def parse_pdf_bill(supplier: str, text: str) -> list[BillReading]:
    """Return the readings of the PDF bill of a utility supplier, and none for any other supplier."""
    if supplier not in PDF_SUPPLIERS:
        return []
    patterns = PDF_SUPPLIERS[supplier]
    if patterns is None:
        raise BillParseError(f"no reader for the PDF bills of {supplier}: add its patterns to PDF_SUPPLIERS")
    meter_pattern, consumption_pattern = patterns
    text = re.sub(r"\s+", " ", text)
    start, end = _one_match(PDF_PERIOD, text, "billing period")
    consumption, unit = _one_match(consumption_pattern, text, "consumption")
    return _readings(
        meter_id=_one_match(meter_pattern, text, "meter ID"),
        start=start,
        end=end,
        consumption=float(consumption.replace(" ", "").replace(",", ".")),
        unit=unit,
        balancing=False,
    )
