import os

import typer

from raksa.config import save_token

app = typer.Typer(help="Authentication management", no_args_is_help=True)


def _update_env_var(key: str, value: str) -> None:
    env_path = ".env"
    line = f"{key}={value}\n"

    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            lines = f.readlines()
        updated = False
        for i, existing in enumerate(lines):
            if existing.startswith(f"{key}="):
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
        _update_env_var("RAKSA_TOKEN", login_token)
        typer.echo(f"Token saved to {path} and .env")
    else:
        typer.echo("Setup cancelled.", err=True)
        raise typer.Exit(1)


@app.command("setup-ht")
def setup_ht():
    """Set up Huoneistotieto authentication token via browser."""
    from raksa.ht_auth_server import run_ht_auth_server

    typer.echo("Opening browser for Huoneistotieto auth setup...")
    token = run_ht_auth_server()
    if token:
        _update_env_var("RAKSA_HT_TOKEN", token)
        typer.echo("Token saved to .env (RAKSA_HT_TOKEN)")
    else:
        typer.echo("Setup cancelled.", err=True)
        raise typer.Exit(1)
