from io import BytesIO
from pathlib import Path

from fastapi import UploadFile
from pptx import Presentation
from pypdf import PdfReader


def _clean_filename(filename: str | None) -> str:
    if not filename or not filename.strip():
        raise ValueError("Cada archivo debe tener un nombre válido.")
    return Path(filename).name


def _extract_pdf(content: bytes, filename: str) -> list[str]:
    try:
        reader = PdfReader(BytesIO(content))
        blocks = []
        for page_number, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                blocks.append(
                    f"--- [Fuente: {filename} | Página {page_number}] ---\n{text}"
                )
        return blocks
    except Exception as exc:
        raise ValueError(f"No se pudo leer el PDF '{filename}': archivo corrupto o ilegible.") from exc


def _extract_pptx(content: bytes, filename: str) -> list[str]:
    try:
        presentation = Presentation(BytesIO(content))
        blocks = []
        for slide_number, slide in enumerate(presentation.slides, start=1):
            parts = [
                shape.text.strip()
                for shape in slide.shapes
                if hasattr(shape, "text") and shape.text.strip()
            ]
            if slide.has_notes_slide:
                notes = slide.notes_slide.notes_text_frame.text.strip()
                if notes:
                    parts.append(f"Notas del orador: {notes}")
            text = "\n".join(parts).strip()
            if text:
                blocks.append(
                    f"--- [Fuente: {filename} | Diapositiva {slide_number}] ---\n{text}"
                )
        return blocks
    except Exception as exc:
        raise ValueError(
            f"No se pudo leer la presentación '{filename}': archivo corrupto o ilegible."
        ) from exc


async def extract_material(files: list[UploadFile]) -> str:
    """Extrae texto trazable de todos los PDF y PPTX recibidos."""
    if not files:
        raise ValueError("Debes subir al menos un archivo de material.")

    all_blocks: list[str] = []
    for upload in files:
        filename = _clean_filename(upload.filename)
        extension = Path(filename).suffix.lower()
        content = await upload.read()
        if not content:
            raise ValueError(f"El archivo '{filename}' está vacío.")
        if extension == ".pdf":
            blocks = _extract_pdf(content, filename)
        elif extension == ".pptx":
            blocks = _extract_pptx(content, filename)
        else:
            raise ValueError(
                f"Formato no compatible para '{filename}'. Solo se aceptan archivos .pdf y .pptx."
            )
        if not blocks:
            raise ValueError(
                f"No se encontró texto legible en '{filename}'. "
                "Verifica que no sea un documento escaneado sin texto."
            )
        all_blocks.extend(blocks)

    return "\n\n".join(all_blocks)
