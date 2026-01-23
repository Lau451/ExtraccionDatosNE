import os
import time
import random
import re
from pathlib import Path
from dotenv import load_dotenv
import google.generativeai as genai

# ======================
# CONFIGURACIÓN
# ======================

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash")

base_dir = Path(__file__).parent
input_folder = base_dir / "Entrada"
output_folder = base_dir / "Salida"
processed_folder = base_dir / "Procesados"

for carpeta in (input_folder, output_folder, processed_folder):
    carpeta.mkdir(exist_ok=True)

print("🤖 Robot de Extracción iniciado")

# ======================
# FUNCIONES
# ======================

def obtener_cliente(nombre_archivo: str) -> str:
    # Todo lo que esté antes del primer "_"
    return nombre_archivo.split("_", 1)[0].strip()

def nombre_unico(base: str, carpeta: Path, extension: str) -> str:
    """
    Si existe base.ext, genera base_2.ext, base_3.ext, etc.
    """
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
# LOOP PRINCIPAL
# ======================

while True:
    archivos = [
        f for f in input_folder.iterdir()
        if f.is_file() and f.suffix.lower() in [".pdf", ".jpg", ".jpeg", ".png"]
    ]

    for archivo in archivos:
        print(f"📄 Procesando: {archivo.name}")
        nombre_base = archivo.stem
        cliente = obtener_cliente(nombre_base)

        try:
            archivo_subido = genai.upload_file(str(archivo))

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

            respuesta = model.generate_content([prompt, archivo_subido])
            contenido = respuesta.text.strip()

            if not contenido.lower().startswith("item;"):
                raise ValueError("Respuesta inválida (no es CSV)")

            # ======================
            # GUARDAR CSV
            # ======================
            nombre_csv = nombre_unico(cliente, output_folder, ".csv")
            with open(output_folder / nombre_csv, "w", encoding="utf-8") as f:
                f.write(contenido)

            print(f"✅ CSV generado: {nombre_csv}")

            # ======================
            # MOVER A PROCESADOS
            # ======================
            nombre_proc = nombre_unico(nombre_base, processed_folder, archivo.suffix)
            archivo.rename(processed_folder / nombre_proc)

            print(f"📦 Movido a Procesados: {nombre_proc}")

            time.sleep(3 + random.uniform(1, 2))

        except Exception as e:
            print(f"❌ Error procesando {archivo.name}: {e}")

    time.sleep(5)
