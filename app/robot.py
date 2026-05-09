from pathlib import Path
import logging
import os
import re
import shutil
import unicodedata
from difflib import SequenceMatcher
from typing import Optional
from uuid import UUID
import pandas as pd
from app.config import CLIENT, get_output_dir, get_processed_dir, get_next_client, generate_with_fallback
from app.gemini_errors import handle_gemini_errors, GeminiQuotaExceededError, GeminiRateLimitError

logger = logging.getLogger(__name__)

# ======================
# FUNCIONES
# ======================

def obtener_cliente(nombre_archivo: str) -> str:
    return nombre_archivo.split("_", 1)[0].strip()


def nombre_unico(base: str, carpeta: Path, extension: str) -> str:
    nombre = f"{base}{extension}"
    i = 2
    while True:
        ruta = carpeta / nombre
        try:
            fd = os.open(str(ruta), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return ruta.name
        except FileExistsError:
            nombre = f"{base}_{i}{extension}"
            i += 1


def _normalizar_texto(texto: str) -> str:
    texto = str(texto).strip().lower()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto


def _mejor_match_columna(columnas: list[str], sinonimos: set[str], umbral: float = 0.72) -> Optional[str]:
    mejor_col = None
    mejor_score = 0.0

    for col in columnas:
        col_norm = _normalizar_texto(col)
        score = 0.0

        if col_norm in sinonimos:
            score = 1.0
        else:
            for s in sinonimos:
                if s in col_norm or col_norm in s:
                    score = max(score, 0.85)
                else:
                    ratio = SequenceMatcher(None, col_norm, s).ratio()
                    score = max(score, ratio)

        if score > mejor_score:
            mejor_score = score
            mejor_col = col

    if mejor_score >= umbral:
        return mejor_col
    return None


def _score_cantidad(serie: pd.Series) -> float:
    if serie.empty:
        return 0.0
    no_vacios = serie.dropna()
    if no_vacios.empty:
        return 0.0
    numeric = pd.to_numeric(no_vacios, errors="coerce")
    ratio_numeric = numeric.notna().mean()
    return float(ratio_numeric)


def _score_descripcion(serie: pd.Series) -> float:
    if serie.empty:
        return 0.0
    no_vacios = serie.dropna()
    if no_vacios.empty:
        return 0.0
    texto = no_vacios.astype(str).str.strip()
    texto = texto[texto != ""]
    if texto.empty:
        return 0.0
    largos = texto.str.len()
    ratio_texto = (largos >= 3).mean()
    return float(ratio_texto)


def _col_to_series(df: pd.DataFrame, col: str) -> pd.Series:
    serie = df[col]
    if isinstance(serie, pd.DataFrame):
        return serie.iloc[:, 0]
    return serie


def _limpiar_cantidad(contenido_csv: str) -> str:
    """Trunca la columna 'cantidad' al entero ignorando lo que va después de la coma."""
    lineas = contenido_csv.strip().split("\n")
    if not lineas:
        return contenido_csv

    encabezado = lineas[0].split(";")
    try:
        idx_cantidad = encabezado.index("cantidad")
    except ValueError:
        return contenido_csv

    filas_procesadas = [";".join(encabezado)]
    for linea in lineas[1:]:
        campos = linea.split(";")
        if len(campos) > idx_cantidad:
            val = campos[idx_cantidad].strip()
            if "," in val:
                val = val.split(",")[0].strip()
            val = val.replace(".", "")
            campos[idx_cantidad] = val
        filas_procesadas.append(";".join(campos))

    return "\n".join(filas_procesadas)


def _rellenar_items_incrementales(contenido_csv: str) -> str:
    """Rellena la columna 'item' de forma incremental si contiene valores vacíos.

    Procesa un CSV con formato "item;cantidad;descripcion;origen" y:
    - Si la columna item está vacía o ausente en algunas filas, las rellena con números incrementales
    - Mantiene los números que ya existan
    - Asegura continuidad incremental

    Args:
        contenido_csv: Contenido CSV con delimitador ';'

    Returns:
        CSV procesado con items rellenos
    """
    lineas = contenido_csv.strip().split("\n")
    if not lineas:
        return contenido_csv

    # Procesar encabezado
    encabezado = lineas[0].split(";")
    try:
        idx_item = encabezado.index("item")
    except ValueError:
        # Si no existe columna item, retornar sin cambios
        return contenido_csv

    # Procesar filas de datos
    filas_procesadas = [";".join(encabezado)]
    contador = 1

    for linea in lineas[1:]:
        campos = linea.split(";")

        # Asegurar que tenemos suficientes campos
        while len(campos) <= idx_item:
            campos.append("")

        # Si el item está vacío, asignar incrementalmente
        if not campos[idx_item] or campos[idx_item].strip() == "":
            campos[idx_item] = str(contador)

        contador += 1
        filas_procesadas.append(";".join(campos))

    return "\n".join(filas_procesadas)



def _normalizar_excel(df: pd.DataFrame, cliente: str) -> pd.DataFrame:
    columnas = list(df.columns)

    sinonimos_item = {
        "item", "renglon", "nro", "nro.", "n", "n.", "numero", "num", "num.",
        "numero de item", "numero de renglon", "cod", "codigo", "code", "sku",
    }
    col_item = _mejor_match_columna(columnas, sinonimos_item)

    item_generado = col_item is None  # Indica si se genera item incremental
    sinonimos_cantidad = {
        "cantidad", "cant", "cant.", "qty", "unidades", "unidad", "uds", "ud", "pcs",
        "cantidad solicitada", "cantidad pedida", "cantidades",
    }
    sinonimos_descripcion = {
        "descripcion", "descripcion producto", "producto", "articulo",
        "articulo producto", "detalle", "concepto", "nombre", "nombre producto",
    }

    col_cantidad = _mejor_match_columna(columnas, sinonimos_cantidad)
    col_descripcion = _mejor_match_columna(columnas, sinonimos_descripcion)

    usados = {c for c in [col_item, col_cantidad, col_descripcion] if c}

    if col_cantidad is None:
        candidatos = [c for c in columnas if c not in usados]
        mejor = None
        mejor_score = 0.0
        for c in candidatos:
            score = _score_cantidad(_col_to_series(df, c))
            if score > mejor_score:
                mejor_score = score
                mejor = c
        if mejor_score >= 0.6:
            col_cantidad = mejor
            usados.add(mejor)

    if col_descripcion is None:
        candidatos = [c for c in columnas if c not in usados]
        mejor = None
        mejor_score = 0.0
        for c in candidatos:
            score = _score_descripcion(_col_to_series(df, c))
            if score > mejor_score:
                mejor_score = score
                mejor = c
        if mejor_score >= 0.6:
            col_descripcion = mejor
            usados.add(mejor)

    salida = pd.DataFrame()

    if col_item:
        salida["item"] = _col_to_series(df, col_item)
    else:
        # Generar item incremental cuando no existe columna "item"
        salida["item"] = range(1, len(df) + 1)

    if col_cantidad:
        salida["cantidad"] = _col_to_series(df, col_cantidad)
    else:
        salida["cantidad"] = ""

    if col_descripcion:
        salida["descripcion"] = _col_to_series(df, col_descripcion)
    else:
        salida["descripcion"] = ""

    salida["origen"] = cliente
    return salida


# ======================
# FUNCION PRINCIPAL
# ======================

@handle_gemini_errors(max_retries=4, backoff_factor=40.0)
def procesar_archivo(
    ruta_archivo: Path,
    nombre_original: Optional[str] = None,
    *,
    session_id: Optional[UUID] = None,  # reservado para uso futuro (licitaciones)
) -> Path:
    if nombre_original:
        original_name = Path(nombre_original).name
        nombre_base = Path(original_name).stem
        extension_original = Path(original_name).suffix or ruta_archivo.suffix
    else:
        nombre_base = ruta_archivo.stem
        extension_original = ruta_archivo.suffix

    cliente = obtener_cliente(nombre_base)

    es_excel = extension_original.lower() in {".xls", ".xlsx"}
    archivo_subido = None
    texto_excel = None

    client = get_next_client()

    if es_excel:
        engine = "xlrd" if extension_original.lower() == ".xls" else "openpyxl"
        df = pd.read_excel(ruta_archivo, engine=engine, index_col=None)
        df_normalizado = _normalizar_excel(df, cliente)
        texto_excel = df_normalizado.to_csv(sep=";", index=False)
    else:
        logger.info("Uploading file to Gemini: %s", ruta_archivo.name)
        archivo_subido = client.files.upload(file=str(ruta_archivo))
        logger.info("Upload OK — file state: %s", archivo_subido.state)

    tipo_doc = "EXCEL" if es_excel else "DOCUMENTO"

    if es_excel:
        estructura = """
El archivo tiene dos secciones:
1. Una cabecera con datos generales (fecha, proveedor, cliente, etc.) — IGNORAR
2. Una tabla con los productos del pedido — EXTRAER SOLO ESTA
"""
    else:
        estructura = ""

    prompt = f"""
Analiza este {tipo_doc} y extrae la informacion solicitada en formato CSV.
{estructura}
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

    if es_excel:
        prompt = prompt + "\n\nCONTENIDO DEL EXCEL (CSV):\n" + texto_excel
        respuesta = generate_with_fallback(client, prompt)
    else:
        respuesta = generate_with_fallback(client, [prompt, archivo_subido])
    contenido = respuesta.text.strip()

    contenido = contenido.replace("```csv", "").replace("```", "").strip()
    if not contenido.endswith("\n"):
        contenido += "\n"
    if "item;" not in contenido.lower():
        raise ValueError("Respuesta invalida (no es CSV)")

    contenido = _limpiar_cantidad(contenido)
    contenido = _rellenar_items_incrementales(contenido)

    output_dir = get_output_dir(origen_id=cliente)
    processed_dir = get_processed_dir(origen_id=cliente)

    nombre_csv = nombre_unico(nombre_base, output_dir, ".csv")
    ruta_salida = output_dir / nombre_csv

    with open(ruta_salida, "w", encoding="utf-8") as f:
        f.write(contenido)

    nombre_proc = nombre_unico(nombre_base, processed_dir, extension_original)
    shutil.move(str(ruta_archivo), str(processed_dir / nombre_proc))

    return ruta_salida
