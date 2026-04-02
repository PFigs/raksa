import os

import typer

from raksa.config import save_token

app = typer.Typer(help="Authentication management", no_args_is_help=True)


def _update_env_file(token: str) -> None:
    env_path = ".env"
    line = f"RAKSA_TOKEN={token}\n"

    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            lines = f.readlines()
        updated = False
        for i, existing in enumerate(lines):
            if existing.startswith("RAKSA_TOKEN="):
                lines[i] = line
                updated = True
                break
        if not updated:
            lines.append(line)
        with open(env_path, "w") as f:
            f.writelines(lines)
    else:
        with open(env_path, "w") as f:
            f.write(line)


@app.command()
def setup():
    """Set up EstateApp authentication credentials via browser."""
    from raksa.auth_server import run_auth_server

    typer.echo("Opening browser for authentication setup...")
    result = run_auth_server()
    if result:
        login_token, user_id = result
        path = save_token(login_token, user_id)
        _update_env_file(login_token)
        typer.echo(f"Token saved to {path} and .env")
    else:
        typer.echo("Setup cancelled.", err=True)
        raise typer.Exit(1)
