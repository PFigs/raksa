# Huoneistotieto Invoice Upload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upload Premis purchase invoice exports (PDF + YAML) to huoneistotieto.fi, organized into year folders.

**Architecture:** New `huoneistotieto/` package with a REST client for folder creation and file upload. New `commands/invoices.py` command wired into the CLI. Config resolved from `RAKSA_HT_*` env vars through `config.py`.

**Tech Stack:** httpx (HTTP client, already a dependency), typer (CLI), pydantic (config validation), pytest (tests)

---

## File Structure

| File | Responsibility |
|------|---------------|
| `src/raksa/huoneistotieto/__init__.py` | Package marker (empty) |
| `src/raksa/huoneistotieto/client.py` | REST client: create folder, upload files |
| `src/raksa/config.py` | Add `resolve_ht_config()` for `RAKSA_HT_*` vars |
| `src/raksa/commands/invoices.py` | `raksa invoices upload` command |
| `src/raksa/cli.py` | Register invoices sub-app |
| `tests/test_huoneistotieto_client.py` | Client unit tests (httpx mocking) |
| `tests/test_invoices_command.py` | Command integration tests (dry-run, submit) |
| `.env.example` | Document new env vars |

---

### Task 1: Config — resolve huoneistotieto env vars

**Files:**
- Modify: `src/raksa/config.py`
- Test: `tests/test_config_ht.py`

- [ ] **Step 1: Write failing test for resolve_ht_config**

Create `tests/test_config_ht.py`:

```python
import os
from unittest.mock import patch

import pytest

from raksa.config import RaksaConfigError, resolve_ht_config


def test_resolve_ht_config_from_env():
    env = {
        "RAKSA_HT_TOKEN": "jwt-token-123",
        "RAKSA_HT_USER_ID": "123456",
        "RAKSA_HT_OFFICE_ID": "131",
        "RAKSA_HT_CONDOMINIUM_ID": "206",
        "RAKSA_HT_CONDOMINIUM_NUMBER": "174",
        "RAKSA_HT_PARENT_FOLDER_ID": "69cb705c3d28bf7d882e43ab",
    }
    with patch.dict(os.environ, env, clear=False):
        config = resolve_ht_config()
    assert config.token == "jwt-token-123"
    assert config.user_id == "123456"
    assert config.office_id == "131"
    assert config.condominium_id == "206"
    assert config.condominium_number == "174"
    assert config.parent_folder_id == "69cb705c3d28bf7d882e43ab"


def test_resolve_ht_config_missing_token():
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(RaksaConfigError, match="RAKSA_HT_TOKEN"):
            resolve_ht_config()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/test_config_ht.py -v`
Expected: FAIL — `resolve_ht_config` does not exist

- [ ] **Step 3: Implement resolve_ht_config**

Add to `src/raksa/config.py` after the existing functions:

```python
from pydantic import BaseModel


class HuoneistotietoConfig(BaseModel):
    token: str
    user_id: str
    office_id: str
    condominium_id: str
    condominium_number: str
    parent_folder_id: str


def resolve_ht_config(parent_folder_id_override: str | None = None) -> HuoneistotietoConfig:
    """Resolve huoneistotieto.fi config from RAKSA_HT_* env vars."""
    load_dotenv(dotenv_path=find_dotenv(usecwd=True))

    required = {
        "RAKSA_HT_TOKEN": "token",
        "RAKSA_HT_USER_ID": "user_id",
        "RAKSA_HT_OFFICE_ID": "office_id",
        "RAKSA_HT_CONDOMINIUM_ID": "condominium_id",
        "RAKSA_HT_CONDOMINIUM_NUMBER": "condominium_number",
        "RAKSA_HT_PARENT_FOLDER_ID": "parent_folder_id",
    }
    values = {}
    for env_var, field in required.items():
        val = os.environ.get(env_var)
        if not val and field != "parent_folder_id":
            raise RaksaConfigError(f"Missing required env var: {env_var}")
        values[field] = val or ""

    if parent_folder_id_override:
        values["parent_folder_id"] = parent_folder_id_override

    if not values["parent_folder_id"]:
        raise RaksaConfigError(
            "Missing required env var: RAKSA_HT_PARENT_FOLDER_ID "
            "(or pass --parent-folder-id)"
        )

    return HuoneistotietoConfig(**values)
```

Note: the `from pydantic import BaseModel` import is already used in `models.py` but not in `config.py`, so it needs to be added at the top of `config.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/test_config_ht.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run python -m pytest tests/ -v`
Expected: All existing tests still pass

- [ ] **Step 6: Commit**

```bash
git add src/raksa/config.py tests/test_config_ht.py
git commit -m "feat: add huoneistotieto config resolution"
```

---

### Task 2: Huoneistotieto REST client

**Files:**
- Create: `src/raksa/huoneistotieto/__init__.py`
- Create: `src/raksa/huoneistotieto/client.py`
- Test: `tests/test_huoneistotieto_client.py`

- [ ] **Step 1: Create package and write failing tests**

Create `src/raksa/huoneistotieto/__init__.py` (empty file).

Create `tests/test_huoneistotieto_client.py`:

```python
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

from raksa.huoneistotieto.client import HuoneistotietoClient


@pytest.fixture
def mock_transport():
    return MagicMock(spec=httpx.BaseTransport)


@pytest.fixture
def client(mock_transport):
    return HuoneistotietoClient(
        token="test-jwt",
        user_id="123456",
        office_id="131",
        condominium_id="206",
        condominium_number="174",
        http_client=httpx.Client(transport=mock_transport),
    )


def _mock_response(transport, status_code=200, json_data=None):
    resp = httpx.Response(
        status_code=status_code,
        json=json_data,
        request=httpx.Request("POST", "https://example.com"),
    )
    transport.handle_request.return_value = resp
    return resp


def test_create_folder(client, mock_transport):
    _mock_response(mock_transport, json_data={
        "result": "69d893ef3d28bf7d88304557",
    })

    folder_id = client.create_folder(
        name="year=2024",
        parent_id="69cb705c3d28bf7d882e43ab",
    )

    assert folder_id == "69d893ef3d28bf7d88304557"
    request = mock_transport.handle_request.call_args[0][0]
    assert "/api/services/app/Asiakirja/AddCondominiumFolder" in str(request.url)
    assert "officeId=131" in str(request.url)
    assert "condominiumNumber=174" in str(request.url)
    assert "name=year%3D2024" in str(request.url)
    assert "parentId=69cb705c3d28bf7d882e43ab" in str(request.url)
    assert "level=3" in str(request.url)
    assert request.headers["authorization"] == "Bearer test-jwt"


def test_upload_files(client, mock_transport, tmp_path):
    _mock_response(mock_transport, json_data={"result": True})

    pdf = tmp_path / "invoice.pdf"
    pdf.write_bytes(b"%PDF-fake")
    yaml_file = tmp_path / "invoice.yaml"
    yaml_file.write_text("seller: Test Oy")

    client.upload_files(
        folder_id="69d893ef3d28bf7d88304557",
        files=[pdf, yaml_file],
    )

    request = mock_transport.handle_request.call_args[0][0]
    assert "/uploadfiles" in str(request.url)
    assert "officeId=131" in str(request.url)
    assert "condominiumId=206" in str(request.url)
    assert "userId=123456" in str(request.url)
    assert "folderId=69d893ef3d28bf7d88304557" in str(request.url)
    assert request.headers["authorization"] == "Bearer test-jwt"


def test_create_folder_error(client, mock_transport):
    _mock_response(mock_transport, status_code=500, json_data={"error": "server error"})

    with pytest.raises(httpx.HTTPStatusError):
        client.create_folder(name="year=2024", parent_id="parent123")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_huoneistotieto_client.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement the client**

Create `src/raksa/huoneistotieto/client.py`:

```python
"""Huoneistotieto.fi REST API client."""
from pathlib import Path

import httpx


BASE_URL = "https://api.huoneistotieto.fi"


class HuoneistotietoClient:
    def __init__(
        self,
        token: str,
        user_id: str,
        office_id: str,
        condominium_id: str,
        condominium_number: str,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._token = token
        self._user_id = user_id
        self._office_id = office_id
        self._condominium_id = condominium_id
        self._condominium_number = condominium_number
        self._http = http_client or httpx.Client(timeout=120.0)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    def create_folder(self, name: str, parent_id: str) -> str:
        """Create a folder and return the new folder ID."""
        resp = self._http.post(
            f"{BASE_URL}/api/services/app/Asiakirja/AddCondominiumFolder",
            params={
                "officeId": self._office_id,
                "condominiumNumber": self._condominium_number,
                "name": name,
                "parentId": parent_id,
                "level": "3",
            },
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()["result"]

    def upload_files(self, folder_id: str, files: list[Path]) -> None:
        """Upload files to a folder via multipart form data."""
        file_tuples = []
        for f in files:
            mime = "application/pdf" if f.suffix == ".pdf" else "application/yaml"
            file_tuples.append(("upload[]", (f.name, f.read_bytes(), mime)))

        resp = self._http.post(
            f"{BASE_URL}/uploadfiles",
            params={
                "officeId": self._office_id,
                "condominiumId": self._condominium_id,
                "userId": self._user_id,
                "folderId": folder_id,
                "level": "3",
            },
            headers=self._headers(),
            files=file_tuples,
        )
        resp.raise_for_status()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_huoneistotieto_client.py -v`
Expected: PASS (the multipart content assertion may need adjusting — see step 5)

- [ ] **Step 5: Run full test suite**

Run: `uv run python -m pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add src/raksa/huoneistotieto/__init__.py src/raksa/huoneistotieto/client.py tests/test_huoneistotieto_client.py
git commit -m "feat: add huoneistotieto REST client"
```

---

### Task 3: CLI command — raksa invoices upload

**Files:**
- Create: `src/raksa/commands/invoices.py`
- Modify: `src/raksa/cli.py`
- Test: `tests/test_invoices_command.py`

- [ ] **Step 1: Write failing test for dry-run mode**

Create `tests/test_invoices_command.py`:

```python
from pathlib import Path

import yaml
from typer.testing import CliRunner

from raksa.cli import app

runner = CliRunner()


def _write_invoice(base: Path, year: int, month: int, seller: str, invoice_num: str):
    """Create a fake invoice PDF+YAML pair in the hive structure."""
    dir_path = base / f"year={year}" / f"month={month}"
    dir_path.mkdir(parents=True, exist_ok=True)
    safe_seller = seller.replace(" ", "_")
    stem = f"{year}-{month:02d}-01_{safe_seller}_{invoice_num}"
    meta = {
        "id": f"inv-{invoice_num}",
        "invoice_number": invoice_num,
        "seller": seller,
        "accounting_date": f"{year}-{month:02d}-01T00:00:00",
        "amount": 100.0,
        "currency": "EUR",
        "payment_status": "Maksettu",
    }
    (dir_path / f"{stem}.yaml").write_text(yaml.dump(meta))
    (dir_path / f"{stem}.pdf").write_bytes(b"%PDF-fake")


def test_upload_dry_run(tmp_path):
    _write_invoice(tmp_path, 2023, 6, "Builder Oy", "001")
    _write_invoice(tmp_path, 2024, 1, "Plumber Ltd", "002")
    _write_invoice(tmp_path, 2024, 3, "Builder Oy", "003")

    result = runner.invoke(app, ["invoices", "upload", str(tmp_path)])
    assert result.exit_code == 0
    assert "year=2023" in result.output
    assert "year=2024" in result.output
    assert "1 file pair" in result.output or "1 invoice" in result.output
    assert "2 file pair" in result.output or "2 invoice" in result.output
    assert "Dry-run" in result.output


def test_upload_dry_run_filter_years(tmp_path):
    _write_invoice(tmp_path, 2023, 6, "Builder Oy", "001")
    _write_invoice(tmp_path, 2024, 1, "Plumber Ltd", "002")

    result = runner.invoke(app, ["invoices", "upload", str(tmp_path), "--years", "2024"])
    assert result.exit_code == 0
    assert "year=2024" in result.output
    assert "year=2023" not in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_invoices_command.py -v`
Expected: FAIL — invoices command not registered

- [ ] **Step 3: Implement the invoices command**

Create `src/raksa/commands/invoices.py`:

```python
"""Upload Premis invoice exports to huoneistotieto.fi."""
from collections import defaultdict
from pathlib import Path
from typing import Annotated

import typer

from raksa.config import RaksaConfigError, resolve_ht_config
from raksa.huoneistotieto.client import HuoneistotietoClient

app = typer.Typer(help="Invoice management", no_args_is_help=True)


def _collect_invoice_pairs(invoices_dir: Path) -> dict[str, list[tuple[Path, Path]]]:
    """Scan hive directory and return {year: [(pdf, yaml), ...]} pairs."""
    by_year: dict[str, list[tuple[Path, Path]]] = defaultdict(list)
    for yaml_path in sorted(invoices_dir.rglob("*.yaml")):
        pdf_path = yaml_path.with_suffix(".pdf")
        if not pdf_path.exists():
            continue
        # Extract year from hive path: .../year=2024/month=1/file.yaml
        for part in yaml_path.parts:
            if part.startswith("year="):
                year = part.split("=")[1]
                by_year[year].append((pdf_path, yaml_path))
                break
    return dict(by_year)


@app.command("upload")
def upload(
    invoices_dir: Annotated[Path, typer.Argument(help="Path to premis invoices hive directory")],
    submit: Annotated[bool, typer.Option("--submit", help="Actually upload (default is dry-run)")] = False,
    years: Annotated[str | None, typer.Option("--years", help="Comma-separated years to upload (default: all)")] = None,
    parent_folder_id: Annotated[str | None, typer.Option("--parent-folder-id", help="Override parent folder ID")] = None,
):
    """Upload Premis invoice exports to huoneistotieto.fi."""
    if not invoices_dir.is_dir():
        typer.echo(f"Error: {invoices_dir} is not a directory", err=True)
        raise typer.Exit(1)

    all_pairs = _collect_invoice_pairs(invoices_dir)
    if not all_pairs:
        typer.echo("No invoice pairs (PDF + YAML) found.")
        return

    # Filter years
    if years:
        requested = {y.strip() for y in years.split(",")}
        all_pairs = {y: pairs for y, pairs in all_pairs.items() if y in requested}

    if not all_pairs:
        typer.echo("No invoices match the requested years.")
        return

    typer.echo(f"Found invoices in {len(all_pairs)} year(s):\n")
    for year in sorted(all_pairs):
        pairs = all_pairs[year]
        typer.echo(f"  year={year}: {len(pairs)} invoices ({len(pairs) * 2} files)")

    total = sum(len(p) for p in all_pairs.values())
    typer.echo(f"\nTotal: {total} invoices ({total * 2} files)")

    if not submit:
        typer.echo("\nDry-run mode. Pass --submit to actually upload.")
        return

    try:
        ht_config = resolve_ht_config(parent_folder_id_override=parent_folder_id)
    except RaksaConfigError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    client = HuoneistotietoClient(
        token=ht_config.token,
        user_id=ht_config.user_id,
        office_id=ht_config.office_id,
        condominium_id=ht_config.condominium_id,
        condominium_number=ht_config.condominium_number,
    )

    batch_size = 20  # files per upload request

    for year in sorted(all_pairs):
        pairs = all_pairs[year]
        typer.echo(f"\nCreating folder year={year}...")
        folder_id = client.create_folder(
            name=f"year={year}",
            parent_id=ht_config.parent_folder_id,
        )
        typer.echo(f"  Created folder: {folder_id}")

        # Flatten pairs into a single file list
        files = []
        for pdf_path, yaml_path in pairs:
            files.append(pdf_path)
            files.append(yaml_path)

        # Upload in batches
        for i in range(0, len(files), batch_size):
            batch = files[i : i + batch_size]
            typer.echo(f"  Uploading batch {i // batch_size + 1} ({len(batch)} files)...")
            client.upload_files(folder_id=folder_id, files=batch)

        typer.echo(f"  Uploaded {len(pairs)} invoices ({len(files)} files)")

    typer.echo("\nDone.")
```

- [ ] **Step 4: Register the invoices sub-app in cli.py**

Add to `src/raksa/cli.py`:

```python
from raksa.commands.invoices import app as invoices_app
```

And after the existing `add_typer` calls:

```python
app.add_typer(invoices_app, name="invoices")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_invoices_command.py -v`
Expected: PASS

- [ ] **Step 6: Run full test suite**

Run: `uv run python -m pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git add src/raksa/commands/invoices.py src/raksa/cli.py tests/test_invoices_command.py
git commit -m "feat: add raksa invoices upload command"
```

---

### Task 4: Update .env.example and verify end-to-end

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: Update .env.example**

Add to `.env.example` after the existing vars:

```
# Huoneistotieto.fi (for invoice uploads)
# RAKSA_HT_TOKEN=your_jwt_token_here
# RAKSA_HT_USER_ID=your_user_id
# RAKSA_HT_OFFICE_ID=your_office_id
# RAKSA_HT_CONDOMINIUM_ID=your_condominium_id
# RAKSA_HT_CONDOMINIUM_NUMBER=your_condominium_number
# RAKSA_HT_PARENT_FOLDER_ID=parent_folder_for_year_folders
```

- [ ] **Step 2: Run full test suite**

Run: `uv run python -m pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 3: Verify dry-run with real data**

Run: `uv run python -m raksa invoices upload "/home/silva/home projects/premis/invoices" --years 2024`
Expected: Shows invoice counts for 2024, prints dry-run message

- [ ] **Step 4: Commit**

```bash
git add .env.example
git commit -m "docs: add huoneistotieto env vars to .env.example"
```

---

### Task 5: Live upload test with a single year

This task is manual — run it yourself to verify the API integration works before uploading all years.

- [ ] **Step 1: Ensure .env has all RAKSA_HT_* vars set**

Check your `.env` file has valid values for all six `RAKSA_HT_*` variables.

- [ ] **Step 2: Test with a single small year first**

Run: `uv run python -m raksa invoices upload "/home/silva/home projects/premis/invoices" --years 2020 --submit`

Year 2020 has only 23 invoices — good for a first test.

- [ ] **Step 3: Verify on huoneistotieto.fi**

Open https://huoneistotieto.fi, navigate to the documents section, and confirm the `year=2020` folder exists with the uploaded files.

- [ ] **Step 4: Upload remaining years**

Run: `uv run python -m raksa invoices upload "/home/silva/home projects/premis/invoices" --years 2021,2022,2023,2024 --submit`
