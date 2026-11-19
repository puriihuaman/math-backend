from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile

from app.models.schemas import (
    EvaluationRequest,
    EvaluationResponse,
    ExercisesResponse,
    GenerateExercisesRequest,
    GenerateWeeklyExamRequest,
    WeekPlanResponse,
)
from app.services.file_parser import extract_material
from app.services.gemini_service import GeminiService

router = APIRouter(prefix="/api/v1/study", tags=["study"])


@router.post("/process-week-material", response_model=WeekPlanResponse)
async def process_week_material(
    modulo: Annotated[int, Form(ge=1, le=4)],
    semana: Annotated[int, Form(ge=1, le=4)],
    files: Annotated[list[UploadFile], File(...)],
) -> WeekPlanResponse:
    material = await extract_material(files)
    return await GeminiService().generate_week_plan(modulo, semana, material)


@router.post("/generate-exercises", response_model=ExercisesResponse)
async def generate_exercises(request: GenerateExercisesRequest) -> ExercisesResponse:
    return await GeminiService().generate_subtopic_exercises(request)


@router.post("/generate-weekly-exam", response_model=ExercisesResponse)
async def generate_weekly_exam(request: GenerateWeeklyExamRequest) -> ExercisesResponse:
    return await GeminiService().generate_weekly_exam(request)


@router.post("/evaluate-short-answer", response_model=EvaluationResponse)
async def evaluate_short_answer(request: EvaluationRequest) -> EvaluationResponse:
    return await GeminiService().evaluate_short_answer(request)
