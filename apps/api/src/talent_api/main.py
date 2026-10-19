from fastapi import Depends, FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .candidate_routes import router as candidate_router
from .config import settings
from .db import get_db
from .hr_routes import router as hr_router
from .request_limits import CandidateRequestLimits

app = FastAPI(
    title="Talent Review API",
    version="0.2.0",
    description="Candidate interviews and authenticated HR review. Use CandidateLink for personal invitations and HRSession for HR endpoints. HR sign-in is explicitly mocked for local development. OpenAI runs only in the separate background worker; audio requires human review.",
    swagger_ui_parameters={"persistAuthorization": False},
)
app.include_router(candidate_router)
app.include_router(hr_router)


@app.middleware("http")
async def private_hr_responses(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/hr/"):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
    return response


app.add_middleware(CandidateRequestLimits)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_origin],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "Idempotency-Key"],
    allow_credentials=True,
)


@app.exception_handler(RequestValidationError)
def invalid_request(request, exc):
    # Never echo submitted credentials or answer contents in validation errors.
    errors = [{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
    return JSONResponse(status_code=422, content=jsonable_encoder({"detail": errors}))


@app.exception_handler(SQLAlchemyError)
def database_unavailable(request, exc):
    return JSONResponse(
        status_code=503, content={"detail": "Database unavailable; retry the request"}
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/health/ready")
def ready(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Database unavailable") from None
    return {"status": "ready"}
