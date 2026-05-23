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
    _restructurar_si_formato_plano,
    _detectar_gaps,
    _reintentar_gaps,
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
# _restructurar_si_formato_plano
# =============================

_FLAT_MD = """\
| Municipalidad | | Comparación de Ofertas | |
| --- | --- | --- | --- |
| Alt | Proveedor | Detalle | Precio |
| 1234 DROGUERIA A MEDICAMENTOS UNIDAD 100 10,00 C. HOSPITALARIOS Item: - 5 - AMOXICILINA Cantidad: 500 1234 DROGUERIA A MEDICAMENTOS UNIDAD 500 5,00 2345 DROGUERIA B MEDICAMENTOS UNIDAD 500 6,00 Item: - 6 - IBUPROFENO Cantidad: 200 3456 DROGUERIA C MEDICAMENTOS UNIDAD 200 3,50 | | | |
| 4567 DROGUERIA D MEDICAMENTOS UNIDAD 200 4,00 Item: - 7 - PARACETAMOL Cantidad: 300 5678 DROGUERIA E MEDICAMENTOS UNIDAD 300 2,00 | | | |
"""

_NO_FLAT_MD = """\
| renglon | proveedor | precio |
| --- | --- | --- |
| 1 | DROGUERIA A | 10.00 |
| 2 | DROGUERIA B | 20.00 |
"""


def test_restructurar_detecta_formato_plano():
    resultado = _restructurar_si_formato_plano(_FLAT_MD)
    assert "## Item 5" in resultado
    assert "## Item 6" in resultado
    assert "## Item 7" in resultado


def test_restructurar_preserva_cuerpo_de_cada_item():
    resultado = _restructurar_si_formato_plano(_FLAT_MD)
    # El cuerpo de Item 5 contiene sus proveedores
    idx_5 = resultado.index("## Item 5")
    idx_6 = resultado.index("## Item 6")
    body_5 = resultado[idx_5:idx_6]
    assert "AMOXICILINA" in body_5
    assert "DROGUERIA A" in body_5


def test_restructurar_no_toca_markdown_estructurado():
    resultado = _restructurar_si_formato_plano(_NO_FLAT_MD)
    assert resultado == _NO_FLAT_MD


def test_restructurar_string_vacio():
    assert _restructurar_si_formato_plano("") == ""


def test_restructurar_sin_items_devuelve_original():
    md = "| col1 | col2 |\n| --- | --- |\n| dato | valor |\n"
    assert _restructurar_si_formato_plano(md) == md


def test_restructurar_mantiene_orden_de_items():
    resultado = _restructurar_si_formato_plano(_FLAT_MD)
    idx_5 = resultado.index("## Item 5")
    idx_6 = resultado.index("## Item 6")
    idx_7 = resultado.index("## Item 7")
    assert idx_5 < idx_6 < idx_7


# =============================
# _detectar_gaps
# =============================

def _make_renglones(*nums: int) -> list[dict]:
    return [{"renglon": n, "proveedores_precios": {}} for n in nums]


def test_detectar_gaps_secuencia_completa():
    renglones = _make_renglones(1, 2, 3, 4, 5)
    assert _detectar_gaps(renglones) == []


def test_detectar_gaps_gap_pequeño_ignorado():
    # Gap de 2 (1, 3): 1 item faltante < threshold=3
    renglones = _make_renglones(1, 3, 4, 5)
    assert _detectar_gaps(renglones) == []


def test_detectar_gaps_gap_justo_en_threshold():
    # Gap de 3 items faltantes (2,3,4) entre 1 y 5 — exactamente el threshold
    renglones = _make_renglones(1, 5, 6, 7)
    assert _detectar_gaps(renglones) == [(2, 4)]


def test_detectar_gaps_gap_grande():
    renglones = _make_renglones(73, 84, 85, 86)
    gaps = _detectar_gaps(renglones)
    assert gaps == [(74, 83)]


def test_detectar_gaps_multiples_gaps():
    renglones = _make_renglones(1, 2, 10, 11, 20, 21)
    gaps = _detectar_gaps(renglones)
    assert (3, 9) in gaps
    assert (12, 19) in gaps


def test_detectar_gaps_lista_vacia():
    assert _detectar_gaps([]) == []


def test_detectar_gaps_un_solo_renglon():
    assert _detectar_gaps(_make_renglones(5)) == []


def test_detectar_gaps_threshold_personalizado():
    renglones = _make_renglones(1, 3, 4, 5)  # gap de 1 item
    assert _detectar_gaps(renglones, min_size=1) == [(2, 2)]
    assert _detectar_gaps(renglones, min_size=2) == []


# =============================
# _reintentar_gaps
# =============================

def test_reintentar_gaps_recupera_items_faltantes():
    gaps = [(74, 76)]
    # El chunk 1 (vacío) contiene marcadores de los ítems faltantes en su markdown
    markdowns = [
        "## Item 73\ncontenido del item 73",
        "## Item 74\ncontenido\n## Item 75\ncontenido\n## Item 76\ncontenido",
        "## Item 77\ncontenido del item 77",
    ]
    chunk_results = [
        {"proveedores": ["P1"], "renglones": [{"renglon": 73, "proveedores_precios": {}}]},
        {"proveedores": [], "renglones": []},
        {"proveedores": ["P2"], "renglones": [{"renglon": 77, "proveedores_precios": {}}]},
    ]
    recovered_item = {"renglon": 75, "proveedores_precios": {"P3": {"precio": "10.00", "marca": "X"}}}

    with patch("app.robot_comparativas._llamar_gemini_json") as mock_gemini:
        mock_gemini.return_value = {
            "proveedores": ["P3"],
            "renglones": [recovered_item],
        }
        new_renglones, new_providers = _reintentar_gaps(gaps, markdowns, chunk_results)

    assert any(r["renglon"] == 75 for r in new_renglones)
    assert "P3" in new_providers


def test_reintentar_gaps_sin_gaps_no_llama_gemini():
    with patch("app.robot_comparativas._llamar_gemini_json") as mock_gemini:
        new_renglones, new_providers = _reintentar_gaps([], ["md"], [{"proveedores": [], "renglones": []}])
    mock_gemini.assert_not_called()
    assert new_renglones == []
    assert new_providers == []


def test_reintentar_gaps_sin_chunks_adyacentes_no_falla():
    gaps = [(10, 15)]
    markdowns = ["Item: - 1 - contenido"]
    chunk_results = [{"proveedores": [], "renglones": [{"renglon": 1, "proveedores_precios": {}}]}]
    new_renglones, new_providers = _reintentar_gaps(gaps, markdowns, chunk_results)
    assert new_renglones == []


def test_reintentar_gaps_excluye_items_fuera_del_gap():
    gaps = [(5, 7)]
    # Markdowns con marcadores de ítem dentro del gap para pasar el pre-check
    markdowns = [
        "Item: - 4 - contenido\nItem: - 5 - contenido\nItem: - 6 - contenido",
        "Item: - 7 - contenido\nItem: - 8 - contenido",
    ]
    chunk_results = [
        {"proveedores": [], "renglones": [{"renglon": 4, "proveedores_precios": {}}]},
        {"proveedores": [], "renglones": [{"renglon": 8, "proveedores_precios": {}}]},
    ]
    with patch("app.robot_comparativas._llamar_gemini_json") as mock_gemini:
        mock_gemini.return_value = {
            "proveedores": [],
            "renglones": [
                {"renglon": 3, "proveedores_precios": {}},
                {"renglon": 6, "proveedores_precios": {}},
                {"renglon": 10, "proveedores_precios": {}},
            ],
        }
        new_renglones, _ = _reintentar_gaps(gaps, markdowns, chunk_results)

    # Solo el item 6 debe ser incluido (está dentro del gap 5-7)
    assert all(r["renglon"] in (5, 6, 7) for r in new_renglones)
    assert any(r["renglon"] == 6 for r in new_renglones)


def test_reintentar_gaps_skip_si_items_ausentes_en_markdown():
    # Gap real del documento: 74→86, los ítems 75-85 no existen en el PDF
    gaps = [(75, 85)]
    markdowns = [
        "## Item 73\ncontenido del 73",   # chunk antes del gap — sin marcadores 75-85
        "## Item 86\ncontenido del 86",   # chunk después del gap — sin marcadores 75-85
    ]
    chunk_results = [
        {"proveedores": [], "renglones": [{"renglon": 73, "proveedores_precios": {}}]},
        {"proveedores": [], "renglones": [{"renglon": 86, "proveedores_precios": {}}]},
    ]
    with patch("app.robot_comparativas._llamar_gemini_json") as mock_gemini:
        new_renglones, new_providers = _reintentar_gaps(gaps, markdowns, chunk_results)

    # Pre-check detecta que los ítems no están en el markdown → 0 API calls
    mock_gemini.assert_not_called()
    assert new_renglones == []


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
