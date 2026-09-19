"""
Tests unitarios para services/extraccion/robot_orden_compra.py — Tramo 1 (extracción).

Mockean la llamada a Gemini (`_llamar_gemini_orden_compra`) y el parseo de documento
(`parse_document`) para ejercitar `procesar_orden_compra()` de punta a punta sin red,
y prueban `_construir_filas()` como función pura sin ningún mock (0 mocks — transformación
de datos, ver strict-tdd.md § Mock Hygiene Rules / Extract-Before-Mock Rule).

Cubre (2.2, tasks.md):
  - CSV escrito en disco con delimitador ';', UTF-8, csv.QUOTE_MINIMAL
    (igual que robot_comparativas.py:850-859).
  - Columnas de D6 en el orden correcto.
  - Caso sin número de línea → celda vacía sin excepción (C10).
  - Plan de entregas con gramática "50@30|50@60" se escribe tal cual (sin parsear).
"""

import csv
from pathlib import Path

import pytest

from services.extraccion.robot_orden_compra import (
    _FIELDNAMES,
    _construir_filas,
    procesar_orden_compra,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _datos_oc4471() -> dict:
    """Cabecera + 2 renglones, con numero_renglon declarado (caso D6 estándar)."""
    return {
        "numero_oc": "OC-4471",
        "fecha_emision": "12/09/2026",
        "cuit_cliente": "30712345679",
        "razon_social_cliente": "HOSPITAL SAN ROQUE",
        "direccion_entrega": "Av. Siempreviva 742",
        "cantidad_entregas": "2",
        "renglones": [
            {
                "numero_renglon": "1",
                "descripcion": "IBUPROFENO 400MG X 20",
                "cantidad": "100",
                "precio_unitario": "1250,00",
                "entregas": "50@30|50@60",
            },
            {
                "numero_renglon": "2",
                "descripcion": "AMOXICILINA 500MG X 16",
                "cantidad": "80",
                "precio_unitario": "980,50",
                "entregas": "",
            },
        ],
    }


def _datos_oc9012_sin_numero_renglon() -> dict:
    """Cabecera + 2 renglones donde el documento NO declara número de línea (C10)."""
    return {
        "numero_oc": "OC-9012",
        "fecha_emision": "03/09/2026",
        "cuit_cliente": "30555555553",
        "razon_social_cliente": "CLINICA DEL SOL",
        "direccion_entrega": "Ruta 9 km 12",
        "cantidad_entregas": "1",
        "renglones": [
            {
                "numero_renglon": "",
                "descripcion": "GASA ESTERIL 10X10",
                "cantidad": "40",
                "precio_unitario": "320,00",
                "entregas": "",
            },
            {
                "numero_renglon": "",
                "descripcion": "ALCOHOL EN GEL 250ML",
                "cantidad": "25",
                "precio_unitario": "410,00",
                "entregas": "",
            },
        ],
    }


def _leer_csv_crudo(csv_path: Path) -> list[str]:
    return csv_path.read_text(encoding="utf-8").splitlines()


# ---------------------------------------------------------------------------
# _construir_filas — función pura, SIN mocks (Extract-Before-Mock Rule)
# ---------------------------------------------------------------------------

class TestConstruirFilas:
    """_construir_filas() es pura: JSON de Gemini -> list[dict] listas para csv.DictWriter."""

    def test_repite_cabecera_por_renglon_en_orden_d6(self):
        filas = _construir_filas(_datos_oc4471())

        assert len(filas) == 2
        assert list(filas[0].keys()) == _FIELDNAMES
        assert filas[0]["numero_oc"] == "OC-4471"
        assert filas[0]["razon_social_cliente"] == "HOSPITAL SAN ROQUE"
        assert filas[1]["numero_oc"] == "OC-4471"
        assert filas[1]["razon_social_cliente"] == "HOSPITAL SAN ROQUE"

    def test_numero_renglon_vacio_no_se_fabrica(self):
        """C10: sin número de línea en el documento -> celda vacía en TODAS las filas,
        nunca autoincrementado ni derivado del orden de aparición."""
        filas = _construir_filas(_datos_oc9012_sin_numero_renglon())

        assert len(filas) == 2
        assert filas[0]["numero_renglon"] == ""
        assert filas[1]["numero_renglon"] == ""

    def test_numero_renglon_declarado_se_preserva_tal_cual(self):
        filas = _construir_filas(_datos_oc4471())

        assert filas[0]["numero_renglon"] == "1"
        assert filas[1]["numero_renglon"] == "2"

    def test_gramatica_de_entregas_se_preserva_verbatim(self):
        """El parseo de "50@30|50@60" ocurre después, en validación — acá se escribe
        tal cual, sin tocar la gramática."""
        filas = _construir_filas(_datos_oc4471())

        assert filas[0]["entregas"] == "50@30|50@60"
        assert filas[1]["entregas"] == ""

    def test_renglones_vacio_produce_lista_vacia_sin_excepcion(self):
        datos = _datos_oc4471()
        datos["renglones"] = []

        assert _construir_filas(datos) == []


# ---------------------------------------------------------------------------
# procesar_orden_compra — mockea Gemini + parseo de documento
# ---------------------------------------------------------------------------

class TestProcesarOrdenCompra:
    def test_escribe_csv_con_columnas_d6_delimitador_y_encoding_correctos(
        self, tmp_path, mocker
    ):
        origen = tmp_path / "HOSPITALSANROQUE_orden.pdf"
        origen.write_bytes(b"%PDF-1.4 contenido de prueba")

        mocker.patch(
            "services.extraccion.robot_orden_compra.parse_document",
            return_value="markdown de prueba",
        )
        mocker.patch(
            "services.extraccion.robot_orden_compra._llamar_gemini_orden_compra",
            return_value=_datos_oc4471(),
        )
        mocker.patch(
            "services.extraccion.robot_orden_compra.get_output_dir",
            return_value=tmp_path,
        )
        mocker.patch(
            "services.extraccion.robot_orden_compra.get_processed_dir",
            return_value=tmp_path / "Procesados",
        )
        (tmp_path / "Procesados").mkdir(exist_ok=True)

        csv_path = procesar_orden_compra(origen, "HOSPITALSANROQUE_orden.pdf")

        assert csv_path.exists()
        assert csv_path.suffix == ".csv"

        lineas = _leer_csv_crudo(csv_path)
        assert lineas[0] == ";".join(_FIELDNAMES)
        assert len(lineas) == 3  # header + 2 renglones

        with open(csv_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f, delimiter=";", quoting=csv.QUOTE_MINIMAL)
            filas = list(reader)
        assert filas[0] == _FIELDNAMES
        assert filas[1][_FIELDNAMES.index("numero_oc")] == "OC-4471"
        assert filas[1][_FIELDNAMES.index("entregas")] == "50@30|50@60"

    def test_caso_sin_numero_de_linea_no_lanza_excepcion(self, tmp_path, mocker):
        """C10, regresión directa: el documento no numera renglones -> extracción
        completa sin fallar, celda vacía en todas las filas del CSV."""
        origen = tmp_path / "CLINICADELSOL_orden.xlsx"
        origen.write_bytes(b"PK\x03\x04 contenido xlsx de prueba")

        mocker.patch(
            "services.extraccion.robot_orden_compra.parse_document",
            return_value="markdown de prueba",
        )
        mocker.patch(
            "services.extraccion.robot_orden_compra._llamar_gemini_orden_compra",
            return_value=_datos_oc9012_sin_numero_renglon(),
        )
        mocker.patch(
            "services.extraccion.robot_orden_compra.get_output_dir",
            return_value=tmp_path,
        )
        mocker.patch(
            "services.extraccion.robot_orden_compra.get_processed_dir",
            return_value=tmp_path / "Procesados",
        )
        (tmp_path / "Procesados").mkdir(exist_ok=True)

        csv_path = procesar_orden_compra(origen, "CLINICADELSOL_orden.xlsx")

        with open(csv_path, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f, delimiter=";")
            filas = list(reader)

        assert len(filas) == 2
        assert filas[0]["numero_renglon"] == ""
        assert filas[1]["numero_renglon"] == ""

    def test_sin_renglones_extraidos_lanza_excepcion(self, tmp_path, mocker):
        """Documento sin ningún renglón detectado (Gemini no encontró items) -> falla
        explícitamente en vez de escribir un CSV vacío (mismo principio que
        robot_comparativas.NoProvidersDetectedError)."""
        from services.extraccion.robot_orden_compra import OrdenCompraSinRenglonesError

        origen = tmp_path / "ORIGEN_orden.pdf"
        origen.write_bytes(b"%PDF-1.4 contenido de prueba")

        datos_vacios = _datos_oc4471()
        datos_vacios["renglones"] = []

        mocker.patch(
            "services.extraccion.robot_orden_compra.parse_document",
            return_value="markdown de prueba",
        )
        mocker.patch(
            "services.extraccion.robot_orden_compra._llamar_gemini_orden_compra",
            return_value=datos_vacios,
        )
        mocker.patch(
            "services.extraccion.robot_orden_compra.get_output_dir",
            return_value=tmp_path,
        )

        with pytest.raises(OrdenCompraSinRenglonesError):
            procesar_orden_compra(origen, "ORIGEN_orden.pdf")
