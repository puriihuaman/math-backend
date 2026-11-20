from typing import Annotated, Literal, Optional

from pydantic import BaseModel, Field, model_validator


NonEmptyText = Annotated[str, Field(min_length=1)]


class SubtemaSchema(BaseModel):
    id: NonEmptyText
    orden: Annotated[int, Field(ge=1)]
    titulo: NonEmptyText
    explicacion_simplificada: NonEmptyText
    analogia_vida_real: NonEmptyText
    conceptos_fundamentales: Annotated[list[NonEmptyText], Field(min_length=3, max_length=5)]
    formulas_y_definiciones_originales: list[NonEmptyText] = Field(default_factory=list)
    ejemplo_resuelto: NonEmptyText
    referencias_material: Annotated[list[NonEmptyText], Field(min_length=1)]


class WeekPlanResponse(BaseModel):
    modulo: Annotated[int, Field(ge=1, le=4)]
    semana: Annotated[int, Field(ge=1, le=4)]
    titulo_semana: NonEmptyText
    resumen_general: NonEmptyText
    subtemas: Annotated[list[SubtemaSchema], Field(min_length=3, max_length=5)]

    @model_validator(mode="after")
    def subtopics_are_ordered(self) -> "WeekPlanResponse":
        orders = [subtema.orden for subtema in self.subtemas]
        if orders != sorted(orders) or len(set(orders)) != len(orders):
            raise ValueError("Los subtemas deben estar ordenados y tener órdenes únicos.")
        return self


class EjercicioSchema(BaseModel):
    id: Annotated[int, Field(ge=1)]
    nivel: Literal["basico", "intermedio", "reto"]
    tipo: Literal["opcion_multiple", "respuesta_corta"]
    enunciado: NonEmptyText
    opciones: list[NonEmptyText] | None = None
    respuesta_correcta: NonEmptyText
    pista: NonEmptyText
    explicacion_paso_a_paso: NonEmptyText

    @model_validator(mode="after")
    def validate_options(self) -> "EjercicioSchema":
        if self.tipo == "opcion_multiple":
            if self.opciones is None or len(self.opciones) != 4:
                raise ValueError("Los ejercicios de opción múltiple requieren exactamente 4 opciones.")
        elif self.opciones is not None:
            raise ValueError("Los ejercicios de respuesta corta no deben incluir opciones.")
        return self


class ExercisesResponse(BaseModel):
    ejercicios: Annotated[list[EjercicioSchema], Field(min_length=1)]


class GenerateExercisesRequest(BaseModel):
    titulo_subtema: NonEmptyText
    explicacion_simplificada: NonEmptyText
    conceptos_fundamentales: Annotated[list[NonEmptyText], Field(min_length=1)]
    formulas: list[NonEmptyText] = Field(default_factory=list)
    cantidad: Annotated[int, Field(ge=1, le=20)] = 6


class SubtemaExamenInput(BaseModel):
    titulo: NonEmptyText
    explicacion_simplificada: NonEmptyText
    conceptos_fundamentales: Annotated[list[NonEmptyText], Field(min_length=1)]
    formulas_y_definiciones_originales: list[NonEmptyText] = Field(default_factory=list)


class GenerateWeeklyExamRequest(BaseModel):
    titulo_semana: Optional[str] = "Semana de Estudio"
    modulo: Optional[int] = None
    semana: Optional[int] = None
    subtemas: Annotated[list[SubtemaExamenInput], Field(min_length=1)]


class EvaluationRequest(BaseModel):
    enunciado: NonEmptyText
    respuesta_correcta_esperada: NonEmptyText
    respuesta_usuario: NonEmptyText


class EvaluationResponse(BaseModel):
    es_correcta: bool
    puntaje: Annotated[int, Field(ge=0, le=100)]
    retroalimentacion: NonEmptyText
