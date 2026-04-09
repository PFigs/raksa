# Extract consumption readings from utility invoices

Given a directory of invoice PDFs and a utility type, read the PDFs and extract consumption data into a common YAML format.

## Usage

```
/extract-consumption <invoices-path> <utility> [--output <dir>]
```

Arguments:
- `invoices-path`: directory containing invoice PDFs (hive structure: `year=*/month=*/*.pdf`)
- `utility`: one of `electricity`, `water`, `heat`
- `--output`: where to save the YAML readings (default: `readings/<utility>/`)

## Process

1. Find all PDF files under the given path
2. Filter to invoices matching the utility type (by reading the PDFs)
3. For each invoice, extract the consumption data
4. Save each reading as a YAML file in the output directory
5. Report a summary of what was extracted

## How to identify utility invoices

Do NOT rely on provider names -- providers can change. Instead, identify by content:

- **electricity**: look for kWh consumption figures, "sähkö", "energiamaksu", "kulutuslasku" with kWh
- **water**: look for m3 consumption, "vesi", "jätevesi", "veden käyttömaksu"
- **heat**: look for MWh consumption, "kaukolämpö", "lämpö", "tehomaksu" with MWh

Some invoices only show cost (no consumption). Skip those -- we only want invoices with actual meter readings or consumption figures.

For electricity specifically: the grid operator (sähköverkko/siirto) invoice typically has the kWh figure. The electricity supplier invoice may not. If both exist for the same period, use the one with consumption and attach costs from both.

## Reading PDFs

Read each PDF using the Read tool. Most Finnish utility invoices have:
- Page 1: summary with billing period and total
- Page 2: detailed breakdown with consumption figures

Always read enough pages to find the consumption data.

## Extracting data

From each invoice, extract:
- **meter_id**: the physical meter number or käyttöpaikka identifier
- **period_start** and **period_end**: the billing period (DD.MM.YYYY format on invoices, convert to YYYY-MM-DD)
- **consumption**: the numeric value in the invoice's unit
- **unit**: kWh, MWh, or m3
- **cost information**: provider name, amount, invoice number

Water invoices may have multiple sub-periods within one invoice. Extract each sub-period as a separate reading.

## Output format

Each reading is a YAML file named `<utility>_<period_end>.yaml` (e.g. `electricity_2024-09-30.yaml`).

If multiple readings exist for the same period end date (e.g. water with sub-periods), append a suffix: `water_2024-09-30_1.yaml`.

```yaml
meter_id: "643007572070390203"
meter_label: "Common electricity"
utility: electricity
unit: kWh
period_start: "2024-09-01"
period_end: "2024-09-30"
reading_date: "2024-09-30"
consumption: 420.940
costs:
  - provider: "Tampereen Energia Sähköverkko Oy"
    amount_eur: 85.04
    type: distribution
    invoice_number: "5002201899"
    source_file: "2024-10-03_Tampereen_Energia_Sähköverkko_Oy_5002201899.pdf"
  - provider: "Fortum"
    amount_eur: 39.07
    type: supply
    invoice_number: "11028251526"
    source_file: "2024-10-14_Fortum_11028251526.pdf"
```

### Field descriptions

| Field | Required | Description |
|-------|----------|-------------|
| meter_id | yes | Physical meter number or metering point ID from the invoice |
| meter_label | yes | Human-readable label in English: "Common electricity", "District heating", "Water" |
| utility | yes | `electricity`, `water`, or `heat` |
| unit | yes | `kWh`, `MWh`, or `m3` |
| period_start | yes | Start of billing period, ISO date |
| period_end | yes | End of billing period, ISO date |
| reading_date | yes | Same as period_end (used for EstateApp import) |
| consumption | yes | Numeric consumption value in the stated unit |
| costs | no | List of cost entries from invoices covering this period |
| costs[].provider | yes | Company name as printed on the invoice |
| costs[].amount_eur | yes | Total invoice amount including VAT |
| costs[].type | yes | `distribution`, `supply`, `base`, or `usage` |
| costs[].invoice_number | yes | Invoice number for traceability |
| costs[].source_file | yes | Filename of the source PDF |

### Matching multiple invoices to one reading

For electricity, the grid operator and supplier invoice the same consumption separately. Match them by:
- Same käyttöpaikka / metering point
- Overlapping or identical billing period

Combine into one reading with multiple cost entries.

## Example invocations

Extract all electricity readings:
```
/extract-consumption /path/to/invoices electricity
```

Extract water readings from 2024 only:
```
/extract-consumption /path/to/invoices/year=2024 water
```

Extract heating readings to a specific output:
```
/extract-consumption /path/to/invoices heat --output ./heat_readings
```

## Important notes

- Finnish invoices use comma as decimal separator (12,225 MWh = 12.225 MWh in the YAML)
- Finnish date format is DD.MM.YYYY -- convert to YYYY-MM-DD in output
- Amounts on invoices include VAT unless stated otherwise -- use the total including VAT
- If you cannot determine the consumption from a PDF, skip it and note it in the summary
- Provider names should be copied exactly as they appear on the invoice
- The meter_label should be consistent across all readings of the same utility type
