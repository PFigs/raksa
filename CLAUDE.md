# Raksa CLI

CLI tool for interacting with EstateApp (app.estateapp.com), a housing company management system.

## Project structure

```
src/raksa/
  client.py      - EstateApp GraphQL API client
  models.py      - Pydantic models (API types + YAML source data + transformation)
  config.py      - Token and config resolution (.env, env var, config file)
  cli.py         - Typer CLI entry point
  auth_server.py - Local HTTP server for browser-based auth setup
  commands/
    auth.py         - raksa auth setup
    renovations.py  - raksa renovations {list,get,import}
    faults.py       - raksa faults {list,get,import}
    meters.py       - raksa meters {import-zaptec,summary}
  premis/
    cases.py        - Read premis case exports (renovation + fault YAMLs)
    invoices.py     - Read premis invoice exports (PDF + YAML metadata)
  meters/
    zaptec.py       - Read Zaptec EV charger Excel exports
    estateapp.py    - EstateApp consumption meter API operations
```

## CLI commands

```
raksa auth setup                              # browser-based token setup
raksa renovations list [--condo-id ID]        # list shareholder renovation gigs
raksa renovations get <gig-id>                # show renovation details
raksa renovations import <dir> [--submit]     # import from hive YAML (dry-run default)
raksa faults list [--condo-id ID]             # list fault notifications
raksa faults get <fault-id>                   # show fault details
raksa faults import <dir> [--submit]          # import from hive YAML (dry-run default)
raksa meters import-zaptec <path> [--submit]  # import EV consumption from Zaptec Excel
raksa meters summary                          # show consumption totals
```

## EstateApp API details

- Meteor 3.4 app with Apollo GraphQL at `https://app.estateapp.com/graphql`
- Auth: raw Meteor login token in the `authorization` header (not Bearer)
- Token obtained from browser: `localStorage.getItem('Meteor.loginToken')`
- GraphQL introspection is disabled; schemas were reverse-engineered from the JS bundle
- `createShareholderRenovationGig` returns `1` (success flag), not the gig ID; use `list_renovations` to find the created gig
- Dates must be ISO 8601 strings on write (e.g. `2021-01-01T00:00:00.000Z`), returned as epoch ms on read
- `endDate` doesn't persist on creation (known API limitation)
- `updateShareholderRenovationGig` works for `title` but not for `startDate` or `status`
- API has intentional typos: `condomininumName` (missing d), `workPerfromer` (transposed r)
- File uploads: `POST /upload` with FormData, use collection `gigPreparation` for gig attachments
- Fault notifications require `informantInfo` with non-null `email`/`phone` (empty string ok)
- Consumption meters: `specification` in readings must match the meter `key` (lowercase, underscores), not the label

## Development

- Use `uv` for all Python operations (never pip)
- Run tests: `uv run python -m pytest tests/ -v`
- Live API write tests: `uv run python -m pytest -m submit tests/test_api_live.py -v`
- Config: copy `.env.example` to `.env` and fill in values

## YAML import format

Source data uses a hive directory structure: `year=*/house=*/*.yaml`
- Repair cases (renovation notifications): `RequestType.Label == "Huoneistomuutosilmoitus"`
- Common cases (fault reports): everything else
- Chat files: `*_chat.yaml` siblings, uploaded alongside the main YAML

## Premis data

Premis (Tahkola) was the previous management system. We no longer have API access, but exported data lives locally:
- Cases: hive YAML in `cases/common/` and `cases/repair/`
- Invoices: PDF + YAML metadata in `invoices/year=*/month=*/`
- The `premis/` module reads this exported data; it does not connect to Premis
