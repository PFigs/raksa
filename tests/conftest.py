from pathlib import Path

import pytest

from raksa.config import resolve_token, resolve_base_url, RaksaConfigError
from raksa.client import EstateAppClient


PREMIS_CASES_DIR = Path("/home/silva/home projects/premis/cases")
CONDO_ID = "kJXwXieRhQjFgRSQ9"
KNOWN_GIG_ID = "69cd4f6246dd8c9ae4779f70"


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
    return CONDO_ID


@pytest.fixture
def known_gig_id():
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
