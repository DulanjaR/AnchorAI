from fastapi import FastAPI

from .api import routes
from .db.models import make_session_factory

app = FastAPI(title="Anchor AI - HCDE", version="0.2.0",
              description="Human Capability Development Engine: decides how much AI help to give, explains why, "
                          "generates the reply with a locally fine-tuned model, and tracks borrowed vs built capability.")
routes.SessionFactory = make_session_factory()
app.include_router(routes.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "component": "hcde"}
