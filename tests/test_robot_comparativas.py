"""
Tests para robot_comparativas: extracción de comparativas de precios.

Cubre:
  - NoProvidersDetectedError
  - _limpiar_precio
  - _comprimir_markdown
  - _filtrar_top_3_por_renglon
  - _split_markdown_chunks
  - _llamar_gemini_json
  - _extraer_comparativa
  - procesar_comparativa (pipeline completo)
"""

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.robot_comparativas import (
    NoProvidersDetectedError,
    _limpiar_precio,
    _comprimir_markdown,
    _filtrar_top_3_por_renglon,
    _split_markdown_chunks,
    _llamar_gemini_json,
    _extraer_comparativa,
    procesar_comparativa,
)


# =============================
# NoProvidersDetectedError
# =============================

def test_no_providers_error_es_value_error():
    with pytest.raises(ValueError):
        raise NoProvidersDetectedError("sin proveedores")


def test_no_providers_error_tiene_atributo_message():
    err = NoProvidersDetectedError("mensaje de prueba")
    assert err.message == "mensaje de prueba"
    assert str(err) == "mensaje de prueba"


# =============================
# _limpiar_precio
# =============================

@pytest.mark.parametrize("entrada,esperado", [
    # Vacíos / marcadores de "no cotiza"
    ("",           ""),
    ("-",          ""),
    ("n/a",        ""),
    ("no cotiza",  ""),
    ("No cotiza",  ""),
    ("sin precio", ""),
    ("s/p",        ""),
    # Formato argentino: punto de miles + coma decimal
    ("1.234,56",   "1234.56"),
    ("$1.234,56",  "1234.56"),
    # Solo coma decimal
    ("12,34",      "12.34"),
    ("12,5",       "12.50"),
    # Punto decimal simple
    ("12.50",      "12.50"),
    ("100.00",     "100.00"),
    # Símbolos de moneda
    ("€12,50",     "12.50"),
    ("12 USD",     "12.00"),
    ("12 ARS",     "12.00"),
    # Cero
    ("0",          "0.00"),
    ("0,00",       "0.00"),
    # Con espacios alrededor
    ("  $12,50  ", "12.50"),
    # No numérico
    ("abc",        ""),
    ("$$$",        ""),
])
def test_limpiar_precio(entrada: str, esperado: str):
    assert _limpiar_precio(entrada) == esperado


def test_limpiar_precio_loguea_warning_para_no_numerico(caplog):
    with caplog.at_level(logging.WARNING, logger="app.robot_comparativas"):
        _limpiar_precio("valor_invalido")
    assert any("Non-numeric" in msg for msg in caplog.messages)


# =============================
# _comprimir_markdown
# =============================

def test_comprimir_colapsa_triple_salto_de_linea():
    resultado = _comprimir_markdown("linea 1\n\n\n\nlinea 2")
    assert "\n\n\n" not in resultado


def test_comprimir_elimina_espacios_al_final_de_linea():
    resultado = _comprimir_markdown("linea con espacios   \notro")
    for linea in resultado.split("\n"):
        assert linea == linea.rstrip()


def test_comprimir_preserva_el_contenido():
    md = "## Título\n\nContenido importante\n\nOtro párrafo"
    resultado = _comprimir_markdown(md)
    assert "Título" in resultado
    assert "Contenido importante" in resultado
    assert "Otro párrafo" in resultado


def test_comprimir_string_vacio():
    assert _comprimir_markdown("") == ""


def test_comprimir_reduce_el_tamano():
    md = "a\n\n\n\n\nb\n\n\n\n\nc"
    resultado = _comprimir_markdown(md)
    assert len(resultado) < len(md)


# =============================
# _filtrar_top_3_por_renglon
# =============================

def _renglones(*items: dict) -> dict:
    return {"proveedores": ["A", "B", "C", "D"], "renglones": list(items)}


def _item(renglon, **precios) -> dict:
    """Helper: construye un renglón con precios en formato dict {proveedor: precio_str}."""
    return {
        "renglon": renglon,
        "proveedores_precios": {
            prov: {"precio": precio, "marca": ""}
            for prov, precio in precios.items()
        },
    }


def test_filtrar_devuelve_maximo_3_por_renglon():
    data = _renglones(_item(1, A="10.00", B="20.00", C="30.00", D="40.00"))
    rows = _filtrar_top_3_por_renglon(data, "CLI")
    assert len([r for r in rows if r["renglon"] == 1]) == 3


def test_filtrar_ordena_por_precio_ascendente():
    data = _renglones(_item(1, Caro="100.00", Barato="10.00", Medio="50.00"))
    rows = _filtrar_top_3_por_renglon(data, "CLI")
    precios = [float(r["precio"]) for r in rows]
    assert precios == sorted(precios)
    assert precios[0] == 10.0


def test_filtrar_omite_proveedores_sin_precio():
    data = _renglones({
        "renglon": 1,
        "descripcion": "Prod",
        "proveedores_precios": {
            "Con precio": {"precio": "10.00", "marca": ""},
            "Sin precio": {"precio": "",       "marca": ""},
            "No cotiza":  {"precio": "no cotiza", "marca": ""},
        },
    })
    rows = _filtrar_top_3_por_renglon(data, "CLI")
    proveedores = [r["proveedor"] for r in rows]
    assert "Sin precio" not in proveedores
    assert "No cotiza" not in proveedores
    assert "Con precio" in proveedores


def test_filtrar_omite_renglon_sin_ningun_precio_valido():
    data = _renglones({
        "renglon": 1,
        "descripcion": "Sin precios",
        "proveedores_precios": {
            "A": {"precio": "",  "marca": ""},
            "B": {"precio": "-", "marca": ""},
        },
    })
    rows = _filtrar_top_3_por_renglon(data, "CLI")
    assert rows == []


def test_filtrar_genera_renglon_incremental_si_falta_el_campo():
    data = _renglones({
        "renglon": "",
        "descripcion": "Sin número",
        "proveedores_precios": {"A": {"precio": "5.00", "marca": ""}},
    })
    rows = _filtrar_top_3_por_renglon(data, "CLI")
    assert len(rows) == 1
    assert rows[0]["renglon"] == 1


def test_filtrar_soporta_formato_legacy_precio_string():
    data = _renglones({
        "renglon": 1,
        "descripcion": "Producto",
        "proveedores_precios": {"A": "15.00", "B": "25.00"},
    })
    rows = _filtrar_top_3_por_renglon(data, "CLI")
    assert len(rows) == 2
    assert rows[0]["precio"] == "15.00"


def test_filtrar_incluye_marca_del_proveedor():
    data = _renglones({
        "renglon": 1,
        "descripcion": "Producto",
        "proveedores_precios": {
            "Farmex": {"precio": "12.00", "marca": "BAYER"},
        },
    })
    rows = _filtrar_top_3_por_renglon(data, "CLI")
    assert rows[0]["marca"] == "BAYER"


def test_filtrar_sanitiza_punto_y_coma_en_todos_los_campos():
    data = _renglones({
        "renglon": 1,
        "descripcion": "Prod;con;puntos",
        "proveedores_precios": {
            "Prov;A": {"precio": "10.00", "marca": "Mar;ca"},
        },
    })
    rows = _filtrar_top_3_por_renglon(data, "CLI;A")
    for campo in ("proveedor", "marca", "cliente"):
        assert ";" not in rows[0][campo]


def test_filtrar_multiples_renglones_independientes():
    data = _renglones(
        _item(1, A="10.00", B="20.00"),
        _item(2, A="30.00"),
    )
    rows = _filtrar_top_3_por_renglon(data, "CLI")
    assert len([r for r in rows if r["renglon"] == 1]) == 2
    assert len([r for r in rows if r["renglon"] == 2]) == 1


def test_filtrar_sin_renglones_retorna_lista_vacia():
    rows = _filtrar_top_3_por_renglon({"renglones": []}, "CLI")
    assert rows == []


# =============================
# _llamar_gemini_json
# =============================

@pytest.fixture
def mock_gemini():
    """Parchea get_next_client y generate_with_fallback en robot_comparativas."""
    with patch("app.robot_comparativas.get_next_client") as mock_client, \
         patch("app.robot_comparativas.generate_with_fallback") as mock_gen:
        mock_client.return_value = MagicMock()
        yield mock_gen


def test_llamar_gemini_parsea_json_valido(mock_gemini):
    mock_gemini.return_value.text = '{"proveedores": ["A"], "renglones": []}'
    result = _llamar_gemini_json("prompt", "markdown")
    assert result == {"proveedores": ["A"], "renglones": []}


def test_llamar_gemini_pasa_config_json(mock_gemini):
    from google.genai import types
    mock_gemini.return_value.text = '{"ok": true}'
    _llamar_gemini_json("prompt", "markdown")
    _, kwargs = mock_gemini.call_args
    config = kwargs.get("config")
    assert config is not None
    assert config.response_mime_type == "application/json"


def test_llamar_gemini_lanza_error_si_api_falla(mock_gemini):
    from app.gemini_errors import GeminiRateLimitError
    mock_gemini.side_effect = Exception("503 error")
    with patch("app.gemini_errors.time.sleep"):
        with pytest.raises(GeminiRateLimitError):
            _llamar_gemini_json("prompt", "markdown")


# =============================
# _split_markdown_chunks
# =============================

def _tabla_markdown(header_rows: list[list], data_rows: list[list]) -> str:
    """Construye una tabla markdown con n columnas para tests."""
    n_cols = len(data_rows[0]) if data_rows else len(header_rows[0]) if header_rows else 2
    sep = "|" + "|".join(["---"] * n_cols) + "|"

    def fila(vals):
        return "|" + "|".join(str(v) for v in vals) + "|"

    col_names = fila([f"c{i}" for i in range(n_cols)])
    lines = [col_names, sep]
    for row in header_rows + data_rows:
        lines.append(fila(row))
    return "\n".join(lines)


def test_split_tabla_pequena_retorna_un_chunk():
    md = _tabla_markdown([[-1, "meta"]], [[1, "prod A"], [2, "prod B"]])
    chunks = _split_markdown_chunks(md, chunk_size=10)
    assert len(chunks) == 1
    assert chunks[0] == md


def test_split_divide_en_chunks_por_chunk_size():
    data = [[i, f"prod {i}"] for i in range(1, 7)]  # renglones 1-6
    md = _tabla_markdown([[-1, "meta"]], data)
    chunks = _split_markdown_chunks(md, chunk_size=2)
    assert len(chunks) == 3


def test_split_incluye_contexto_en_cada_chunk():
    data = [[i, f"prod {i}"] for i in range(1, 5)]
    md = _tabla_markdown([[-1, "PROVEEDOR A"], [-2, "PROVEEDOR B"]], data)
    chunks = _split_markdown_chunks(md, chunk_size=2)
    for chunk in chunks:
        assert "PROVEEDOR A" in chunk
        assert "PROVEEDOR B" in chunk


def test_split_no_duplica_renglones():
    data = [[i, f"prod {i}"] for i in range(1, 7)]
    md = _tabla_markdown([[-1, "meta"]], data)
    chunks = _split_markdown_chunks(md, chunk_size=3)
    # Cada renglon aparece exactamente una vez en el total de chunks
    all_lines = "\n".join(chunks).split("\n")
    for i in range(1, 7):
        count = sum(1 for l in all_lines if l.startswith(f"|{i}|"))
        assert count == 1, f"renglon {i} aparece {count} veces"


def test_split_primer_chunk_tiene_primeros_renglones():
    data = [[i, f"prod {i}"] for i in range(1, 7)]
    md = _tabla_markdown([[-1, "meta"]], data)
    chunks = _split_markdown_chunks(md, chunk_size=3)
    assert "|1|" in chunks[0]
    assert "|4|" not in chunks[0]
    assert "|4|" in chunks[1]


def test_split_markdown_sin_tabla_retorna_lista_con_original():
    md = "texto sin tabla"
    assert _split_markdown_chunks(md) == [md]


# =============================
# _extraer_comparativa
# =============================

def test_extraer_comparativa_lanza_error_sin_proveedores():
    datos = {"proveedores": [], "renglones": []}
    with patch("app.robot_comparativas._llamar_gemini_json", return_value=datos):
        with pytest.raises(NoProvidersDetectedError):
            _extraer_comparativa("markdown", Path("archivo.pdf"))


def test_extraer_comparativa_retorna_datos_completos():
    datos = {
        "proveedores": ["Prov A", "Prov B"],
        "renglones": [{"renglon": 1, "descripcion": "Prod", "proveedores_precios": {}}],
    }
    with patch("app.robot_comparativas._llamar_gemini_json", return_value=datos):
        result = _extraer_comparativa("markdown", Path("archivo.pdf"))
    assert result["proveedores"] == ["Prov A", "Prov B"]
    assert len(result["renglones"]) == 1


def test_extraer_comparativa_usa_chunking_para_markdown_grande():
    from app.robot_comparativas import _CHUNK_THRESHOLD
    chunk1 = {
        "proveedores": ["Prov A"],
        "renglones": [{"renglon": 1, "descripcion": "Prod 1", "proveedores_precios": {}}],
    }
    chunk2 = {
        "proveedores": ["Prov A"],
        "renglones": [{"renglon": 2, "descripcion": "Prod 2", "proveedores_precios": {}}],
    }
    markdown_grande = "x" * (_CHUNK_THRESHOLD + 1)
    with patch("app.robot_comparativas._split_markdown_chunks", return_value=["chunk1", "chunk2"]) as p_split, \
         patch("app.robot_comparativas._llamar_gemini_json", side_effect=[chunk1, chunk2]):
        result = _extraer_comparativa(markdown_grande, Path("grande.pdf"))
    p_split.assert_called_once_with(markdown_grande)
    assert len(result["renglones"]) == 2
    assert result["renglones"][0]["renglon"] == 1
    assert result["renglones"][1]["renglon"] == 2


def test_extraer_comparativa_no_usa_chunking_para_markdown_pequeno():
    from app.robot_comparativas import _CHUNK_THRESHOLD
    datos = {"proveedores": ["A"], "renglones": []}
    markdown_pequeno = "x" * (_CHUNK_THRESHOLD - 1)
    with patch("app.robot_comparativas._split_markdown_chunks") as p_split, \
         patch("app.robot_comparativas._llamar_gemini_json", return_value=datos):
        _extraer_comparativa(markdown_pequeno, Path("pequeno.pdf"))
    p_split.assert_not_called()


# =============================
# procesar_comparativa (pipeline)
# =============================

@pytest.fixture
def pipeline(tmp_path):
    """Archivo de prueba + mocks de todas las dependencias externas del pipeline."""
    archivo = tmp_path / "CLI_comparativa.pdf"
    archivo.write_bytes(b"fake pdf")

    csv_destino = tmp_path / "CLI_comparativa.csv"
    procesado_destino = tmp_path / "CLI_comparativa_proc.pdf"

    datos_gemini = {
        "proveedores": ["Farmex", "Droguería Sur"],
        "renglones": [
            {
                "renglon": 1,
                "descripcion": "AMOXICILINA 500MG",
                "proveedores_precios": {
                    "Farmex":        {"precio": "15.00", "marca": "BAYER"},
                    "Droguería Sur": {"precio": "12.00", "marca": "GENFAR"},
                },
            }
        ],
    }

    with patch("app.parsers.parse_document", return_value="## Markdown") as p_parse, \
         patch("app.robot_comparativas._guardar_docling_output") as p_docling, \
         patch("app.robot_comparativas._extraer_comparativa", return_value=datos_gemini) as p_extraer, \
         patch("app.robot_comparativas._escribir_csv", return_value=csv_destino) as p_csv, \
         patch("app.robot_comparativas._mover_a_procesados", return_value=procesado_destino) as p_mover:
        yield {
            "archivo": archivo,
            "csv_destino": csv_destino,
            "parse": p_parse,
            "docling": p_docling,
            "extraer": p_extraer,
            "csv": p_csv,
            "mover": p_mover,
        }


def test_pipeline_retorna_ruta_csv(pipeline):
    resultado = procesar_comparativa(pipeline["archivo"], "CLI_comparativa.pdf")
    assert resultado == pipeline["csv_destino"]


def test_pipeline_llama_parse_document(pipeline):
    procesar_comparativa(pipeline["archivo"], "CLI_comparativa.pdf")
    pipeline["parse"].assert_called_once_with(pipeline["archivo"])


def test_pipeline_llama_extraer_comparativa(pipeline):
    procesar_comparativa(pipeline["archivo"], "CLI_comparativa.pdf")
    pipeline["extraer"].assert_called_once()


def test_pipeline_llama_mover_a_procesados(pipeline):
    procesar_comparativa(pipeline["archivo"], "CLI_comparativa.pdf")
    pipeline["mover"].assert_called_once()


def test_pipeline_deriva_cliente_del_nombre_original(pipeline):
    procesar_comparativa(pipeline["archivo"], "FARMACIA_doc.pdf")
    args = pipeline["csv"].call_args[0]
    # _escribir_csv(rows, nombre_base, cliente) — cliente es el primer segmento
    assert args[2] == "FARMACIA"


def test_pipeline_lanza_error_si_no_hay_renglones(pipeline):
    pipeline["extraer"].return_value = {"proveedores": ["A"], "renglones": []}
    with pytest.raises(json.JSONDecodeError):
        procesar_comparativa(pipeline["archivo"], "CLI_comparativa.pdf")


def test_pipeline_lanza_error_si_no_quedan_filas_validas(pipeline):
    pipeline["extraer"].return_value = {
        "proveedores": ["A"],
        "renglones": [
            {
                "renglon": 1,
                "descripcion": "Prod",
                "proveedores_precios": {"A": {"precio": "", "marca": ""}},
            }
        ],
    }
    with pytest.raises(json.JSONDecodeError):
        procesar_comparativa(pipeline["archivo"], "CLI_comparativa.pdf")
