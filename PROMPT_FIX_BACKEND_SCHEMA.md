# Especificación de Corrección — Backend "DiscretaFlow" (Fix `400 INVALID_ARGUMENT` en `google-genai`)

## 1. Diagnóstico del Error
Al llamar a `gemini-2.5-flash` con Structured Outputs usando modelos de Pydantic v2, el SDK `google-genai` serializa propiedades como `additionalProperties` / `additional_properties` (y referencias `$defs` / `$ref`) que la API REST de Gemini rechaza con:
`400 INVALID_ARGUMENT: Unknown name "additional_properties" at 'generation_config.response_schema': Cannot find field.`

---

## 2. Correcciones Obligatorias a Implementar

### A. Limpieza de Modelos en `app/models/schemas.py`
1. **Prohibido `extra="forbid"` o tipos `dict` genéricos:**
   - Asegúrate de que ningún esquema Pydantic tenga `model_config = ConfigDict(extra="forbid")`, ya que eso fuerza la inyección de `additionalProperties: false` en el JSON Schema.
   - Si en el endpoint `/api/v1/study/generate-weekly-exam` existe algún campo tipado como `list[dict]`, reemplázalo por un modelo explícito (`SubtemaExamenInput` con `titulo: str`, `explicacion_simplificada: str`, `conceptos_fundamentales: list[str]`, `formulas_y_definiciones_originales: list[str]`).
2. **Validación final:** Después de recibir y parsear el JSON crudo devuelto por Gemini, valida siempre la respuesta en Python usando `Model.model_validate_json(response.text)` para garantizar el 100% de integridad de tipos.

### B. Sanitizador Universal de JSON Schema en `app/services/gemini_service.py`
Crea una función auxiliar `build_gemini_schema(pydantic_model: type[BaseModel]) -> dict` y úsala en **todas** las llamadas a `client.models.generate_content` (o `client.aio.models.generate_content`) dentro de `types.GenerateContentConfig`:

1. Obtén el diccionario base con `raw_schema = pydantic_model.model_json_schema()`.
2. Resuelve todas las referencias internas `$ref` apuntando a `$defs` (inlining recursivo de submodelos como `SubtemaSchema` o `EjercicioSchema`) y elimina la clave raíz `$defs`. 3. Recorre recursivamente todo el diccionario del esquema y **elimina cualquier clave no soportada por la API de Gemini**: - `additionalProperties` - `additional_properties` - `$schema`
   - `default`
   - `title`
4. Si una propiedad es `Optional[...]` (que Pydantic v2 representa como `{"anyOf": [{"type": "array", ...}, {"type": "null"}]}`), simplifícala en el esquema enviado a Gemini a su tipo principal con `"nullable": True` (ej. `{"type": "array", "items": {"type": "string"}, "nullable": True}`), ya que `anyOf` con `null` también suele provocar errores `400 INVALID_ARGUMENT` en Gemini.
5. Pasa el diccionario sanitizado resultante al parámetro `response_schema=build_gemini_schema(...)` junto con `response_mime_type="application/json"`.

### C. Verificación y Prueba Unitaria Rápida
1. Verifica que las 4 llamadas a Gemini en `gemini_service.py` (`generate_week_plan`, `generate_subtopic_exercises`, `generate_weekly_exam`, `evaluate_short_answer`) usen `build_gemini_schema(...)` y validen la salida con `.model_validate_json(response.text)`.
2. Asegúrate de que el manejo de errores HTTP capture tanto `google.genai.errors.APIError` / `ClientError` (devolviendo el código de estado real y el detalle legible en JSON, especialmente `429` para cuota excedida) como errores de validación.
3. Ejecuta una comprobación rápida de importación e impresión del esquema generado (`python -c "from app.services.gemini_service import build_gemini_schema; from app.models.schemas import WeekPlanResponse, ExercisesResponse; import json; print(json.dumps(build_gemini_schema(WeekPlanResponse), indent=2))"`) para confirmar que no existe ninguna clave `additionalProperties`, `$defs` ni `anyOf` en el JSON resultante.