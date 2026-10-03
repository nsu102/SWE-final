from mangum import Mangum

from src.backend.app import app

handler = Mangum(app, lifespan="auto")
