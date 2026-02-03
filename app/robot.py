from pathlib import Path
import shutil
from typing import Optional
import google.generativeai as genai
from app.config import MODEL, OUTPUT_DIR, PROCESSED_DIR

# ======================
# FUNCIONES
# ======================

def obtener_cliente(nombre_archivo: str) -> str:
    return nombre_archivo.split("_", 1)[0].strip()


def nombre_unico(base: str, carpeta: Path, extension: str) -> str:
    destino = carpeta / f"{base}{extension}"
    if not destino.exists():
        return destino.name

    i = 2
    while True:
        candidato = carpeta / f"{base}_{i}{extension}"
        if not candidato.exists():
            return candidato.name
        i += 1


# ======================
# FUNCION PRINCIPAL
# ======================

def procesar_archivo(ruta_archivo: Path, nombre_original: Optional[str] = None) -> Path:
    if nombre_original:
        original_name = Path(nombre_original).name
        nombre_base = Path(original_name).stem
        extension_original = Path(original_name).suffix or ruta_archivo.suffix
    else:
        nombre_base = ruta_archivo.stem
        extension_original = ruta_archivo.suffix

    cliente = obtener_cliente(nombre_base)

    es_excel = extension_original.lower() in {".xls", ".xlsx"}
    archivo_subido = genai.upload_file(str(ruta_archivo))

    tipo_doc = "EXCEL" if es_excel else "DOCUMENTO"
    prompt = f"""
Analiza este {tipo_doc} y extrae la informacion solicitada en formato CSV.

CAMPOS:
item;cantidad;descripcion;origen

REGLAS:
- Devuelve SOLO CSV
- Usa punto y coma (;)
- Incluye encabezado
- Una fila por producto
- Sin texto adicional
- No uses comillas
- El campo origen debe ser exactamente: {cliente}
"""

    respuesta = MODEL.generate_content([prompt, archivo_subido])
    contenido = respuesta.text.strip()

    if not contenido.lower().startswith("item;"):
        raise ValueError("Respuesta invalida (no es CSV)")

    nombre_csv = nombre_unico(nombre_base, OUTPUT_DIR, ".csv")
    ruta_salida = OUTPUT_DIR / nombre_csv

    with open(ruta_salida, "w", encoding="utf-8") as f:
        f.write(contenido)

    nombre_proc = nombre_unico(nombre_base, PROCESSED_DIR, extension_original)
    shutil.move(str(ruta_archivo), str(PROCESSED_DIR / nombre_proc))

    return ruta_salida
