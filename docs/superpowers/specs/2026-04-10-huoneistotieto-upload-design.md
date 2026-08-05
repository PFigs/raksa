# Huoneistotieto Invoice Upload

Upload Premis purchase invoice exports (PDF + YAML metadata) to huoneistotieto.fi, organized into year folders matching the local hive structure.

## Module structure

```
src/raksa/
  huoneistotieto/
    __init__.py
    client.py          # Huoneistotieto REST API client
  commands/
    invoices.py        # raksa invoices upload
```

## CLI command

```
raksa invoices upload <invoices-dir> [--submit] [--years 2020,2021,2022,2023,2024] [--parent-folder-id ID]
```

- `invoices-dir` -- path to the premis invoices hive directory (e.g. `~/premis/invoices`)
- `--submit` -- execute the upload (dry-run by default)
- `--years` -- comma-separated years to upload; defaults to all years found in directory
- `--parent-folder-id` -- override `RAKSA_HT_PARENT_FOLDER_ID` from env

## Config

All huoneistotieto values come from `.env` / env vars, resolved through `config.py`:

| Env var | Purpose |
|---------|---------|
| `RAKSA_HT_TOKEN` | Bearer JWT auth token |
| `RAKSA_HT_USER_ID` | User ID for upload endpoint |
| `RAKSA_HT_OFFICE_ID` | Office ID (used in both endpoints) |
| `RAKSA_HT_CONDOMINIUM_ID` | Condominium ID (used in upload endpoint) |
| `RAKSA_HT_CONDOMINIUM_NUMBER` | Condominium number (used in folder creation) |
| `RAKSA_HT_PARENT_FOLDER_ID` | Parent folder under which year folders are created |

The client constructor takes all of these as arguments. No hard-coded values.

## API endpoints

### Create folder

```
POST /api/services/app/Asiakirja/AddCondominiumFolder
  ?officeId={office_id}
  &condominiumNumber={condo_number}
  &name={url_encoded_name}
  &parentId={parent_folder_id}
  &level=3
```

All parameters are query params. No request body. Assumed to return the new folder ID (response shape not yet confirmed -- will verify during implementation).

### Upload files

```
POST /uploadfiles
  ?officeId={office_id}
  &condominiumId={condo_id}
  &userId={user_id}
  &folderId={folder_id}
  &level=3
```

- Auth: `Authorization: Bearer {token}`
- Content-Type: `multipart/form-data`
- Field name: `upload[]` (array notation)
- Files: PDF + YAML pairs per invoice

Note: folder creation uses `condominiumNumber` while upload uses `condominiumId` -- different identifiers for different endpoints.

## Upload flow

1. Scan `invoices-dir` for `year=*/month=*/` hive structure using existing `premis/invoices.py` loader
2. Group invoices by year, filter to requested `--years`
3. For each year:
   a. Create a `year=YYYY` folder under the parent folder ID
   b. Collect all PDF + YAML file pairs across all months in that year
   c. Upload files in batches to the created folder (flat -- no month subfolders on huoneistotieto)
4. Print summary: folders created, files uploaded per year

Dry-run mode prints what would happen without making API calls.

## Batch upload

Upload files in batches (e.g. 20 files per request) to avoid oversized multipart payloads. Each batch is a single POST to `/uploadfiles`.

## Error handling

- Missing env vars: raise `RaksaConfigError` with the missing var name
- Folder creation failure: log error, skip that year, continue with next
- Upload failure: log error with the batch details, continue with next batch
- Missing PDF for a YAML (or vice versa): warn, skip that invoice
