import typer

from raksa.commands.auth import app as auth_app
from raksa.commands.renovations import app as renovations_app
from raksa.commands.faults import app as faults_app

app = typer.Typer(
    name="raksa",
    help="CLI tool for housing company management systems",
    no_args_is_help=True,
)
app.add_typer(auth_app, name="auth")
app.add_typer(renovations_app, name="renovations")
app.add_typer(faults_app, name="faults")
