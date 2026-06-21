from typer.testing import CliRunner

from actionlineage import __version__
from actionlineage.cli import app

runner = CliRunner()


def test_version_command() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_doctor_command() -> None:
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "actionlineage=" in result.stdout
    assert "python=" in result.stdout
