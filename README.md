# Raksa

CLI tool for managing housing company data in [EstateApp](https://estateapp.com/en/), with import support for [Premis/Tahkola](https://www.kiinteistotahkola.fi/) exports and [Zaptec](https://zaptec.com/) EV charger data.

Built for Finnish housing companies (taloyhtiö) that need to migrate historical data or automate consumption tracking.

## Install

```bash
uv pip install git+https://github.com/PFigs/raksa.git
```

Or clone and install locally:

```bash
git clone git@github.com:PFigs/raksa.git
cd raksa
uv sync
```

## Setup

Get your EstateApp login token by running this in the browser console at `app.estateapp.com`:

```bash
raksa auth setup
```

This opens a local page with instructions. Alternatively, create a `.env` file:

```
RAKSA_TOKEN=your_login_token
RAKSA_CONDO_ID=your_condominium_id
```

The condominium ID is in the EstateApp URL: `app.estateapp.com/condominiums/<id>/all`.

## Commands

### Renovation notifications

```bash
raksa renovations list                         # list all
raksa renovations get <id>                     # show details
raksa renovations import <yaml-dir> --submit   # import from Premis YAML
```

### Fault reports

```bash
raksa faults list                              # list all
raksa faults get <id>                          # show details
raksa faults import <yaml-dir> --submit        # import from Premis YAML
```

### Consumption meters

```bash
raksa meters summary                           # show yearly totals
raksa meters import-zaptec <path> --submit     # import EV charger data from Zaptec Excel
raksa meters import-readings <dir> --submit    # import consumption readings from YAML
raksa meters fetch-temperature                 # fetch monthly temp from FMI open data
```

### Auth

```bash
raksa auth setup                               # browser-based token setup
```

All import commands default to dry-run. Pass `--submit` to actually send data.

## Data sources

### Premis/Tahkola exports

Renovation and fault cases exported as YAML in a hive directory structure:

```
cases/
  repair/year=2024/house=A6/2024-01-01_12345.yaml
  repair/year=2024/house=A6/2024-01-01_12345_chat.yaml
  common/year=2024/house=A6/2024-03-15_67890.yaml
```

The `repair` directory contains renovation notifications (muutostyöilmoitus), `common` has fault reports and service requests.

### Zaptec EV charger exports

Excel usage reports from the Zaptec portal, with per-charger consumption data.

### Consumption readings

A common YAML format for utility consumption extracted from invoices:

```yaml
meter_id: "55306988"
meter_label: "Kaukolämpö (55306988)"
utility: heat
unit: MWh
period_start: "2024-09-01"
period_end: "2024-09-30"
reading_date: "2024-09-30"
consumption: 12.225
costs:
  - provider: "Tampereen Energia Oy"
    amount_eur: 975.70
    type: usage
    invoice_number: "6003443405"
    source_file: "2024-10-01_Tampereen_Energia_Oy_6003443405.pdf"
```

Works for electricity (kWh), heating (MWh), and water (m3).

### FMI temperature data

Monthly average temperature from the [Finnish Meteorological Institute](https://en.ilmatieteenlaitos.fi/open-data) open data API. Useful for correlating heating consumption with weather.

## EstateApp API

Raksa talks to EstateApp's GraphQL API, which was reverse-engineered from the Meteor app's JavaScript bundle. There is no official API documentation. Key details:

- Auth: raw Meteor login token in the `authorization` header
- Dates: ISO 8601 on write, epoch ms on read
- The API has intentional typos (`condomininumName`, `workPerfromer`)
- `createShareholderRenovationGig` returns `1`, not the created ID
- `endDate` doesn't persist on creation
- File uploads go to `POST /upload` with collection `gigPreparation`

See `CLAUDE.md` for the full list of quirks.

## Development

```bash
uv sync                                        # install deps
uv run python -m pytest tests/ -v              # run tests
uv run python -m pytest -m submit tests/       # run live API write tests
```

## License

MIT
