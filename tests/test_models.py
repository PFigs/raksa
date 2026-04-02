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


from raksa.models import (
    YAMLCase,
    YAMLEntityRef,
    YAMLLabelValue,
    YAMLRenovationType,
    YAMLExecutorType,
    YAMLTypeLabelValue,
)


SAMPLE_REPAIR_YAML = {
    "Title": "1043543",
    "CreatedOn": "2020-10-29T15:52:59",
    "ModifiedOn": "2020-11-23T10:52:10",
    "BuildingAddress": "Asuntamaanraitti 1 B",
    "ContactPerson": {"Id": "cp1", "LogicalName": "contact", "Name": "Laura Silva"},
    "Space": {"Id": "sp1", "LogicalName": "uds_space", "Name": "G18"},
    "Cooperative": {"Id": "co1", "LogicalName": "account", "Name": "Asunto Oy Vuoreksen Apollo, Tampere"},
    "EstimatedTiming": "09.11.2020 - 20.11.2020",
    "PublicDescription": "Lattian vaihto ja tasoittaminen",
    "RenovationTypes": [
        {
            "Id": "rt1",
            "OrganizationName": "ASUA GROUP OY",
            "BusinessId": "2474742-4",
            "Description": "Lattian vaihto",
            "Type": {"Label": "Muu muutostyö", "Value": 752560019},
            "ExecutorType": {"Label": "Suomalainen yritys", "Value": 752560000},
            "Email": None,
            "MobilePhone": None,
            "FirstName": None,
            "LastName": None,
            "FullName": None,
            "Birthday": None,
            "ForeignRegistrationNumber": None,
        }
    ],
    "RequestType": {"Label": "Huoneistomuutosilmoitus", "Value": 100000000},
    "State": {"Label": "Ratkaistu", "Value": 1},
    "Status": {"Label": "Valmis", "Value": 752560003},
    "HasFiles": True,
    "Id": "case1",
}


def test_yaml_case_parses_repair():
    case = YAMLCase(**SAMPLE_REPAIR_YAML)
    assert case.title == "1043543"
    assert case.space.name == "G18"
    assert case.contact_person.name == "Laura Silva"
    assert len(case.renovation_types) == 1
    assert case.renovation_types[0].organization_name == "ASUA GROUP OY"
    assert case.is_renovation is True


def test_yaml_case_to_renovation_input():
    case = YAMLCase(**SAMPLE_REPAIR_YAML)
    renovation = case.to_renovation_input(condo_id="condo123")
    assert renovation["condominiumId"] == "condo123"
    assert renovation["type"] == "shareholderRenovationWork"
    assert renovation["status"] == "UPCOMING"
    srw = renovation["shareholderRenovationWork"]
    assert srw["apartmentAddress"] == "Asuntamaanraitti 1 B G18"
    assert srw["chosenJobs"]["otherChanges"] is True
    assert len(srw["contractors"]) == 1
    assert srw["contractors"][0]["companyName"] == "ASUA GROUP OY"
    assert srw["contractors"][0]["companyBusinessId"] == "2474742-4"


def test_yaml_case_parses_estimated_timing():
    case = YAMLCase(**SAMPLE_REPAIR_YAML)
    renovation = case.to_renovation_input(condo_id="c1")
    assert renovation["startDate"] is not None
    assert renovation["endDate"] is not None


def test_yaml_case_heat_pump_maps_correctly():
    data = {**SAMPLE_REPAIR_YAML}
    data["RenovationTypes"] = [
        {**SAMPLE_REPAIR_YAML["RenovationTypes"][0], "Type": {"Label": "Ilmalämpöpumpun asennus", "Value": 1}},
    ]
    case = YAMLCase(**data)
    renovation = case.to_renovation_input(condo_id="c1")
    assert renovation["shareholderRenovationWork"]["chosenJobs"]["heatPumpInstallation"] is True


SAMPLE_COMMON_YAML = {
    "Title": "1029483",
    "CreatedOn": "2019-11-17T20:22:11",
    "ModifiedOn": "2020-03-30T09:50:21",
    "Description": "Ulko-oven yläpuolella oleva ulko valo on palanut.",
    "Space": {"Id": "sp1", "LogicalName": "uds_space", "Name": "A6"},
    "Cooperative": {"Id": "co1", "LogicalName": "account", "Name": "Asunto Oy Vuoreksen Apollo, Tampere"},
    "CaseLevel1": {"Label": "Tiedustelu", "Value": 752560002},
    "State": {"Label": "Ratkaistu", "Value": 1},
    "Status": {"Label": "Valmis", "Value": 752560003},
    "HasFiles": False,
    "Id": "case2",
    "RequestType": {"Label": "Palvelupyyntö", "Value": 752560013},
}


def test_yaml_case_parses_common():
    case = YAMLCase(**SAMPLE_COMMON_YAML)
    assert case.title == "1029483"
    assert case.is_renovation is False


def test_yaml_case_to_fault_input():
    case = YAMLCase(**SAMPLE_COMMON_YAML)
    fault = case.to_fault_input()
    assert fault["faultDescription"] == "Ulko-oven yläpuolella oleva ulko valo on palanut."
    assert fault["space"] == "A6"
