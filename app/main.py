from datetime import datetime, timezone

from fastapi import FastAPI

from app.database import Base, engine
import app.models  # noqa: F401 — ensures models are registered before create_all
from app.routers import ingest, insights, members

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Member Intelligence API")

app.include_router(ingest.router)
app.include_router(members.router)
app.include_router(members.segments_router)
app.include_router(insights.router)


@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}
