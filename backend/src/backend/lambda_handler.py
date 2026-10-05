from mangum import Mangum

from src.backend.config import load_app_env

# Apply .env.production (Secrets Manager) before importing the app, so settings such as
# HF_HUB_OFFLINE / OMP_NUM_THREADS are in place before torch/transformers are imported.
load_app_env()

from src.backend.app import app  # noqa: E402

asgi_handler = Mangum(app, lifespan="auto")


def handler(event: dict, context: object):
    if event.get("source") == "aws.events" and event.get("detail-type") == "LookFindModelWarmup":
        from src.backend.ml import get_models

        get_models()
        return {"status": "warm"}
    return asgi_handler(event, context)
