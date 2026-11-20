Actúa como un Ingeniero Backend Senior especialista en Python, FastAPI e Ingeniería de Prompts. Realiza **dos ajustes quirúrgicos** en el proyecto actual sin modificar los endpoints existentes ni la lógica de `build_gemini_schema`:

### 1. Mejorar la claridad pedagógica de las analogías (`app/services/gemini_service.py`)
En el prompt del sistema de `generate_week_plan`, añade esta regla estricta para el campo `analogia_vida_real`:
- **Regla de Analogía Única y Concreta:** Genera **una sola analogía de la vida real** por subtema (nunca mezcles dos metáforas diferentes en el mismo párrafo). Debe enfocarse únicamente en el concepto central del subtema usando un ejemplo cotidiano numérico o visual muy concreto y fácil de visualizar (por ejemplo: repartir porciones iguales sin que sobre nada, turnos de reloj, cajas dentro de cajas). Evita frases abstractas o poéticas.

### 2. Blindar el esquema de entrada de `/api/v1/study/generate-weekly-exam` (`app/models/schemas.py` y `app/routers/study.py`)
Actualmente, el frontend envía `{ "modulo": 1, "semana": 1, "subtemas": [...] }` sin incluir `"titulo_semana"`, provocando un error `422 Unprocessable Content`.
- En el modelo de entrada del endpoint `/generate-weekly-exam` (en `app/models/schemas.py`), haz que `titulo_semana` sea opcional con valor por defecto:
  `titulo_semana: Optional[str] = "Semana de Estudio"`
  y acepta también los campos opcionales `modulo: Optional[int] = None` y `semana: Optional[int] = None` para que FastAPI no rechace el payload del frontend.
- Si `titulo_semana` llega vacío o con el valor por defecto, constrúyelo dinámicamente en el servicio usando los títulos de los subtemas recibidos.

Verifica que `uvicorn` recargue sin errores y mantén intactos los demás endpoints.
