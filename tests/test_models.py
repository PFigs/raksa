from raksa.models import (
    Contact,
    Contractor,
    ChosenJobs,
    Collateral,
    WorkPerformer,
    ShareholderRenovation,
    ShareholderRenovationWork,
    FaultNotification,
    InformantInfo,
)


def test_contact_from_api():
    c = Contact(id="abc", name="Jukka", phone="+358123", email="j@test.fi")
    assert c.name == "Jukka"
    assert c.id == "abc"


def test_chosen_jobs_defaults_to_none():
    jobs = ChosenJobs()
    assert jobs.kitchen_renovation is None
    assert jobs.heat_pump_installation is None


def test_chosen_jobs_with_values():
    jobs = ChosenJobs(heat_pump_installation=True, kitchen_renovation=False)
    assert jobs.heat_pump_installation is True
    assert jobs.kitchen_renovation is False
    assert jobs.bathroom_renovation is None


def test_shareholder_renovation_from_api_response():
    data = {
        "id": "gig1",
        "title": "ILP asennus",
        "status": "UPCOMING",
        "start_date": "1774904400000",
        "end_date": None,
        "apartment_address": "Raitti 1 H 20",
        "informant": {"id": "c1", "name": "Test", "phone": None, "email": None},
        "chosen_jobs": {"heat_pump_installation": True},
    }
    r = ShareholderRenovation(**data)
    assert r.id == "gig1"
    assert r.chosen_jobs.heat_pump_installation is True
    assert r.informant.name == "Test"


def test_fault_notification_from_api_response():
    data = {
        "id": "fn1",
        "condominium_id": "condo1",
        "fault_description": "Broken light",
        "street_address": "Raitti 1",
        "space": "A6",
        "apartment": "A6",
    }
    f = FaultNotification(**data)
    assert f.fault_description == "Broken light"
    assert f.space == "A6"
