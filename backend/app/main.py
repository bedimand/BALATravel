from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.deps import ensure_local_user
from app.api.routes import agent, share, trips, users
from app.core.config import get_settings
from app.core.database import Base, SessionLocal, engine, ensure_sqlite_schema


settings = get_settings()
Base.metadata.create_all(bind=engine)
ensure_sqlite_schema()
with SessionLocal() as db:
    ensure_local_user(db)

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router, prefix=settings.api_prefix)
app.include_router(trips.router, prefix=settings.api_prefix)
app.include_router(agent.router, prefix=settings.api_prefix)
app.include_router(share.router, prefix=settings.api_prefix)


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
