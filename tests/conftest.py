import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

from raksa.config import resolve_token, resolve_base_url, resolve_condo_id, RaksaConfigError
from raksa.client import EstateAppClient

load_dotenv()

PREMIS_CASES_DIR = Path(os.environ.get("RAKSA_PREMIS_DIR", "premis/cases"))
CONDO_ID = os.environ.get("RAKSA_CONDO_ID", "")
KNOWN_GIG_ID = os.environ.get("RAKSA_KNOWN_GIG_ID", "")


@pytest.fixture(scope="session")
def live_client():
    """Client connected to the real EstateApp API. Skips if no token configured."""
    try:
        token = resolve_token()
    except RaksaConfigError:
        pytest.skip("No RAKSA_TOKEN configured -- skipping live API tests")
    return EstateAppClient(token=token, base_url=resolve_base_url())


@pytest.fixture
def condo_id():
    resolved = CONDO_ID or resolve_condo_id()
    if not resolved:
        pytest.skip("No RAKSA_CONDO_ID configured")
    return resolved


@pytest.fixture
def known_gig_id():
    if not KNOWN_GIG_ID:
        pytest.skip("No RAKSA_KNOWN_GIG_ID configured")
    return KNOWN_GIG_ID


@pytest.fixture
def premis_repair_dir():
    path = PREMIS_CASES_DIR / "repair"
    if not path.exists():
        pytest.skip("premis repair data not available")
    return path


@pytest.fixture
def premis_common_dir():
    path = PREMIS_CASES_DIR / "common"
    if not path.exists():
        pytest.skip("premis common data not available")
    return path
