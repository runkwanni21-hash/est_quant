from __future__ import annotations

# Import sub-modules as side-effects so every @app.command() decorator fires
# and registers each command on the shared Typer app object.
from tele_quant.cli import (  # noqa: F401
    _analysis,
    _backlog,
    _briefing,
    _core,
    _dashboard,
    _ops,
    _relation,
    _sector,
)

# Re-export app so that `from tele_quant.cli import app` continues to work.
from tele_quant.cli._app import app

# Re-export helpers/classes that tests patch/import directly from `tele_quant.cli`.
# (The original cli.py had these as module-level names.)
from tele_quant.cli._briefing import weekly
from tele_quant.cli._common import _settings, console
from tele_quant.cli._core import once  # tests import tele_quant.cli.once
from tele_quant.cli._ops import lint_report
from tele_quant.pipeline import TeleQuantPipeline  # tests patch tele_quant.cli.TeleQuantPipeline

__all__ = ["TeleQuantPipeline", "_settings", "app", "console", "lint_report", "once", "weekly"]
