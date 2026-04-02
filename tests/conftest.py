from pathlib import Path

import pytest


PREMIS_CASES_DIR = Path("/home/silva/home projects/premis/cases")


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
