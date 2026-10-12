from fastapi import FastAPI

app = FastAPI(title="Anchor AI - HCDE", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "component": "hcde"}
