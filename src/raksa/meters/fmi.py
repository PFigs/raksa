"""Fetch monthly average temperature from the Finnish Meteorological Institute open data API."""
import re
from xml.etree import ElementTree

import httpx

FMI_WFS_URL = "https://opendata.fmi.fi/wfs"
STORED_QUERY = "fmi::observations::weather::monthly::timevaluepair"
PARAMETER = "tmon"  # monthly mean temperature


def fetch_monthly_temperatures(
    place: str,
    start_year: int,
    end_year: int,
) -> list[dict]:
    """Fetch monthly average temperatures from FMI for a place and year range.

    Returns list of dicts with keys: year, month, temperature_c, place.
    """
    all_readings = []
    # FMI limits response size, so fetch year by year
    for year in range(start_year, end_year + 1):
        params = {
            "service": "WFS",
            "version": "2.0.0",
            "request": "getFeature",
            "storedquery_id": STORED_QUERY,
            "place": place,
            "starttime": f"{year}-01-01",
            "endtime": f"{year}-12-31",
            "parameters": PARAMETER,
        }
        resp = httpx.get(FMI_WFS_URL, params=params, timeout=30)
        resp.raise_for_status()
        readings = _parse_response(resp.text, place)
        all_readings.extend(readings)

    return all_readings


def _parse_response(xml_text: str, place: str) -> list[dict]:
    """Parse FMI WFS XML response into temperature readings."""
    readings = []
    # Extract time-value pairs from the XML
    # The XML uses namespaces but we can parse with simple regex for reliability
    times = re.findall(r"<wml2:time>(.*?)</wml2:time>", xml_text)
    values = re.findall(r"<wml2:value>(.*?)</wml2:value>", xml_text)

    for time_str, value_str in zip(times, values):
        if value_str == "NaN":
            continue
        year = int(time_str[:4])
        month = int(time_str[5:7])
        temperature = float(value_str)
        readings.append({
            "year": year,
            "month": month,
            "temperature_c": temperature,
            "place": place,
        })

    return readings
