import json
import os
from pathlib import Path

from dotenv import load_dotenv, find_dotenv


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
