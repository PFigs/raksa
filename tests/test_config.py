import json
import os
from pathlib import Path

import pytest

from raksa.config import resolve_token, resolve_condo_id, RaksaConfigError


def test_resolve_token_from_env(monkeypatch):
    monkeypatch.setenv("RAKSA_TOKEN", "tok_from_env")
    assert resolve_token() == "tok_from_env"


def test_resolve_token_from_dotenv(tmp_path, monkeypatch):
    monkeypatch.delenv("RAKSA_TOKEN", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("RAKSA_TOKEN=tok_from_dotenv\n")
    monkeypatch.chdir(tmp_path)
    assert resolve_token() == "tok_from_dotenv"


def test_resolve_token_from_config_file(tmp_path, monkeypatch):
    monkeypatch.delenv("RAKSA_TOKEN", raising=False)
    config_dir = tmp_path / ".config" / "raksa"
    config_dir.mkdir(parents=True)
    token_file = config_dir / "token.json"
    token_file.write_text(json.dumps({"loginToken": "tok_from_file", "userId": "uid1"}))
    monkeypatch.setattr("raksa.config.CONFIG_DIR", config_dir)
    assert resolve_token() == "tok_from_file"


def test_resolve_token_raises_when_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("RAKSA_TOKEN", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("raksa.config.CONFIG_DIR", tmp_path / "nonexistent")
    with pytest.raises(RaksaConfigError, match="No token found"):
        resolve_token()


def test_resolve_condo_id_from_env(monkeypatch):
    monkeypatch.setenv("RAKSA_CONDO_ID", "condo123")
    assert resolve_condo_id() == "condo123"


def test_resolve_condo_id_returns_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("RAKSA_CONDO_ID", raising=False)
    monkeypatch.chdir(tmp_path)
    assert resolve_condo_id() is None
