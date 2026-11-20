import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.routers.study import router as study_router
from app.services.gemini_service import (
    GeminiAPIError,
    GeminiRateLimitError,
    GeminiResponseValidationError,
    GeminiUnavailableError,
)

logger = logging.getLogger(__name__)
settings = get_settings()
app = FastAPI(title="DiscretaFlow Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(GeminiRateLimitError)
async def gemini_rate_limit_handler(
    request: Request, exc: GeminiRateLimitError
) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit",
            "message": str(exc),
            "retryable": True,
        },
    )


@app.exception_handler(GeminiUnavailableError)
async def gemini_unavailable_handler(
    request: Request, exc: GeminiUnavailableError
) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "error": "gemini_unavailable",
            "message": str(exc),
            "retryable": True,
        },
    )


@app.exception_handler(GeminiAPIError)
async def gemini_api_error_handler(
    request: Request, exc: GeminiAPIError
) -> JSONResponse:
    status_code = exc.status_code if 400 <= exc.status_code <= 599 else 502
    return JSONResponse(
        status_code=status_code,
        content={
            "error": "gemini_api_error",
            "message": "Gemini rechazó la solicitud.",
            "detail": exc.detail,
        },
    )


@app.exception_handler(GeminiResponseValidationError)
async def gemini_validation_error_handler(
    request: Request, exc: GeminiResponseValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={
            "error": "invalid_gemini_response",
            "message": "Gemini devolvió una respuesta incompatible.",
            "detail": str(exc),
        },
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"error": "invalid_input", "message": str(exc)},
    )


@app.exception_handler(RequestValidationError)
async def request_validation_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": "validation_error", "message": "Los datos enviados no son válidos.", "details": exc.errors()},
    )


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Error no controlado en %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": "internal_error", "message": "Ocurrió un error interno."},
    )


@app.get("/api/v1/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "DiscretaFlow Backend"}


app.include_router(study_router)
