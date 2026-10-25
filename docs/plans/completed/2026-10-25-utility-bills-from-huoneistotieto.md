# Import utility bills from Huoneistotieto

## Design

### Scope

- Add `raksa meters sync-bills`. It reads the electricity, heat and water bills from Huoneistotieto, extracts the
  consumption, and submits one EstateApp reading per meter and billing period. It is a dry run unless `--submit` is set.
- The bills sit on the Huoneistotieto accounting side, not in the document folders:
  1. `GET /api/services/app/Asiakirja/GetAccountingDocuments?officeId=…&condominiumId=…&year=…` returns the
     accounting documents of a year. The `OSTOLASKUT` document holds a JSON list of purchase invoices. Each row has
     the payee, the due date, the amount and the attachment file names (`liitteet`).
  2. `GET /api/services/app/Asiakirja/GetInvoiceFile?officeId=…&condominiumNumber=…&fileName=…` returns one
     attachment as base64.
- The bills from 2026-03 on are HTML e-invoices with text:

  | Utility | Bill | Values on the bill |
  |---|---|---|
  | Heat | Tampereen Energia, monthly `KULUTUSLASKU` | MWh, meter number |
  | Electricity | Tampereen Energia Sähköverkko, monthly `KULUTUSLASKU` | kWh, site ID (`Käyttöpaikkatunnus`) |
  | Water | Tampereen Vesi, quarterly `ARVIOLASKU` (estimate) | m3, meter number, water and wastewater rows |

- Run the command each day in the apollo-office scheduled workflow, after the Zaptec sync.

### Out of scope

- Costs. EstateApp readings have no cost field.
- YAML files. The command goes from the bill to EstateApp. The `readings/` folder in apollo-office stays as the
  history up to 2026-01.
- PDF attachments. Two utility bills in 2026 are PDFs: the 2026-02 heat bill is a scan without text, and the 2026-03
  Fortum bill repeats the kWh of the grid bill. Enter the 2026-02 heat reading once by hand with the
  `extract-consumption` skill and `raksa meters import-readings`.
- Water balancing bills (`TASAUSLASKU`). See the decisions.

### Decisions

- **Water gets the quarterly estimate as its reading**, the same way as the 2024 and 2025 data already in EstateApp.
  Skip the balancing bills. Rejected: real readings only, because the last balancing bill covers 2024-01 to 2026-02 in
  one value. Rejected: replace the estimates when a balancing bill arrives, because it needs delete-and-resubmit logic.
- **Identify the utility by the bill content, not by the payee name.** The unit on the period line (`MWh`, `kWh`,
  `m3`) decides the utility. A bill without a `KULUTUSLASKU` or `ARVIOLASKU` period line is skipped.
- **Electricity comes from the grid bill.** The Fortum supply bill has the same kWh and the same site ID each month,
  so it adds no data, and a second submit for the same meter and date is refused. The parser skips it.
- **Reuse the existing meter labels**, so the readings join the existing series: `Kaukolämpö (<meter>)`,
  `Sähkö yhteinen (<site ID>)`, `Vesi (<meter>)` and `Jätevesi (<meter>)`. The water meter changed on 2026-02-27 from
  14667678 to 06245559, so water continues under a new meter.
- **The reading date is the last day of the billing period.**
- **Insert new dates and skip dates that already hold a reading. Never replace.** The Datahub import already holds
  electricity to 2026-07 from hourly data, and it stays. When a skipped value differs from the bill, the command prints
  both values. Rejected: replace on difference, because a bill and the Datahub export round differently.
- **Lift `plan_readings` from `meters/datahub.py` into `meters/estateapp.py`, with a date and value pair as input.**
  The Datahub import and the bill import then share one planner. Rejected: a second planner for bills.
- **Read the current year and the year before.** `GetAccountingDocumentYears` returns only 2026 today, but a January
  run still needs the December bills.
- **Add the bill step to the existing daily workflow in apollo-office**, with its own failure email. It reuses the
  checkout, the uv setup and the secrets. Rejected: a separate workflow, which repeats all of those.

### Reuse

- The Huoneistotieto login from `raksa/link_sign_in.py` for the token, and `HuoneistotietoClient` for the two new calls.
- `ensure_meters_exist`, `get_consumptions`, `submit_readings` and the check after the submit from `import-datahub`,
  because the EstateApp counts are not reliable.

### Risks and rollout

- **Unofficial endpoints and an HTML layout that can change.** A parse failure fails the run, and the workflow emails
  its owner. A bill that parses to no reading prints a warning and does not fail the run.
- **EstateApp refuses a second submit for a meter and date.** The planner skips existing dates, so each date is
  submitted once.
- Rollout:
  1. Merge raksa.
  2. Add the `RAKSA_HT_CONDOMINIUM_NUMBER` secret to apollo-office. The other Huoneistotieto secrets are already there.
  3. Run `sync-bills` without `--submit` and check the plan. Then run it with `--submit` once by hand.
  4. Enter the 2026-02 heat reading by hand.
  5. Merge the apollo-office workflow step.

## Tasks

### Task 1: The sync-bills command

- **Goal:** `raksa meters sync-bills --submit` puts the heat, electricity and water readings from the Huoneistotieto
  bills into EstateApp, and a second run changes nothing.
- **Acceptance criteria:**
  - The client lists the purchase invoice rows of a year and downloads an attachment.
  - The parser returns the utility, the meter or site ID, the period and the consumption for the heat, grid and water
    estimate bills. It returns nothing for the Fortum bill and the balancing bill.
  - A water estimate gives two readings, one for `Vesi` and one for `Jätevesi`.
  - Readings for existing dates are skipped. A different value prints both values.
  - The command checks EstateApp after the submit, the same way as `import-datahub`.
  - `import-datahub` behaves as before with the lifted planner.
- **Tests:**
  - `test_parse_bill` over trimmed HTML fixtures of a heat bill, a grid bill, a water estimate, a Fortum bill and a
    balancing bill. It fails if a field is read wrong or if an ignored bill gives a reading.
  - `test_plan_readings_never_replaces` fails if an existing date gets submitted again or if a difference is not
    reported.
  - `test_list_purchase_invoices` fails if the double-encoded JSON of `GetAccountingDocuments` is decoded wrong.
- **Model:** Opus.
- **Constraints:** trim the fixtures to the lines the parser needs, without names, addresses or bank accounts.
  Change no behavior of the existing commands.

### Task 2: The daily workflow step in apollo-office

- **Goal:** the daily scheduled workflow in apollo-office runs `raksa meters sync-bills --submit` after the Zaptec
  sync, and emails its owner when the bill step fails.
- **Acceptance criteria:**
  - The bill step runs even when the Zaptec step fails, and the Zaptec step runs even when the bill step fails.
  - The step gets the Huoneistotieto secrets, including `RAKSA_HT_CONDOMINIUM_NUMBER`.
  - A failed bill step sends an email that names the bill import, separate from the Zaptec email.
- **Tests:** none. Check it with a manual run of the workflow after the merge.
- **Model:** Opus.
- **Constraints:** reuse the checkout, the uv setup and the email step of the Zaptec workflow. Do not add a second
  workflow file.
