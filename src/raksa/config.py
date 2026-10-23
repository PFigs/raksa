import json
import os
from pathlib import Path

from dotenv import load_dotenv, find_dotenv
from pydantic import BaseModel


CONFIG_DIR = Path.home() / ".config" / "raksa"


class RaksaConfigError(Exception):
    pass


def resolve_token() -> str:
    load_dotenv(dotenv_path=find_dotenv(usecwd=True))

    token = os.environ.get("RAKSA_TOKEN")
    if token:
        return token

    token_file = CONFIG_DIR / "token.json"
    if token_file.exists():
        data = json.loads(token_file.read_text())
        token = data.get("loginToken")
        if token:
            return token

    raise RaksaConfigError(
        "No token found. Set RAKSA_TOKEN in .env, as an env var, "
        "or run 'raksa auth setup'."
    )


def resolve_condo_id() -> str | None:
    load_dotenv(dotenv_path=find_dotenv(usecwd=True))
    return os.environ.get("RAKSA_CONDO_ID")


def resolve_base_url() -> str:
    load_dotenv(dotenv_path=find_dotenv(usecwd=True))
    return os.environ.get("RAKSA_BASE_URL", "https://app.estateapp.com")


def save_token(login_token: str, user_id: str) -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    token_file = CONFIG_DIR / "token.json"
    token_file.write_text(json.dumps({"loginToken": login_token, "userId": user_id}, indent=2))
    return token_file


class HuoneistotietoConfig(BaseModel):
    token: str
    user_id: str
    office_id: str
    condominium_id: str
    condominium_number: str
    parent_folder_id: str = ""


def resolve_ht_config(
    parent_folder_id_override: str | None = None,
    require_parent_folder: bool = True,
) -> HuoneistotietoConfig:
    load_dotenv(dotenv_path=find_dotenv(usecwd=True))

    required = {
        "RAKSA_HT_TOKEN": "token",
        "RAKSA_HT_USER_ID": "user_id",
        "RAKSA_HT_OFFICE_ID": "office_id",
        "RAKSA_HT_CONDOMINIUM_ID": "condominium_id",
        "RAKSA_HT_CONDOMINIUM_NUMBER": "condominium_number",
    }
    values = {}
    for env_var, field in required.items():
        val = os.environ.get(env_var)
        if not val:
            raise RaksaConfigError(f"Missing required env var: {env_var}")
        values[field] = val

    values["parent_folder_id"] = (
        parent_folder_id_override
        or os.environ.get("RAKSA_HT_PARENT_FOLDER_ID")
        or ""
    )

    if require_parent_folder and not values["parent_folder_id"]:
        raise RaksaConfigError(
            "Missing required env var: RAKSA_HT_PARENT_FOLDER_ID "
            "(or pass --parent-folder-id)"
        )

    return HuoneistotietoConfig(**values)
