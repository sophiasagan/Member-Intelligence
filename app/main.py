from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI

from app.database import Base, engine
import app.models  # noqa: F401 — ensures models are registered before create_all
from app.routers import ingest, insights, members


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs after uvicorn binds to the port — safe for slow DB connections
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Member Intelligence API", lifespan=lifespan)

app.include_router(ingest.router)
app.include_router(members.router)
app.include_router(members.segments_router)
app.include_router(insights.router)


@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}
