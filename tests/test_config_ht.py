import os
from unittest.mock import patch

import pytest

from raksa.config import RaksaConfigError, resolve_ht_config

_ALL_HT_VARS = {
    "RAKSA_HT_TOKEN": "jwt-token-123",
    "RAKSA_HT_USER_ID": "123456",
    "RAKSA_HT_OFFICE_ID": "131",
    "RAKSA_HT_CONDOMINIUM_ID": "206",
    "RAKSA_HT_CONDOMINIUM_NUMBER": "174",
    "RAKSA_HT_PARENT_FOLDER_ID": "69cb705c3d28bf7d882e43ab",
}

# Patch load_dotenv to prevent .env file from leaking into tests
_no_dotenv = patch("raksa.config.load_dotenv")


def test_resolve_ht_config_from_env():
    with _no_dotenv, patch.dict(os.environ, _ALL_HT_VARS, clear=False):
        config = resolve_ht_config()
    assert config.token == "jwt-token-123"
    assert config.user_id == "123456"
    assert config.office_id == "131"
    assert config.condominium_id == "206"
    assert config.condominium_number == "174"
    assert config.parent_folder_id == "69cb705c3d28bf7d882e43ab"


def test_resolve_ht_config_missing_token():
    with _no_dotenv, patch.dict(os.environ, {}, clear=True):
        with pytest.raises(RaksaConfigError, match="RAKSA_HT_TOKEN"):
            resolve_ht_config()


def test_resolve_ht_config_parent_folder_override():
    env = {k: v for k, v in _ALL_HT_VARS.items() if k != "RAKSA_HT_PARENT_FOLDER_ID"}
    with _no_dotenv, patch.dict(os.environ, env, clear=True):
        config = resolve_ht_config(parent_folder_id_override="override123")
    assert config.parent_folder_id == "override123"


def test_resolve_ht_config_missing_parent_folder():
    env = {k: v for k, v in _ALL_HT_VARS.items() if k != "RAKSA_HT_PARENT_FOLDER_ID"}
    with _no_dotenv, patch.dict(os.environ, env, clear=True):
        with pytest.raises(RaksaConfigError, match="RAKSA_HT_PARENT_FOLDER_ID"):
            resolve_ht_config()
