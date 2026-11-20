import json
from copy import deepcopy
from typing import TypeVar

from google import genai
from google.genai import errors, types
from pydantic import BaseModel, ValidationError

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


class GeminiAPIError(RuntimeError):
    """Error legible de la API de Gemini conservando su código HTTP."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class GeminiResponseValidationError(RuntimeError):
    """Indica que Gemini no devolvió datos compatibles con el esquema."""


T = TypeVar("T", bound=BaseModel)


UNSUPPORTED_SCHEMA_KEYS = {
    "additionalProperties",
    "additional_properties",
    "$schema",
    "default",
    "title",
}


def build_gemini_schema(pydantic_model: type[BaseModel]) -> dict:
    """Convierte el JSON Schema Pydantic a un esquema compatible con Gemini."""
    raw_schema = pydantic_model.model_json_schema()
    defs = raw_schema.pop("$defs", {})

    def resolve(node: object) -> object:
        if isinstance(node, list):
            return [resolve(item) for item in node]
        if not isinstance(node, dict):
            return node

        if "$ref" in node:
            ref = node["$ref"]
            if isinstance(ref, str) and ref.startswith("#/$defs/"):
                name = ref.removeprefix("#/$defs/")
                if name in defs:
                    resolved = resolve(deepcopy(defs[name]))
                    siblings = {key: resolve(value) for key, value in node.items() if key != "$ref"}
                    if isinstance(resolved, dict):
                        resolved.update(siblings)
                    return resolved

        resolved_node = {}
        for key, value in node.items():
            if key in UNSUPPORTED_SCHEMA_KEYS:
                continue
            if key == "anyOf":
                branches = value if isinstance(value, list) else []
                resolved_branches = [resolve(branch) for branch in branches]
                non_null = [
                    branch
                    for branch in resolved_branches
                    if not (isinstance(branch, dict) and branch.get("type") == "null")
                ]
                if len(resolved_branches) == 2 and len(non_null) == 1:
                    branch = deepcopy(non_null[0])
                    if isinstance(branch, dict):
                        branch["nullable"] = True
                        resolved_node.update(branch)
                        continue
                continue
            resolved_node[key] = resolve(value)
        return resolved_node

    resolved = resolve(raw_schema)
    if not isinstance(resolved, dict):
        raise RuntimeError("El esquema Pydantic no pudo convertirse a un objeto JSON.")
    resolved.pop("$defs", None)
    return resolved


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
                    response_schema=build_gemini_schema(response_schema),
                ),
            )
        except (errors.APIError, errors.ClientError) as exc:
            status_code = int(getattr(exc, "code", 500) or 500)
            detail = getattr(exc, "message", None) or str(exc)
            if status_code == 429 or _is_rate_limit_error(exc):
                raise GeminiRateLimitError(
                    "La cuota temporal de Gemini se agotó. Espera un momento y vuelve a intentarlo."
                ) from exc
            raise GeminiAPIError(status_code, detail) from exc
        except Exception as exc:
            if _is_rate_limit_error(exc):
                raise GeminiRateLimitError(
                    "La cuota temporal de Gemini se agotó. Espera un momento y vuelve a intentarlo."
                ) from exc
            raise

        text = getattr(response, "text", None)
        if not text:
            raise RuntimeError("Gemini devolvió una respuesta vacía.")
        try:
            return response_schema.model_validate_json(text)
        except ValidationError as exc:
            raise GeminiResponseValidationError(
                f"Gemini devolvió una respuesta incompatible con el esquema: {exc}"
            ) from exc

    async def generate_week_plan(self, modulo: int, semana: int, material: str) -> WeekPlanResponse:
        prompt = f"""
Eres un docente experto de Matemática Discreta y diseñador de sesiones de 25 minutos.
Crea el plan de estudio de la semana {semana} del módulo {modulo} usando exclusivamente el
material trazable que aparece abajo. Divide en 3 a 5 subtemas secuenciales, de menor a mayor
complejidad. Explica con lenguaje cotidiano, añade analogías concretas y conserva las fórmulas
originales con LaTeX válido entre $...$ o $$...$$. No inventes referencias: cada referencia
debe copiar exactamente el nombre y Página/Diapositiva de una etiqueta del material.
Regla estricta de analogía: para el campo analogia_vida_real genera una sola analogía de
la vida real por subtema, sin mezclar metáforas ni conceptos. Usa únicamente un ejemplo
cotidiano numérico o visual, concreto y fácil de imaginar, como repartir porciones iguales,
turnos de reloj o cajas dentro de cajas. Evita explicaciones poéticas y abstractas.
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
        titulo_semana = (request.titulo_semana or "").strip()
        if not titulo_semana or titulo_semana == "Semana de Estudio":
            subtopic_titles = [
                subtema.titulo.strip()
                for subtema in request.subtemas
                if subtema.titulo.strip()
            ]
            titulo_semana = (
                f"Examen semanal: {', '.join(subtopic_titles)}"
                if subtopic_titles
                else "Examen semanal de Matemática Discreta"
            )
        prompt = f"""
Genera exactamente 10 ejercicios integradores para el examen de la semana "{titulo_semana}".
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
