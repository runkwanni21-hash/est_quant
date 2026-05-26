from __future__ import annotations

from tele_quant.logging import console  # noqa: F401
from tele_quant.settings import Settings
from tele_quant.telegram_sender import TelegramSender  # noqa: F401


def _settings() -> Settings:
    settings = Settings()
    settings.ensure_runtime_dirs()
    return settings
