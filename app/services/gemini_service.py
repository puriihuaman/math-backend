import json
from typing import TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel

from app.config import get_settings
from app.models.schemas import (
    EvaluationRequest,
    EvaluationResponse,
    ExercisesResponse,
    GenerateExercisesRequest,
    GenerateWeeklyExamRequest,
    WeekPlanResponse,
)


class GeminiRateLimitError(RuntimeError):
    """Indica que se agotó temporalmente la cuota de Gemini."""


T = TypeVar("T", bound=BaseModel)


def _is_rate_limit_error(error: Exception) -> bool:
    text = str(error).lower()
    status_code = getattr(error, "status_code", None) or getattr(error, "code", None)
    return (
        status_code == 429
        or "429" in text
        or "resource exhausted" in text
        or "rate limit" in text
    )


class GeminiService:
    def __init__(self) -> None:
        settings = get_settings()
        self.model = settings.gemini_model
        self.client = genai.Client(api_key=settings.gemini_api_key.get_secret_value())

    async def _generate(self, prompt: str, response_schema: type[T]) -> T:
        try:
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.25,
                    response_mime_type="application/json",
                    response_schema=response_schema,
                ),
            )
        except Exception as exc:
            if _is_rate_limit_error(exc):
                raise GeminiRateLimitError(
                    "La cuota temporal de Gemini se agotó. Espera un momento y vuelve a intentarlo."
                ) from exc
            raise

        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, response_schema):
            return parsed
        text = getattr(response, "text", None)
        if not text:
            raise RuntimeError("Gemini devolvió una respuesta vacía.")
        try:
            return response_schema.model_validate(json.loads(text))
        except (json.JSONDecodeError, ValueError) as exc:
            raise RuntimeError("Gemini devolvió una respuesta con formato inválido.") from exc

    async def generate_week_plan(self, modulo: int, semana: int, material: str) -> WeekPlanResponse:
        prompt = f"""
Eres un docente experto de Matemática Discreta y diseñador de sesiones de 25 minutos.
Crea el plan de estudio de la semana {semana} del módulo {modulo} usando exclusivamente el
material trazable que aparece abajo. Divide en 3 a 5 subtemas secuenciales, de menor a mayor
complejidad. Explica con lenguaje cotidiano, añade analogías concretas y conserva las fórmulas
originales con LaTeX válido entre $...$ o $$...$$. No inventes referencias: cada referencia
debe copiar exactamente el nombre y Página/Diapositiva de una etiqueta del material.
Al serializar JSON, escapa correctamente las barras invertidas de comandos LaTeX
(por ejemplo \\land, \\lor, \\neg, \\forall, \\exists, \\rightarrow, \\subseteq).

MATERIAL:
{material}
"""
        return await self._generate(prompt, WeekPlanResponse)

    async def generate_subtopic_exercises(
        self, request: GenerateExercisesRequest
    ) -> ExercisesResponse:
        prompt = f"""
Genera exactamente {request.cantidad} ejercicios progresivos sobre "{request.titulo_subtema}".
Mantén, en lo posible, la proporción 2 básicos, 2 intermedios y 2 reto por cada bloque de seis:
los básicos son opción múltiple; los intermedios mezclan opción múltiple y respuesta corta; los
reto son respuesta corta. Si la cantidad no es seis, distribuye los niveles proporcionalmente.
Cada opción múltiple debe tener exactamente cuatro opciones y tres distractores plausibles,
basados en errores frecuentes (signos, inclusión, cuantificadores o leyes lógicas), nunca
absurdos. Todo ejercicio debe incluir una pista útil sin revelar la respuesta y una explicación
paso a paso. Usa LaTeX válido y escapa sus barras invertidas al producir JSON.

EXPLICACIÓN: {request.explicacion_simplificada}
CONCEPTOS: {json.dumps(request.conceptos_fundamentales, ensure_ascii=False)}
FÓRMULAS: {json.dumps(request.formulas, ensure_ascii=False)}
"""
        return await self._generate(prompt, ExercisesResponse)

    async def generate_weekly_exam(
        self, request: GenerateWeeklyExamRequest
    ) -> ExercisesResponse:
        subtopics = [subtema.model_dump() for subtema in request.subtemas]
        prompt = f"""
Genera exactamente 10 ejercicios integradores para el examen de la semana "{request.titulo_semana}".
Incluye 4 básicos, 4 intermedios y 2 reto, mezclando todos los subtemas. Los opción múltiple
requieren exactamente cuatro opciones con tres distractores inteligentes, producto de errores
universitarios plausibles. Incluye pista y solución detallada en todos. Usa LaTeX válido y escapa
sus barras invertidas en JSON.

SUBTEMAS:
{json.dumps(subtopics, ensure_ascii=False)}
"""
        return await self._generate(prompt, ExercisesResponse)

    async def evaluate_short_answer(self, request: EvaluationRequest) -> EvaluationResponse:
        prompt = f"""
Evalúa semánticamente la respuesta de un estudiante en Matemática Discreta. Acepta expresiones
equivalentes aunque cambie la sintaxis (por ejemplo p ^ q, p and q y p \\land q), y equivalencias
algebraicas o lógicas válidas. Asigna puntaje entero de 0 a 100 y explica con amabilidad y
precisión qué está bien y qué debe corregirse. No evalúes solo coincidencia textual.

ENUNCIADO: {request.enunciado}
RESPUESTA ESPERADA: {request.respuesta_correcta_esperada}
RESPUESTA DEL USUARIO: {request.respuesta_usuario}
"""
        return await self._generate(prompt, EvaluationResponse)
