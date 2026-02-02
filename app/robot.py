from pathlib import Path
import google.generativeai as genai
from app.config import MODEL,OUTPUT_DIR, PROCESSED_DIR

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
# FUNCIÓN PRINCIPAL
# ======================

def procesar_archivo(ruta_archivo: Path) -> Path:
    nombre_base = ruta_archivo.stem
    cliente = obtener_cliente(nombre_base)

    archivo_subido = genai.upload_file(str(ruta_archivo))

    prompt = f"""
Analiza este documento y extrae la información solicitada en formato CSV.

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
        raise ValueError("Respuesta inválida (no es CSV)")

    nombre_csv = nombre_unico(cliente, OUTPUT_DIR, ".csv")
    ruta_salida = OUTPUT_DIR / nombre_csv

    with open(ruta_salida, "w", encoding="utf-8") as f:
        f.write(contenido)

    nombre_proc = nombre_unico(nombre_base, PROCESSED_DIR, ruta_archivo.suffix)
    ruta_archivo.rename(PROCESSED_DIR / nombre_proc)

    return ruta_salida
