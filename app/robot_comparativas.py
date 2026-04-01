from pathlib import Path
from typing import Optional
import shutil

import google.generativeai as genai
import pandas as pd

from app.config import MODEL, get_output_dir, get_processed_dir, COMPARATIVAS_OUTPUT_BASE
from app.robot import obtener_cliente, nombre_unico

# ======================
# PROMPT
# ======================

_PROMPT = """Analizá este documento de comparativa de precios de licitación.

Tu objetivo es extraer, para CADA COMBINACIÓN de ítem + proveedor, una fila en el CSV de salida.

TIPOS DE ESTRUCTURA POSIBLES:
- Horizontal: los proveedores son columnas y los ítems son filas. Los nombres de proveedores están en las primeras filas como encabezados de columna.
- Vertical: cada fila ya representa un proveedor para un ítem determinado. Puede haber filas de "cabecera de ítem" seguidas de filas de proveedores.

Detectá la estructura y normalizá al formato de salida sin importar cuál sea.

CAMPOS DE SALIDA (en este orden):
1. renglon: número de renglón o ítem
2. descripcion: descripción del producto
3. marca: laboratorio o marca del producto. Puede estar en una columna dedicada, en las notas del proveedor, o en la descripción. Si no hay información, dejá vacío.
4. proveedor: nombre completo del proveedor o droguería
5. precio: precio unitario ofertado. Usá punto como separador decimal. No incluyas símbolo de moneda.
6. origen: usá exactamente este valor: {origen}

REGLAS ESTRICTAS:
- Una fila por cada combinación renglón + proveedor
- Si un proveedor no cotizó un ítem (precio 0, vacío, guion o "no cotiza"), OMITIR esa fila
- Si existen columnas de descuento o porcentaje entre proveedores (por ejemplo valores como 0.05, 5%), ignorarlas
- No uses comillas en el CSV
- Separador: punto y coma (;)
- Incluí encabezado: renglon;descripcion;marca;proveedor;precio;origen
- Devolvé SOLO el CSV, sin texto adicional ni bloques de código
"""

# ======================
# FUNCION PRINCIPAL
# ======================

def procesar_comparativa(
    ruta_archivo: Path,
    nombre_original: Optional[str] = None,
) -> Path:
    if nombre_original:
        nombre_base = Path(nombre_original).stem
        extension = Path(nombre_original).suffix.lower()
    else:
        nombre_base = ruta_archivo.stem
        extension = ruta_archivo.suffix.lower()

    origen = obtener_cliente(nombre_base)
    prompt = _PROMPT.format(origen=origen)

    contenido_texto: Optional[str] = None
    archivo_subido = None

    if extension in {".xls", ".xlsx"}:
        engine = "xlrd" if extension == ".xls" else "openpyxl"
        df = pd.read_excel(ruta_archivo, engine=engine, header=None)
        contenido_texto = df.to_csv(sep=";", index=False, header=False)

    elif extension == ".ods":
        df = pd.read_excel(ruta_archivo, engine="odf", header=None)
        contenido_texto = df.to_csv(sep=";", index=False, header=False)

    elif extension in {".html", ".htm"}:
        with open(ruta_archivo, "r", encoding="utf-8", errors="replace") as f:
            contenido_texto = f.read()

    else:
        archivo_subido = genai.upload_file(str(ruta_archivo))

    if contenido_texto is not None:
        respuesta = MODEL.generate_content(prompt + "\n\nCONTENIDO DEL DOCUMENTO:\n" + contenido_texto)
    else:
        respuesta = MODEL.generate_content([prompt, archivo_subido])

    csv_texto = respuesta.text.replace("```csv", "").replace("```", "").strip()
    if not csv_texto.endswith("\n"):
        csv_texto += "\n"

    primera_linea = csv_texto.split("\n")[0].lower()
    if "renglon" not in primera_linea:
        raise ValueError("Respuesta inválida: no tiene el encabezado esperado de comparativa")

    output_dir = get_output_dir(base_dir=COMPARATIVAS_OUTPUT_BASE, origen_id=origen)
    processed_dir = get_processed_dir(base_dir=COMPARATIVAS_OUTPUT_BASE, origen_id=origen)

    nombre_csv = nombre_unico(nombre_base, output_dir, ".csv")
    ruta_salida = output_dir / nombre_csv

    with open(ruta_salida, "w", encoding="utf-8") as f:
        f.write(csv_texto)

    nombre_proc = nombre_unico(nombre_base, processed_dir, extension)
    shutil.move(str(ruta_archivo), str(processed_dir / nombre_proc))

    return ruta_salida
