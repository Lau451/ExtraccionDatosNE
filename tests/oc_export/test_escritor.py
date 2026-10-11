import csv
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from services.presupuestacion.oc_export import escritor
from services.presupuestacion.oc_export.escritor import (
    carpeta_oc,
    construir_nombre,
    escribir_csv,
)
from services.presupuestacion.oc_export.filas import ENCABEZADOS
from services.shared.exceptions import ConflictError

_BA = ZoneInfo("America/Argentina/Buenos_Aires")


def _fila(descripcion="Ñandú áéíóú"):
    fila = [""] * len(ENCABEZADOS)
    fila[9] = descripcion
    return fila


def _leer(path, encoding="cp1252"):
    with open(path, encoding=encoding, newline="") as f:
        return list(csv.reader(f))


def test_nombre_deterministico_con_timestamp_inyectado():
    ahora = datetime(2026, 10, 5, 9, 8, 7, tzinfo=_BA)
    assert (
        construir_nombre("C01", "4500-1", 3, ahora=ahora)
        == "OC_C01_4500-1_v3_20261005090807.csv"
    )


def test_nombre_sanea_caracteres_invalidos():
    ahora = datetime(2026, 10, 5, 9, 8, 7, tzinfo=_BA)
    nombre = construir_nombre(" C/01 ", "45 00/1:ñ", 1, ahora=ahora)
    assert nombre == "OC_C-01_45-00-1--_v1_20261005090807.csv"


def test_nombre_usa_hora_de_buenos_aires():
    utc = datetime(2026, 10, 5, 12, 0, 0, tzinfo=ZoneInfo("UTC"))
    assert construir_nombre("C", "1", 1, ahora=utc).endswith("_20261005090000.csv")


def test_carpeta_oc(tmp_path):
    assert carpeta_oc(str(tmp_path)) == tmp_path / "oc"


def test_escribe_cp1252_con_encabezado_y_acentos(tmp_path):
    destino = escribir_csv(
        [_fila()], carpeta=tmp_path / "oc", nombre="a.csv", encoding="cp1252"
    )
    assert destino == tmp_path / "oc" / "a.csv"
    assert b"\xd1and\xfa" in destino.read_bytes()
    filas = _leer(destino)
    assert filas[0] == ENCABEZADOS
    assert filas[1][9] == "Ñandú áéíóú"


def test_coma_y_comillas_hacen_roundtrip(tmp_path):
    desc = 'Caja "x 20", sin fraccionar'
    destino = escribir_csv([_fila(desc)], carpeta=tmp_path, nombre="a.csv", encoding="cp1252")
    assert _leer(destino)[1][9] == desc


def test_emoji_se_reemplaza_por_signo_de_pregunta(tmp_path):
    destino = escribir_csv([_fila("Caja 😀")], carpeta=tmp_path, nombre="a.csv", encoding="cp1252")
    assert _leer(destino)[1][9] == "Caja ?"


def test_fin_de_linea_crlf(tmp_path):
    destino = escribir_csv([_fila()], carpeta=tmp_path, nombre="a.csv", encoding="cp1252")
    datos = destino.read_bytes()
    assert datos.count(b"\r\n") == 2
    assert datos.replace(b"\r\n", b"").count(b"\n") == 0


def test_sin_temporales_en_exito(tmp_path):
    escribir_csv([_fila()], carpeta=tmp_path, nombre="a.csv", encoding="cp1252")
    assert [p.name for p in tmp_path.iterdir()] == ["a.csv"]


def test_sin_temporales_ni_final_si_falla_a_mitad(tmp_path, monkeypatch):
    class _WriterRoto:
        def __init__(self, *a, **k):
            pass

        def writerow(self, fila):
            pass

        def writerows(self, filas):
            raise RuntimeError("boom")

    monkeypatch.setattr(escritor.csv, "writer", _WriterRoto)
    with pytest.raises(RuntimeError):
        escribir_csv([_fila()], carpeta=tmp_path, nombre="a.csv", encoding="cp1252")
    assert list(tmp_path.iterdir()) == []


def test_sin_temporales_si_falla_el_renombrado(tmp_path, monkeypatch):
    def _roto(*a, **k):
        raise OSError("sin permiso")

    monkeypatch.setattr(escritor.os, "replace", _roto)
    with pytest.raises(OSError):
        escribir_csv([_fila()], carpeta=tmp_path, nombre="a.csv", encoding="cp1252")
    assert list(tmp_path.iterdir()) == []


def test_no_pisa_archivo_existente(tmp_path):
    existente = tmp_path / "a.csv"
    existente.write_bytes(b"original")
    with pytest.raises(ConflictError):
        escribir_csv([_fila()], carpeta=tmp_path, nombre="a.csv", encoding="cp1252")
    assert existente.read_bytes() == b"original"
    assert [p.name for p in tmp_path.iterdir()] == ["a.csv"]
