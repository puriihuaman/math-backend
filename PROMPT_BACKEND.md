# Especificación Técnica y Plan de Implementación — Backend MVP "DiscretaFlow"

## 1. Rol y Objetivo
Actúa como un Ingeniero de Software Senior especialista en Python, FastAPI e Ingeniería de Prompts. Tu objetivo es construir el **Backend completo, limpio, modular y listo para producción local** del MVP **"DiscretaFlow"**, una plataforma educativa anti-procrastinación diseñada para el estudio autónomo de Matemática Discreta (estructurada en un ciclo universitario de **4 Módulos × 4 Semanas**).

---

## 2. Stack Tecnológico y Restricciones de Arquitectura
- **Lenguaje:** Python 3.11+
- **Framework Web:** FastAPI + Uvicorn.
- **SDK de Inteligencia Artificial:** Google GenAI SDK oficial (`google-genai`), utilizando el modelo `gemini-2.5-flash` (capa gratuita) con **Structured Outputs (Pydantic)** para garantizar respuestas JSON 100% deterministas y tipadas.
- **Extracción de Documentos:** `pypdf` (o `pdfplumber`) para archivos `.pdf` y `python-pptx` para presentaciones PowerPoint.
- **Estado y Base de Datos:** **Stateless (Sin base de datos ni autenticación propia)**. El backend recibe archivos o contextos JSON, los procesa y devuelve respuestas estructuradas. Toda persistencia vive en el frontend (`localStorage` + Google Drive AppData).
- **Resiliencia:** Manejo explícito de errores de tasa de peticiones (`429 Resource Exhausted` / Rate Limits de la capa gratuita de Gemini) y validación de archivos corruptos/vacíos.
- **CORS:** Configurado para aceptar peticiones desde `http://localhost:5173` (Frontend Vue 3 + Vite).

---

## 3. Estructura de Directorios Obligatoria
Crea exactamente esta estructura de carpetas y archivos:

```text
discreta-backend/
├── app/
│   ├── __init__.py
│   ├── main.py                  # Instancia FastAPI, middleware CORS, manejo global de excepciones y routers
│   ├── config.py                # Carga y validación de variables de entorno (GEMINI_API_KEY)
│   ├── models/
│   │   ├── __init__.py
│   │   └── schemas.py           # Todos los modelos Pydantic (Request y Response)
│   ├── services/
│   │   ├── __init__.py
│   │   ├── file_parser.py       # Extracción de texto con trazabilidad de archivo y página/diapositiva
│   │   └── gemini_service.py    # Lógica de negocio e ingeniería de prompts con Gemini
│   └── routers/
│       ├── __init__.py
│       └── study.py             # Endpoints REST bajo el prefijo /api/v1/study
├── .env.example
├── requirements.txt
└── README.md
```

---

## 4. Especificación de Componentes y Lógica de Negocio

### A. `app/services/file_parser.py` (Extracción con Trazabilidad)
- Debe aceptar múltiples archivos simultáneamente (por ejemplo, el PDF de teoría y el PPTX de clase de una misma semana).
- **Regla crítica de trazabilidad:** Al extraer el texto, debe etiquetar cada bloque con el nombre exacto del archivo y su número de página o diapositiva para que la IA pueda generar citas exactas:
  - Para PDF: `--- [Fuente: {nombre_archivo} | Página {num_pagina}] ---\n{texto}`
  - Para PPTX: `--- [Fuente: {nombre_archivo} | Diapositiva {num_diapositiva}] ---\n{texto}` (incluyendo notas del orador si existen).
- Si un archivo no es `.pdf` ni `.pptx`, o está vacío/ilegible (ej. PDF escaneado sin texto), lanzar una excepción controlada (`ValueError`) con un mensaje claro en español.

### B. `app/models/schemas.py` (Contratos de Datos Estrictos)
Define esquemas Pydantic v2 claros y bien tipados:

1. **`SubtemaSchema`**:
   - `id`: `str` (slug único, ej. `"mod1-sem1-sub1"`)
   - `orden`: `int` (1, 2, 3...)
   - `titulo`: `str`
   - `explicacion_simplificada`: `str` (Lenguaje cotidiano, directo y empático, sin jerga innecesaria).
   - `analogia_vida_real`: `str` (Situación cotidiana concreta que ilustre el concepto abstracto).
   - `conceptos_fundamentales`: `list[str]` (Lista de 3 a 5 ideas clave).
   - `formulas_y_definiciones_originales`: `list[str]` (Rigor matemático del curso usando formato LaTeX válido entre `$...$` o `$$...$$`).
   - `ejemplo_resuelto`: `str` (Desarrollo paso a paso con formato LaTeX).
   - `referencias_material`: `list[str]` (Citas exactas al material subido, ej. `["Semana1_Logica.pdf - Página 4", "Clase1.pptx - Diapositiva 7"]`).

2. **`WeekPlanResponse`**:
   - `modulo`: `int`
   - `semana`: `int`
   - `titulo_semana`: `str`
   - `resumen_general`: `str`
   - `subtemas`: `list[SubtemaSchema]` (Entre 3 y 5 subtemas ordenados progresivamente de menor a mayor complejidad).

3. **`EjercicioSchema`**:
   - `id`: `int`
   - `nivel`: `Literal["basico", "intermedio", "reto"]`
   - `tipo`: `Literal["opcion_multiple", "respuesta_corta"]`
   - `enunciado`: `str` (Con formato LaTeX `$...$`).
   - `opciones`: `Optional[list[str]]` (Exactamente 4 opciones si `tipo == "opcion_multiple"`, `None` si es `respuesta_corta`).
   - `respuesta_correcta`: `str`
   - `pista`: `str` (Indicación conceptual para guiar el razonamiento en papel y lápiz sin revelar la respuesta).
   - `explicacion_paso_a_paso`: `str` (Solución detallada que explica por qué la respuesta es correcta y por qué los distractores son incorrectos).

4. **`ExercisesResponse`**:
   - `ejercicios`: `list[EjercicioSchema]`

5. **`EvaluationRequest` y `EvaluationResponse`**:
   - Request: `enunciado: str`, `respuesta_correcta_esperada: str`, `respuesta_usuario: str`.
   - Response: `es_correcta: bool`, `puntaje: int` (0 a 100), `retroalimentacion: str` (Explicación amable y precisa).

### C. `app/services/gemini_service.py` (Reglas Pedagógicas de IA)
Configura llamadas a `gemini-2.5-flash` usando `response_schema` de Pydantic y temperatura baja (`0.2` - `0.3`) para máxima precisión matemática:

1. **Generación de Plan Semanal (`generate_week_plan`)**:
   - Fusiona el contenido de todos los archivos de la semana.
   - Divide el tema en **3 a 5 subtemas secuenciales** diseñados para sesiones de estudio de ~25 minutos.
   - Instruye explícitamente a Gemini a traducir definiciones densas a lenguaje cotidiano con analogías reales, conservando intactas las fórmulas originales en LaTeX válido (asegurando doble escape correcto en JSON para que no se rompan comandos como `\land`, `\lor`, `\neg`, `\forall`, `\exists`, `\rightarrow`, `\subseteq`).
   - Exige que `referencias_material` cite exactamente las fuentes etiquetadas por `file_parser.py`.

2. **Generación de Ejercicios Progresivos (`generate_subtopic_exercises`)**:
   - Genera por defecto **6 ejercicios** (o la cantidad solicitada en el parámetro `cantidad`, manteniendo la proporción):
     - **2 de nivel `basico`**: `opcion_multiple` (validación de conceptos y lectura de símbolos).
     - **2 de nivel `intermedio`**: combinando `opcion_multiple` y `respuesta_corta` (aplicación de propiedades, tablas de verdad, conjuntos o conteo).
     - **2 de nivel `reto`**: `respuesta_corta` (problemas aplicados que requieren resolución en papel y lápiz).
   - **Regla crítica de Distractores Inteligentes:** Para todo ejercicio de `opcion_multiple`, las 3 opciones incorrectas **NO pueden ser obvias ni absurdas**. Deben construirse simulando errores algebraicos o lógicos frecuentes de estudiantes universitarios (ej. negar mal un cuantificador, confundir contrarrecíproca con recíproca, error de signo o de inclusión), obligando al estudiante a resolver el problema en papel antes de elegir.
   - **Regla de Pistas:** Todo ejercicio debe incluir una `pista` útil que oriente al estudiante sobre qué teorema, ley o paso aplicar.

3. **Generación de Test Examen Semanal (`generate_weekly_exam`)**:
   - Recibe la lista completa de subtemas de la semana y genera **10 ejercicios integradores** mezclados (4 básicos, 4 intermedios, 2 reto) que evalúen toda la semana en conjunto. Mantiene la regla de distractores inteligentes.

4. **Evaluación Semántica de Respuesta Corta (`evaluate_short_answer`)**:
   - Evalúa equivalencia lógica/matemática más allá de la sintaxis exacta (ej. debe aceptar como equivalentes `p ^ q`, `p and q`, `p \land q` o expresiones algebraicas equivalentes).

---

## 5. Endpoints REST (`/api/v1/study`)

1. **`POST /api/v1/study/process-week-material`**
   - `Form`: `modulo: int`, `semana: int`
   - `Files`: `files: list[UploadFile]``
   - Retorna: `WeekPlanResponse`
2. **`POST /api/v1/study/generate-exercises`**
   - `Body (JSON)`: `{ "titulo_subtema": str, "explicacion_simplificada": str, "conceptos_fundamentales": list[str], "formulas": list[str], "cantidad": int = 6 }`
   - Retorna: `ExercisesResponse`
3. **`POST /api/v1/study/generate-weekly-exam`**
   - `Body (JSON)`: `{ "titulo_semana": str, "subtemas": list[dict] }`
   - Retorna: `ExercisesResponse` (con 10 preguntas integradoras)
4. **`POST /api/v1/study/evaluate-short-answer`**
   - `Body (JSON)`: `EvaluationRequest`
   - Retorna: `EvaluationResponse`
5. **`GET /api/v1/health`**
   - Retorna: `{ "status": "ok", "service": "DiscretaFlow Backend" }`

---

## 6. Plan de Ejecución Paso a Paso
Ejecuta la construcción en este orden estricto, verificando la calidad de cada archivo antes de pasar al siguiente:
1. Crea `requirements.txt` (incluyendo `fastapi`, `uvicorn[standard]`, `python-multipart`, `pydantic`, `pydantic-settings`, `google-genai`, `pypdf`, `python-pptx`) y `.env.example`.
2. Implementa `app/config.py` validando que exista `GEMINI_API_KEY`.
3. Implementa `app/models/schemas.py` con validaciones estrictas de campos y tipos.
4. Implementa `app/services/file_parser.py` con soporte multi-archivo y etiquetas de página/diapositiva.
5. Implementa `app/services/gemini_service.py` cuidando el formateo LaTeX en JSON y los prompts pedagógicos.
6. Implementa `app/routers/study.py` y `app/main.py` incluyendo un manejador global de excepciones que capture errores de cuota de Gemini (`429`) y devuelva un JSON limpio con código HTTP `429` y mensaje amigable en español para que el frontend pueda mostrar un botón de reintento.
7. Crea un `README.md` con instrucciones concisas para configurar el entorno virtual, variables de entorno y probar los endpoints en `/docs`.