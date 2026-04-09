"""Live API integration tests against EstateApp.

Read tests run against the real API.
Write tests are prepared but marked with @pytest.mark.submit -- run them with:
    pytest -m submit tests/test_api_live.py

All tests skip if RAKSA_TOKEN is not configured.
"""
import uuid

import pytest


# ---------------------------------------------------------------------------
# Read operations (safe to run)
# ---------------------------------------------------------------------------

class TestListRenovations:
    def test_returns_list(self, live_client, condo_id):
        renovations = live_client.list_renovations(condo_id)
        assert isinstance(renovations, list)
        assert len(renovations) >= 1

    def test_renovation_has_expected_fields(self, live_client, condo_id):
        renovations = live_client.list_renovations(condo_id)
        r = renovations[0]
        assert r.id
        assert r.shareholder_renovation_work is not None

    def test_renovation_has_chosen_jobs_field(self, live_client, condo_id):
        renovations = live_client.list_renovations(condo_id)
        r = renovations[0]
        srw = r.shareholder_renovation_work
        assert srw.chosen_jobs is not None


class TestGetRenovation:
    def test_get_known_gig(self, live_client, known_gig_id):
        r = live_client.get_renovation(known_gig_id)
        assert r.id == known_gig_id

    def test_known_gig_is_heat_pump(self, live_client, known_gig_id):
        r = live_client.get_renovation(known_gig_id)
        srw = r.shareholder_renovation_work
        assert srw is not None
        assert srw.chosen_jobs.heat_pump_installation is True

    def test_known_gig_has_contractor(self, live_client, known_gig_id):
        r = live_client.get_renovation(known_gig_id)
        srw = r.shareholder_renovation_work
        assert len(srw.contractors) >= 1
        contractor = srw.contractors[0]
        assert contractor.company_name
        assert contractor.company_business_id

    def test_known_gig_has_address(self, live_client, known_gig_id):
        r = live_client.get_renovation(known_gig_id)
        srw = r.shareholder_renovation_work
        assert srw.apartment_address
        assert "Asuntamaanraitti" in srw.apartment_address


class TestListFaults:
    def test_returns_list(self, live_client, condo_id):
        faults = live_client.list_faults(condo_id)
        assert isinstance(faults, list)


# ---------------------------------------------------------------------------
# Write operations (prepared, not run by default)
# ---------------------------------------------------------------------------

def _make_test_renovation_input(condo_id: str) -> dict:
    """Build a renovation input modeled after the existing heat pump gig.

    Uses fake data only -- no PII.
    """
    return {
        "condominiumId": condo_id,
        "type": "shareholderRenovationWork",
        "status": "UPCOMING",
        "startDate": str(int(1774904400 * 1000)),  # same epoch as existing gig
        "endDate": str(int(1774904400 * 1000)),
        "title": "Raksa CLI testitapaus, Z99",
        "shareholderRenovationWork": {
            "apartmentAddress": "Asuntamaanraitti 1 Z 99",
            "informant": {
                "_id": str(uuid.uuid4()),
                "name": "Testi Testaaja",
                "phone": "+358401234567",
                "email": "testi@example.com",
            },
            "informantIsApartmentOwner": True,
            "workDescription": (
                "Tämä on Raksa CLI:n automaattinen testitapaus. "
                "Ilmalämpöpumpun asennus testiasuntoon Z99. "
                "Tämän voi poistaa."
            ),
            "hazardousSubstanceSurveysDone": None,
            "renovationRequiresFireWork": False,
            "contractors": [
                {
                    "_id": str(uuid.uuid4()),
                    "companyName": "Testi Asennus Oy",
                    "companyBusinessId": "1234567-0",
                    "contact": {
                        "_id": str(uuid.uuid4()),
                        "name": "Testi Asennus Oy",
                        "phone": "+358409876543",
                        "email": "asennus@example.com",
                    },
                }
            ],
            "chosenJobs": {
                "heatPumpInstallation": True,
            },
            "collateral": {
                "authorizedToSubmitRenovationWork": True,
                "understandContractorLiability": True,
                "infoProvidedIsAccurate": True,
                "acceptModificationTerms": True,
                "awareOfProcessingAfterPayment": True,
            },
        },
    }


def _make_test_fault_input() -> dict:
    """Build a fault notification input with fake data."""
    return {
        "faultDescription": (
            "Raksa CLI testitapaus. Testi vikailmoitus asunnosta Z99. "
            "Tämän voi poistaa."
        ),
        "space": "Z99",
        "apartment": "Z99",
        "streetAddress": "Asuntamaanraitti 1",
        "contactName": "Testi Testaaja",
    }


@pytest.mark.submit
class TestCreateRenovation:
    """Create a renovation gig via the API.

    Run with: pytest -m submit tests/test_api_live.py::TestCreateRenovation -v
    """

    def test_create_renovation_gig(self, live_client, condo_id):
        gig_input = _make_test_renovation_input(condo_id)
        gig_id = live_client.create_renovation(gig_input)
        assert gig_id is not None
        assert isinstance(gig_id, str)
        print(f"\n  Created renovation gig: {gig_id}")

    def test_created_gig_is_readable(self, live_client, condo_id):
        gig_input = _make_test_renovation_input(condo_id)
        gig_id = live_client.create_renovation(gig_input)

        fetched = live_client.get_renovation(gig_id)
        assert fetched.id == gig_id
        srw = fetched.shareholder_renovation_work
        assert srw is not None
        assert srw.chosen_jobs.heat_pump_installation is True
        assert "Z 99" in srw.apartment_address or "Z99" in srw.apartment_address
        print(f"\n  Verified gig {gig_id} is readable")


@pytest.mark.submit
class TestCreateFault:
    """Create a fault notification via the API.

    Run with: pytest -m submit tests/test_api_live.py::TestCreateFault -v
    """

    def test_create_fault_notification(self, live_client, condo_id):
        fault_input = _make_test_fault_input()
        fault_id = live_client.create_fault(condo_id, fault_input)
        assert fault_id is not None
        assert isinstance(fault_id, str)
        print(f"\n  Created fault notification: {fault_id}")
