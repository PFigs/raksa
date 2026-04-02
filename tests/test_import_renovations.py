from pathlib import Path

import yaml

from raksa.commands.renovations import load_renovation_cases


def test_load_renovation_cases_from_hive(tmp_path):
    year_dir = tmp_path / "year=2021" / "house=G18"
    year_dir.mkdir(parents=True)
    case_file = year_dir / "2021-01-01_12345.yaml"
    case_file.write_text(yaml.dump({
        "Title": "12345",
        "CreatedOn": "2021-01-01T10:00:00",
        "Id": "abc",
        "HasFiles": False,
        "RequestType": {"Label": "Huoneistomuutosilmoitus", "Value": 100000000},
        "Space": {"Id": "s1", "LogicalName": "uds_space", "Name": "G18"},
        "BuildingAddress": "Raitti 1",
        "ContactPerson": {"Id": "c1", "LogicalName": "contact", "Name": "Test Person"},
        "Cooperative": {"Id": "co1", "LogicalName": "account", "Name": "Test Oy"},
        "RenovationTypes": [{
            "Id": "r1",
            "OrganizationName": "Builder Oy",
            "BusinessId": "1234567-8",
            "Description": "Floor work",
            "Type": {"Label": "Lattiamateriaalin vaihtaminen", "Value": 1},
            "ExecutorType": {"Label": "Suomalainen yritys", "Value": 752560000},
            "Email": None, "MobilePhone": None, "FirstName": None,
            "LastName": None, "FullName": None, "Birthday": None,
            "ForeignRegistrationNumber": None,
        }],
        "State": {"Label": "Ratkaistu", "Value": 1},
        "Status": {"Label": "Valmis", "Value": 752560003},
    }))
    # Chat file that should be skipped
    chat_file = year_dir / "2021-01-01_12345_chat.yaml"
    chat_file.write_text("- Message: hello")

    # Non-renovation case that should be skipped
    common_file = year_dir / "2021-02-01_99999.yaml"
    common_file.write_text(yaml.dump({
        "Title": "99999",
        "CreatedOn": "2021-02-01T10:00:00",
        "Id": "def",
        "HasFiles": False,
        "RequestType": {"Label": "Palvelupyyntö", "Value": 752560013},
        "Space": {"Id": "s1", "LogicalName": "uds_space", "Name": "G18"},
        "State": {"Label": "Ratkaistu", "Value": 1},
        "Status": {"Label": "Valmis", "Value": 752560003},
    }))

    cases = load_renovation_cases(tmp_path)
    assert len(cases) == 1
    assert cases[0].title == "12345"
    assert cases[0].is_renovation is True
