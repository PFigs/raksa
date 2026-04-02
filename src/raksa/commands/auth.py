import json

import typer

from raksa.config import save_token

app = typer.Typer(help="Authentication management", no_args_is_help=True)


@app.command()
def setup():
    """Set up EstateApp authentication credentials."""
    typer.echo("To get your token, open app.estateapp.com in your browser,")
    typer.echo("open DevTools (F12), go to Console, and run:\n")
    typer.echo('  JSON.stringify({')
    typer.echo('    loginToken: localStorage.getItem("Meteor.loginToken"),')
    typer.echo('    userId: localStorage.getItem("Meteor.userId")')
    typer.echo('  })\n')

    raw = typer.prompt("Paste the JSON output here")
    try:
        data = json.loads(raw.strip().strip("'\""))
    except json.JSONDecodeError:
        typer.echo("Error: invalid JSON. Please try again.", err=True)
        raise typer.Exit(1)

    login_token = data.get("loginToken")
    user_id = data.get("userId")
    if not login_token or not user_id:
        typer.echo("Error: JSON must contain 'loginToken' and 'userId' keys.", err=True)
        raise typer.Exit(1)

    path = save_token(login_token, user_id)
    typer.echo(f"Token saved to {path}")
