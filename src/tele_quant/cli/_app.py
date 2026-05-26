from __future__ import annotations

from typing import Annotated

import typer

from tele_quant.logging import configure_logging

app = typer.Typer(no_args_is_help=True, rich_markup_mode="rich")


@app.callback()
def main(
    log_level: Annotated[str, typer.Option("--log-level", help="INFO, DEBUG, WARNING")] = "INFO",
) -> None:
    configure_logging(log_level)
