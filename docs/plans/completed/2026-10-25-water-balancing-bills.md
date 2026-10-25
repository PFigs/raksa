# Import water balancing bills

## Design

### Scope

- `raksa meters sync-bills` reads the Tampereen Vesi balancing bill (`TASAUSLASKU`) as well as the quarterly
  estimates. A balancing bill gives the real consumption of a long period, after the meter is read.
- It inserts one correction reading per water meter (`Vesi` and `Jätevesi`), dated on the last day of the balancing
  period. The value is the real consumption minus the readings stored for that meter inside the period, before its
  last day.
- The real consumption is the value after `Kulutus:`. The other quantity rows on the bill split the period by price,
  so they are not the consumption.

### Out of scope

- Replacing or deleting the estimates. The correction keeps the insert-only rule of `sync-bills`.
- Spreading the correction over the quarters of the period.

### Decisions

- **One correction reading on the last day of the period.** The period total then matches the meter. Rejected: replace
  the estimates of the period, because it needs delete-and-resubmit logic. Rejected: skip balancing bills, because
  January and February 2026 have no other source after the meter change, and the estimates of 2024 and 2025 were
  380 m3 too low.
- **Sum the readings before the last day, and include the estimates that the same run inserts.** A second run then
  computes the same value, finds it stored on the last day, and skips it. The correction stays right when a late
  estimate and the balancing bill arrive in the same run.
- **A negative correction fails the run.** The estimates were then too high. EstateApp's handling of a negative reading
  is unknown, so a person decides. Rejected: submit it, or skip it without an email.
- **The 2024-01-01 to 2026-02-26 correction is already in EstateApp** (380 m3 for both old meters, entered by hand on
  2026-10-25). The first run after this change must skip it.

### Reuse

- `parse_bill` in `meters/bills.py`, the planner in `meters/estateapp.py`, and the check after the submit in
  `sync-bills`.

### Risks and rollout

- **A stored reading that is wrong inside the period makes the correction wrong.** A duplicate reading made the
  Jätevesi total 404 m3 too high before it was deleted on 2026-10-25.
- Rollout: merge. The next daily run shows a skip for 2026-02-26 on both old water meters.

## Tasks

### Task 1: Balancing bill corrections

- **Goal:** a water balancing bill gives one correction reading per water meter, and a second run changes nothing.
- **Acceptance criteria:**
  - The parser returns two readings for a balancing bill, `Vesi (<meter>)` and `Jätevesi (<meter>)`, with the
    `Kulutus:` value, the period, and a mark that they are balancing readings.
  - `sync-bills` turns each balancing reading into the real value minus the stored and the planned readings of that
    meter inside the period, before its last day.
  - A negative correction fails the run with a message that names the meter and the period.
  - A dry run against the live services shows a skip for 2026-02-26 on `Vesi (14667678)` and
    `Jätevesi (14667678)`, with no difference printed.
  - The plan file `2026-10-25-utility-bills-from-huoneistotieto.md` no longer says that balancing bills are skipped.
- **Tests:**
  - `test_parse_bill` expects the two balancing readings from the balancing fixture. It fails if the parser takes a
    price row instead of the `Kulutus:` value.
  - `test_sync_bills_corrects_a_balancing_bill` fails if the correction ignores a stored estimate, ignores an estimate
    planned in the same run, counts a reading on the last day, or submits a negative value.
- **Model:** Opus.
- **Constraints:** keep insert-only. Change no behavior for heat, electricity or the water estimates.
