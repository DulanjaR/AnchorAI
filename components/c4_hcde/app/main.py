from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse

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


DEMO = Path(__file__).parent / "static" / "demo.html"


@app.get("/demo", include_in_schema=False)
def demo() -> FileResponse:
    return FileResponse(DEMO)


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse("/demo")
