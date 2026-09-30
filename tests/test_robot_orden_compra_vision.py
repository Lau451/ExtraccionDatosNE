"""
Tests de la ruta Gemini Vision para órdenes de compra escaneadas.

Un PDF sin capa de texto ya no pasa por OCR -> Markdown (docling + RapidOCR, que
leía "800" como "008" y dejaba vacío el renglón con número centrado): se le manda
el PDF mismo a Gemini. Todo lo demás (PDF con texto, Excel, etc.) queda igual.

Gemini y el parser se mockean (sin red); los PDF fixture se arman con PyMuPDF.
"""

import csv
import json
from types import SimpleNamespace

import fitz
import pytest

from services.extraccion import robot_orden_compra as robot
from services.extraccion.gemini_errors import GeminiTruncationError

_DATOS = {
    "numero_oc": "OC-1",
    "renglones": [
        {"numero_renglon": "16", "descripcion": "BISACODILO", "cantidad": "800"},
    ],
}


def _pdf_con_texto(path):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Orden de compra " + "texto nativo de prueba " * 10)
    doc.save(str(path))
    doc.close()
    return path


def _pdf_escaneado(path):
    """PDF de solo imagen: sin capa de texto."""
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 40), False)
    pix.clear_with(255)
    doc = fitz.open()
    page = doc.new_page()
    page.insert_image(page.rect, pixmap=pix)
    doc.save(str(path))
    doc.close()
    return path


def _respuesta(texto, finish_reason="STOP"):
    return SimpleNamespace(
        text=texto, candidates=[SimpleNamespace(finish_reason=finish_reason)]
    )


@pytest.fixture
def entorno(tmp_path, mocker):
    (tmp_path / "Procesados").mkdir()
    mocker.patch.object(robot, "get_output_dir", return_value=tmp_path)
    mocker.patch.object(robot, "get_processed_dir", return_value=tmp_path / "Procesados")
    return tmp_path


class TestEsPdfEscaneado:
    def test_pdf_solo_imagen_es_escaneado(self, tmp_path):
        assert robot._es_pdf_escaneado(_pdf_escaneado(tmp_path / "a.pdf")) is True

    def test_pdf_con_texto_no_es_escaneado(self, tmp_path):
        assert robot._es_pdf_escaneado(_pdf_con_texto(tmp_path / "b.pdf")) is False

    def test_archivo_ilegible_no_es_escaneado(self, tmp_path):
        roto = tmp_path / "c.pdf"
        roto.write_bytes(b"%PDF-1.4 basura")
        assert robot._es_pdf_escaneado(roto) is False

    def test_no_pdf_no_es_escaneado(self, tmp_path):
        xlsx = tmp_path / "d.xlsx"
        xlsx.write_bytes(b"PK")
        assert robot._es_pdf_escaneado(xlsx) is False


class TestProcesarRutas:
    def test_pdf_escaneado_usa_vision_y_no_el_parser_ocr(self, entorno, mocker):
        origen = _pdf_escaneado(entorno / "HOSPITAL_scan.pdf")
        parser = mocker.patch.object(robot, "parse_document_orden_compra")
        gemini = mocker.patch.object(robot, "_llamar_gemini_orden_compra", return_value=_DATOS)

        csv_path = procesar(origen, instrucciones_extra="Renglon = columna 1")

        parser.assert_not_called()
        kwargs = gemini.call_args.kwargs
        assert kwargs["documento_pdf"].startswith(b"%PDF")
        assert "Renglon = columna 1" in kwargs["prompt"]
        with open(csv_path, encoding="utf-8", newline="") as f:
            fila = next(csv.DictReader(f, delimiter=";"))
        assert fila["cantidad"] == "800"

    def test_pdf_con_texto_sigue_por_markdown(self, entorno, mocker):
        origen = _pdf_con_texto(entorno / "HOSPITAL_nativo.pdf")
        parser = mocker.patch.object(
            robot, "parse_document_orden_compra", return_value="# markdown"
        )
        gemini = mocker.patch.object(robot, "_llamar_gemini_orden_compra", return_value=_DATOS)

        procesar(origen)

        parser.assert_called_once()
        assert gemini.call_args.args == ("# markdown",)
        assert gemini.call_args.kwargs.get("documento_pdf") is None

    def test_excel_no_evalua_vision(self, entorno, mocker):
        origen = entorno / "CLIENTE_orden.xlsx"
        origen.write_bytes(b"PK")
        mocker.patch.object(robot, "parse_document_orden_compra", return_value="md")
        gemini = mocker.patch.object(robot, "_llamar_gemini_orden_compra", return_value=_DATOS)

        procesar(origen)

        assert gemini.call_args.kwargs.get("documento_pdf") is None


def procesar(origen, **kwargs):
    return robot.procesar_orden_compra(origen, origen.name, **kwargs)


class TestLlamadaGeminiVision:
    def _llamar(self, mocker, respuesta, **kwargs):
        mocker.patch.object(robot, "get_next_client", return_value=object())
        gen = mocker.patch.object(robot, "generate_with_fallback", return_value=respuesta)
        # sin backoff real en los reintentos del decorador
        mocker.patch("time.sleep")
        return gen, robot._llamar_gemini_orden_compra("", **kwargs)

    def test_envia_pdf_y_prompt_como_partes(self, mocker):
        gen, datos = self._llamar(
            mocker, _respuesta(json.dumps(_DATOS)), prompt="PROMPT X", documento_pdf=b"%PDF-bytes"
        )
        contents = gen.call_args.args[1]
        assert isinstance(contents, list)
        parte_pdf = contents[0]
        assert parte_pdf.inline_data.mime_type == "application/pdf"
        assert parte_pdf.inline_data.data == b"%PDF-bytes"
        assert contents[1] == "PROMPT X"
        assert datos["numero_oc"] == "OC-1"

    def test_sin_pdf_envia_prompt_mas_markdown_como_antes(self, mocker):
        mocker.patch.object(robot, "get_next_client", return_value=object())
        gen = mocker.patch.object(
            robot, "generate_with_fallback", return_value=_respuesta(json.dumps(_DATOS))
        )
        robot._llamar_gemini_orden_compra("MD", prompt="P")
        assert gen.call_args.args[1] == "P\n\nMD"

    def test_truncamiento_lanza_error_tambien_en_vision(self, mocker):
        mocker.patch.object(robot, "get_next_client", return_value=object())
        mocker.patch.object(
            robot, "generate_with_fallback", return_value=_respuesta("{}", "FinishReason.MAX_TOKENS")
        )
        mocker.patch("time.sleep")
        with pytest.raises(GeminiTruncationError):
            robot._llamar_gemini_orden_compra("", documento_pdf=b"%PDF")

    def test_json_invalido_lanza_error_tambien_en_vision(self, mocker):
        mocker.patch.object(robot, "get_next_client", return_value=object())
        mocker.patch.object(robot, "generate_with_fallback", return_value=_respuesta("no json"))
        mocker.patch("time.sleep")
        with pytest.raises(GeminiTruncationError):
            robot._llamar_gemini_orden_compra("", documento_pdf=b"%PDF")
