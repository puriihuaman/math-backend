Actúa como un Ingeniero Backend Senior en Python y FastAPI. Añade resiliencia contra sobrecargas temporales (`503 Service Unavailable` / `UNAVAILABLE`) de la API gratuita de Gemini sin alterar los contratos ni la lógica de esquemas:

### 1. Reintento automático con backoff en `app/services/gemini_service.py`
- Crea un helper interno `call_gemini_with_retry(...)` (síncrono o `async`, acorde a cómo esté implementado el cliente actual) que envuelva las llamadas a `client.models.generate_content` (o `client.aio.models.generate_content`).
- Si Google Gemini devuelve un error transitorio con código de estado `503` (servidor sobrecargado) o error de conexión temporal, reintenta automáticamente hasta **3 veces** con espera exponencial (`2s`, `4s`).
- Si tras los 3 intentos sigue fallando o si el error es `400` / `401` / `429` (cuota excedida), propaga la excepción inmediatamente sin esperar para que el manejador HTTP devuelva una respuesta clara al frontend.
- Asegúrate de que `generate_week_plan`, `generate_subtopic_exercises`, `generate_weekly_exam` y `evaluate_short_answer` utilicen este helper.