# Datahub Electricity Import

Import the housing company's metered electricity consumption from Fingrid Datahub into EstateApp as
monthly readings, replacing the invoice-derived values currently held for the same meter.

## Module structure

```
src/raksa/
  meters/
    datahub.py         # CSV parse + monthly aggregation
  commands/
    meters.py          # raksa meters import-datahub
```

## CLI command

```
raksa meters import-datahub <csv> [--condo-id ID] [--submit]
```

- `csv` -- path to a Datahub customer portal export
- `--condo-id` -- override `RAKSA_CONDO_ID`
- `--submit` -- execute (dry-run by default, per the other meter commands)

Dry-run output lists each month, its kWh, and the action that would be taken
(`insert` / `skip` / `replace`), plus any month dropped as incomplete.

## Data source

There is no Datahub API for customers. Fingrid states that mechanical retrieval of consumption data
is not available; the customer portal at `oma.datahub.fi` sits behind Suomi.fi strong authentication
and offers a CSV export. The housing company's data requires logging in as a company user rather
than as a private person -- a personal session only exposes that person's own usage points.

Getting the export is therefore manual: log in, open the accounting point's Energy Reporting, pick a
range, click Download information. `raksa` starts from the downloaded file.

The portal's internal endpoint (`POST /_api/GetConsumptionData`, taking `MeteringPointEAN`,
`PeriodStartTS`, `PeriodEndTS`, `ResolutionDuration`, `UnitType`, `ProductType`) was mapped but is
deliberately not used: the session is an HttpOnly cookie that JavaScript cannot read, it dies with
the Suomi.fi session, and it is not a published interface.

## Export format

UTF-8 with BOM, `;` separated, decimal comma, one row per interval:

```
MeteringPointGSRN;Product Type;Resolution;Unit Type;Reading Type;Start Time;Quantity;Quality
643000000000000000;8716867000030;PT15M;kWh;BN01;2025-12-31T22:00:00Z;0,390000;OK
```

- `Start Time` is UTC. `2025-12-31T22:00:00Z` is 1 Jan 2026 00:00 in Helsinki.
- `Resolution` is an ISO 8601 duration. A single export mixes them: a six-year export contains
  24693 `PT1H` rows for the older years and 111488 `PT15M` rows for the newer ones, so one month can
  hold both. Summing is resolution-independent, and coverage-based completeness (below) tolerates the
  switchover; counting expected intervals per month would not.
- `Quantity` is kWh for the interval, not a meter register value.
- `Quality` observed as `OK` throughout six years.

Exporting the point's sales agreement and its grid agreement yields byte-identical files. For a
consumption-only point there is one measured series at the accounting point, which both the retailer
and the DSO bill against; the agreement being viewed does not change it. So bought and transferred
energy need no reconciliation, and either export is the same input.

## Aggregation

Interval quantities are summed into Helsinki-time calendar months. Timestamps are UTC, so both DST
transitions fall out correctly: in the sample, March 2026 has 2972 intervals (2976 - 4, the hour lost
to spring forward) and the only non-15-minute step in the file is that jump.

A month is emitted only when the file covers it completely: the summed duration of the month's
intervals must equal the month's true span in UTC (743 hours for March 2026, 672 for February). This
drops the partial current month (in the sample, August 2026 at 113.74 kWh over 416 intervals) and
also catches a gap in the middle of a month, which comparing only the earliest and latest timestamps
cannot see. Summing durations needs no per-resolution expected-interval count, so it tolerates a file
that mixes `PT1H` and `PT15M` within one month.

Monthly values are rounded to 2 decimals, matching the existing readings.

## EstateApp mapping

| Field | Value |
|-------|-------|
| `category` | `electricity` |
| `specification` | meter key, e.g. `sähkö_yhteinen_(643000000000000000)` |
| `readingDate` | last day of the month, e.g. `2026-02-28` |
| `value` | monthly kWh |
| `type` | `usual` |

The meter already exists as `Sähkö yhteinen (<GSRN>)` with key
`sähkö_yhteinen_(643000000000000000)` and multiplier 1, which is what the existing
`readings/electricity/*.yaml` import produced. The label is derived from the GSRN in the CSV so the
key matches, and `ensure_meters_exist` is reused -- it creates nothing when the meter is there.

## Replace behaviour

Existing readings for the window are read with `get_consumptions` (added for the Zaptec sync), and
each aggregated month is classified:

- no reading for that meter and date -> insert
- reading exists with the same value -> skip
- reading exists with a different value -> replace, metered value wins

Comparison is on the rounded monthly value, so a stored 1227.44 against a metered 1227.44 is a skip.

Replacement mechanism is unverified and must be settled with a live test on one month before the
logic is built on it. Both candidates exist in the API: `editConsumptionMonitoring` with the
existing reading's `_id` in the input (update in place), or `removeConsumptionMonitoring(_id)`
followed by an insert.

Nothing on disk is rewritten. The `readings/electricity/*.yaml` files and their invoice `costs`
blocks are left alone; this command talks only to EstateApp.

## Current state

Datahub holds hourly data from 2020-08-06 onward. A full export aggregates to 73 months, of which 71
are complete; 2020-08 is dropped because the export begins on the 6th, and the current month because
it is partial.

Classified against the 63 readings EstateApp holds for this meter:

- 61 skip -- the stored invoice-derived value matches the metered value to the cent
- 8 insert -- 2020-09 and 2020-10, which predate the invoice series, plus 2026-02 through 2026-07
- 2 replace -- 2022-03 (822.92 -> 778.03) and 2022-04 (703.81 -> 611.05)

Every EstateApp month is covered by a complete Datahub month, so no stored reading is left stranded.

The two 2022 disagreements do not offset each other and their neighbouring months match exactly, so
they are not an invoice period shifted across a month boundary; the invoices for those months look
estimated or adjusted. Metered wins, but the importer must show the before and after values so a
disagreement like this is visible rather than silently applied.

## Errors and edge cases

- More than one `MeteringPointGSRN` in the file -- fail with a message to export one accounting point
  at a time. Handling multiple points would require a GSRN-to-meter mapping that does not exist.
- `Unit Type` other than `kWh` -- fail.
- Rows with `Quality` other than `OK` -- include in the sum, and report the count per month so an
  estimated reading is visible rather than silent.
- Empty file, or no complete month in it -- report and exit without touching EstateApp.
- Missing token or condo id -- existing `_get_client` / `_get_condo_id` handling.

## Testing

- Parser and aggregation, against a small committed CSV fixture: BOM, decimal comma, a DST
  transition, an incomplete trailing month, a non-`OK` quality row.
- Month completeness: a month present in full is emitted; a partial leading or trailing month is not.
- Classification: insert when absent, skip when equal, replace when different.
- CLI: dry-run submits nothing; `--submit` inserts and replaces; single-GSRN and unit-type failures
  exit non-zero.
- Existing meter tests stay untouched and passing.

## Out of scope

- Automating the portal download or driving it from a captured session cookie.
- Storing hourly or 15-minute data in EstateApp.
- Utilities other than electricity, and meters other than the exported accounting point.
