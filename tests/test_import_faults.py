from pathlib import Path

import yaml

from raksa.commands.faults import load_fault_cases


def test_load_fault_cases_from_hive(tmp_path):
    year_dir = tmp_path / "year=2019" / "house=A6"
    year_dir.mkdir(parents=True)
    case_file = year_dir / "2019-11-17_1029483.yaml"
    case_file.write_text(yaml.dump({
        "Title": "1029483",
        "CreatedOn": "2019-11-17T20:22:11",
        "Id": "abc",
        "HasFiles": False,
        "Description": "Ulko-oven valo palanut.",
        "Space": {"Id": "s1", "LogicalName": "uds_space", "Name": "A6"},
        "Cooperative": {"Id": "co1", "LogicalName": "account", "Name": "Test Oy"},
        "RequestType": {"Label": "Palvelupyyntö", "Value": 752560013},
        "CaseLevel1": {"Label": "Vikailmoitus", "Value": 752560000},
        "State": {"Label": "Ratkaistu", "Value": 1},
        "Status": {"Label": "Valmis", "Value": 752560003},
    }))
    # Renovation case that should be skipped
    reno_file = year_dir / "2019-12-01_99999.yaml"
    reno_file.write_text(yaml.dump({
        "Title": "99999",
        "CreatedOn": "2019-12-01T10:00:00",
        "Id": "def",
        "HasFiles": False,
        "RequestType": {"Label": "Huoneistomuutosilmoitus", "Value": 100000000},
        "Space": {"Id": "s1", "LogicalName": "uds_space", "Name": "A6"},
        "BuildingAddress": "Raitti 1",
        "ContactPerson": {"Id": "c1", "LogicalName": "contact", "Name": "Test"},
        "Cooperative": {"Id": "co1", "LogicalName": "account", "Name": "Test Oy"},
        "RenovationTypes": [],
        "State": {"Label": "Ratkaistu", "Value": 1},
        "Status": {"Label": "Valmis", "Value": 752560003},
    }))

    cases = load_fault_cases(tmp_path)
    assert len(cases) == 1
    assert cases[0].title == "1029483"
    assert cases[0].is_renovation is False
