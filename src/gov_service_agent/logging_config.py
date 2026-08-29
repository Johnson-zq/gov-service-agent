"""Package logging setup for gov_service_agent (stdlib only)."""

from __future__ import annotations

import logging
import sys

from gov_service_agent.settings import Settings

APP_LOGGER_NAME = "gov_service_agent"
ACCESS_LOGGER_NAME = "gov_service_agent.access"

_HANDLER_OWNED_ATTR = "_gov_service_agent_owned"

_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def _map_level(settings: Settings) -> int:
    return getattr(logging, settings.log_level.value)


def setup_logging(settings: Settings) -> None:
    """
    Configure gov_service_agent loggers only.

    Idempotent: does not attach duplicate owned handlers.
    Does not call basicConfig or mutate root / uvicorn loggers.
    """
    level = _map_level(settings)
    formatter = logging.Formatter(_FORMAT)

    app_logger = logging.getLogger(APP_LOGGER_NAME)
    app_logger.setLevel(level)
    app_logger.propagate = False

    owned = [
        handler
        for handler in app_logger.handlers
        if getattr(handler, _HANDLER_OWNED_ATTR, False)
    ]
    if owned:
        for handler in owned:
            handler.setLevel(level)
            handler.setFormatter(formatter)
    else:
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(level)
        handler.setFormatter(formatter)
        setattr(handler, _HANDLER_OWNED_ATTR, True)
        app_logger.addHandler(handler)

    access_logger = logging.getLogger(ACCESS_LOGGER_NAME)
    access_logger.setLevel(level)
    # No dedicated handler; records propagate to parent gov_service_agent.
    access_logger.propagate = True
