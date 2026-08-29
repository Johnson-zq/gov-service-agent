import logging

from fastapi import FastAPI

from gov_service_agent.logging_config import setup_logging
from gov_service_agent.middleware.request_context import RequestContextMiddleware
from gov_service_agent.settings import get_settings

settings = get_settings()
setup_logging(settings)

app = FastAPI(title="gov-service-agent")
app.add_middleware(RequestContextMiddleware)


@app.get("/health")
def health():
    return {"status": "ok"}


logging.getLogger("gov_service_agent").info(
    "message=application_initialized app_env=%s log_level=%s",
    settings.app_env.value,
    settings.log_level.value,
)
