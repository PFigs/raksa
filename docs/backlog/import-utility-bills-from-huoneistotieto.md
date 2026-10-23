---
worth: yes
added: 2026-10-23
---
# import electricity, water and heating bills from Huoneistotieto

The electricity, water and heating readings reach EstateApp by hand today: the `extract-consumption` skill turns each
bill into a YAML file, and `raksa meters import-readings` submits it. The YAML files now live in the private
apollo-office repo under `readings/`.

Fetch the bills from Huoneistotieto instead, extract consumption and costs, and import them, on a schedule like the
Zaptec sync. The headless Huoneistotieto login from `raksa/link_sign_in.py` already works, and the Huoneistotieto
client can list document folders.

Still to find out: where the bills sit in Huoneistotieto (a document folder or the accounting side), which endpoint
downloads one, and whether the PDFs are text or scans. EstateApp refuses a second submit for a meter and date that
already holds readings, so submit each period in one call.
