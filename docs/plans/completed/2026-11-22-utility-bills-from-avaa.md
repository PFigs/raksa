# Read the utility bills from Avaa

## Design

### Scope

- The property manager moved the purchase invoices to Avaa (app.avaa.io) on 2026-11-01. The October bills are in Avaa
  only, as PDF attachments. `raksa meters sync-bills` reads the bills from Avaa and from Huoneistotieto.
- A new Avaa client signs in with email and password, lists the purchase invoices of the housing company, and downloads
  their attachments.
- `sync-bills` reads the heat bill of Tampereen Energia Oy and the grid bill of Tampereen Energia Sähköverkko Oy from the
  PDF text. A PDF bill of Tampereen Vesi Oy fails the run until a reader for it exists.
- The daily workflow in apollo-office passes `RAKSA_AVAA_EMAIL` and `RAKSA_AVAA_PASSWORD` to the bills step.

### Out of scope

- The water bill PDF. No sample exists yet. The first one arrives in January 2027.
- The EstateApp sign-in, which still goes through Huoneistotieto.
- The removal of the Huoneistotieto bill source. It holds the HTML bills from 2026-03 to 2026-09.

### Decisions

- **Choose the PDF reader by the supplier name.** Avaa gives the supplier of each invoice, and each supplier prints its
  own layout. Rejected: one reader for all PDFs, because the heat and grid PDFs share no line layout.
- **Each pattern must match exactly one value.** The period, the meter ID and the consumption each come from one
  pattern per supplier. Zero matches or two different values fail the run. This is the rule the HTML reader follows.
- **Fail on a PDF from Tampereen Vesi Oy.** A silent skip leaves no reading and sends no email until the next bill
  leaves a gap. Rejected: skip it, as the importer skips Fortum.
- **Find the housing company from the account.** `getCustomerCondos` lists the companies of the user, and the client
  requires exactly one. Rejected: a `RAKSA_AVAA_CONDO_ID` variable, which adds a secret that the account already
  answers.
- **Read both sources.** The readings of both go through the check that refuses two values for one meter and date.

### Reuse

- `BillReading`, the unit table `UTILITIES` and the gap check in `sync-bills`.
- `pypdf` reads the PDF text. It is a pure Python package.

### Risks and rollout

- **Avaa has no public API.** The client uses the endpoints of the Avaa web page. It needs the `X-XSRF-TOKEN` header
  from the `XSRF-TOKEN` cookie, or the API answers 401. A change on the Avaa side fails the run and sends the email.
- **A supplier changes its PDF layout.** The pattern then matches nothing and the run fails.
- Rollout: add the secrets `RAKSA_AVAA_EMAIL` and `RAKSA_AVAA_PASSWORD` to apollo-office, merge the workflow change,
  then merge raksa. The daily run checks out raksa `main`, so a raksa merge before the workflow change fails the run.
  The current raksa ignores the new variables. A run after the merge inserts the October heat and grid readings.

## Tasks

### Task 1: Avaa bills in sync-bills

- **Goal:** `sync-bills` imports the heat and grid readings of the Avaa PDF bills.
- **Acceptance criteria:**
  - The client signs in, reads every page of the invoice list, and downloads the attachments.
  - A failed sign-in fails with a clear message.
  - The heat and grid PDFs of October 2026 give the readings 16.97 MWh and 1263.457 kWh.
  - A PDF of Tampereen Vesi Oy fails the run.
  - A dry run against the live services lists the October readings as inserts.
- **Tests:**
  - `test_avaa_client_reads_every_page` fails if the client stops after the first page or drops the XSRF header.
  - `test_avaa_client_fails_on_a_wrong_password` fails if a refused sign-in passes.
  - `test_parse_pdf_bill` fails if a heat or grid reading is wrong, or if Fortum gives a reading.
  - `test_parse_pdf_bill_fails_on_a_water_bill` fails if a Tampereen Vesi Oy PDF passes.
  - `test_sync_bills_reads_avaa` fails if an Avaa reading does not reach the submit.
- **Model:** Opus.
- **Constraints:** keep the HTML reader and the Huoneistotieto source as they are.
