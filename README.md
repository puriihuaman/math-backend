# DiscretaFlow Backend

Backend stateless para generar planes semanales, ejercicios y evaluaciones de Matemática
Discreta con FastAPI y Gemini Structured Outputs.

## Configuración local

Requiere Python 3.11 o superior. Activa el entorno virtual e instala las dependencias:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edita `.env` y define `GEMINI_API_KEY` con una clave de Google AI Studio. El servidor se
También define `CORS_ORIGINS` con el origen exacto del frontend. Para varios entornos,
separa los orígenes con comas, por ejemplo `http://localhost:5173,https://app.ejemplo.com`.
El servidor se inicia con:

```bash
uvicorn app.main:app --reload
```

La documentación interactiva está disponible en <http://localhost:8000/docs>. El endpoint
`GET /api/v1/health` no requiere credenciales. El endpoint de materiales acepta varios PDF
o PPTX y conserva las etiquetas de página/diapositiva para las referencias generadas.

## Endpoints

- `POST /api/v1/study/process-week-material`: genera el plan de una semana desde archivos.
- `POST /api/v1/study/generate-exercises`: genera ejercicios de un subtema.
- `POST /api/v1/study/generate-weekly-exam`: genera el examen semanal integrador.
- `POST /api/v1/study/evaluate-short-answer`: evalúa semánticamente una respuesta corta.
- `GET /api/v1/health`: comprueba que el servicio está activo.

Los errores de cuota de Gemini se responden con HTTP 429 y `retryable: true` para que el
frontend pueda mostrar una acción de reintento.
