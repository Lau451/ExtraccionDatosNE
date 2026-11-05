import csv
import errno
import os
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from services.integracion_progress.salida import escritor
from services.integracion_progress.salida.escritor import (
    borrar_archivo,
    carpeta_oc,
    construir_nombre,
    escribir_csv,
)
from services.shared.exceptions import ConflictError

_BA = ZoneInfo("America/Argentina/Buenos_Aires")
# El escritor no conoce las columnas de ningún tipo: recibe los encabezados.
ENCABEZADOS = [f"columna_{i}" for i in range(12)]


def _fila(descripcion="Ñandú áéíóú"):
    fila = [""] * len(ENCABEZADOS)
    fila[9] = descripcion
    return fila


def _leer(path, encoding="cp1252"):
    with open(path, encoding=encoding, newline="") as f:
        return list(csv.reader(f, delimiter=";"))


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
        ENCABEZADOS, [_fila()], carpeta=tmp_path / "oc", nombre="a.csv", encoding="cp1252"
    )
    assert destino == tmp_path / "oc" / "a.csv"
    assert b"\xd1and\xfa" in destino.read_bytes()
    filas = _leer(destino)
    assert filas[0] == ENCABEZADOS
    assert filas[1][9] == "Ñandú áéíóú"


def test_campos_separados_por_punto_y_coma(tmp_path):
    fila = _fila("Caja x 20")
    fila[0] = "1520.50"
    destino = escribir_csv(ENCABEZADOS, [fila], carpeta=tmp_path, nombre="a.csv", encoding="cp1252")
    lineas = destino.read_bytes().decode("cp1252").split("\r\n")
    assert lineas[0] == ";".join(ENCABEZADOS)
    assert lineas[1] == ";".join(fila)


def test_punto_y_coma_y_comillas_hacen_roundtrip(tmp_path):
    desc = 'Caja "x 20"; sin fraccionar'
    destino = escribir_csv(ENCABEZADOS, [_fila(desc)], carpeta=tmp_path, nombre="a.csv", encoding="cp1252")
    assert _leer(destino)[1][9] == desc


def test_coma_y_comillas_hacen_roundtrip(tmp_path):
    desc = 'Caja "x 20", sin fraccionar'
    destino = escribir_csv(ENCABEZADOS, [_fila(desc)], carpeta=tmp_path, nombre="a.csv", encoding="cp1252")
    assert _leer(destino)[1][9] == desc


def test_emoji_se_reemplaza_por_signo_de_pregunta(tmp_path):
    destino = escribir_csv(ENCABEZADOS, [_fila("Caja 😀")], carpeta=tmp_path, nombre="a.csv", encoding="cp1252")
    assert _leer(destino)[1][9] == "Caja ?"


def test_fin_de_linea_crlf(tmp_path):
    destino = escribir_csv(ENCABEZADOS, [_fila()], carpeta=tmp_path, nombre="a.csv", encoding="cp1252")
    datos = destino.read_bytes()
    assert datos.count(b"\r\n") == 2
    assert datos.replace(b"\r\n", b"").count(b"\n") == 0


def test_sin_temporales_en_exito(tmp_path):
    escribir_csv(ENCABEZADOS, [_fila()], carpeta=tmp_path, nombre="a.csv", encoding="cp1252")
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
        escribir_csv(ENCABEZADOS, [_fila()], carpeta=tmp_path, nombre="a.csv", encoding="cp1252")
    assert list(tmp_path.iterdir()) == []


def test_sin_temporales_si_falla_el_renombrado(tmp_path, monkeypatch):
    def _roto(*a, **k):
        raise OSError("sin permiso")

    for nombre in ("rename", "link", "replace"):
        monkeypatch.setattr(escritor.os, nombre, _roto)
    with pytest.raises(OSError):
        escribir_csv(ENCABEZADOS, [_fila()], carpeta=tmp_path, nombre="a.csv", encoding="cp1252")
    assert list(tmp_path.iterdir()) == []


def test_no_pisa_archivo_existente(tmp_path):
    existente = tmp_path / "a.csv"
    existente.write_bytes(b"original")
    with pytest.raises(ConflictError):
        escribir_csv(ENCABEZADOS, [_fila()], carpeta=tmp_path, nombre="a.csv", encoding="cp1252")
    assert existente.read_bytes() == b"original"
    assert [p.name for p in tmp_path.iterdir()] == ["a.csv"]


class _SistemaFalso:
    """Fuerza la rama de `_publicar` con la semántica de cada sistema, sin depender
    del sistema donde corre el test: `os.rename` de Windows falla si el destino
    existe (en POSIX lo pisaría) y `os.link` de POSIX falla si existe (y no se
    depende de que el disco tenga hard links)."""

    def __init__(self, monkeypatch, sistema, *, error_link=None):
        self.llamadas: list[str] = []
        self._replace_real = os.replace
        self._error_link = error_link
        monkeypatch.setattr(escritor.os, "name", sistema)
        monkeypatch.setattr(escritor.os, "rename", self._rename)
        monkeypatch.setattr(escritor.os, "link", self._link)
        monkeypatch.setattr(escritor.os, "replace", self._replace)

    def _rename(self, origen, destino):
        self.llamadas.append("rename")
        if Path(destino).exists():
            raise FileExistsError(errno.EEXIST, "existe", str(destino))
        self._replace_real(origen, destino)

    def _link(self, origen, destino):
        self.llamadas.append("link")
        if self._error_link is not None:
            raise OSError(self._error_link, "sin hard links")
        if Path(destino).exists():
            raise FileExistsError(errno.EEXIST, "existe", str(destino))
        shutil.copyfile(origen, destino)

    def _replace(self, origen, destino):
        self.llamadas.append("replace")
        self._replace_real(origen, destino)


def _carrera_que_crea(monkeypatch, existente):
    """Otro proceso crea `existente` después del chequeo previo, mientras se escribe."""
    writer_real = escritor.csv.writer

    def writer_con_carrera(*args, **kwargs):
        existente.write_bytes(b"del otro proceso")
        return writer_real(*args, **kwargs)

    monkeypatch.setattr(escritor.csv, "writer", writer_con_carrera)


@pytest.mark.parametrize(
    ("sistema", "llamadas"), [("nt", ["rename"]), ("posix", ["link"])]
)
def test_publica_sin_temporales_en_cada_sistema(tmp_path, monkeypatch, sistema, llamadas):
    falso = _SistemaFalso(monkeypatch, sistema)

    destino = escribir_csv(ENCABEZADOS, [_fila()], carpeta=tmp_path, nombre="a.csv", encoding="cp1252")

    assert falso.llamadas == llamadas
    assert [p.name for p in tmp_path.iterdir()] == ["a.csv"]
    assert _leer(destino)[1][9] == "Ñandú áéíóú"


@pytest.mark.parametrize(
    ("sistema", "llamadas"), [("nt", ["rename"]), ("posix", ["link"])]
)
def test_no_pisa_un_archivo_que_aparece_mientras_escribe(tmp_path, monkeypatch, sistema, llamadas):
    # R3-002 (T1): entre el chequeo de existencia y el renombrado otro proceso crea el
    # mismo nombre; os.replace lo pisaba.
    falso = _SistemaFalso(monkeypatch, sistema)
    existente = tmp_path / "a.csv"
    _carrera_que_crea(monkeypatch, existente)

    with pytest.raises(ConflictError) as error:
        escribir_csv(ENCABEZADOS, [_fila()], carpeta=tmp_path, nombre="a.csv", encoding="cp1252")

    assert error.value.message == "Ya existe el archivo a.csv"
    assert falso.llamadas == llamadas
    assert existente.read_bytes() == b"del otro proceso"
    assert [p.name for p in tmp_path.iterdir()] == ["a.csv"]


# --- T8: observaciones de la revisión de T7 (L15) ---------------------------------


@pytest.mark.parametrize("error_link", sorted(e for e in escritor._SIN_HARD_LINKS if e > 0))
def test_sin_hard_links_publica_con_replace(tmp_path, monkeypatch, error_link):
    # R3-publicar-fallback-unproved: un disco sin hard links cae al chequeo + replace.
    falso = _SistemaFalso(monkeypatch, "posix", error_link=error_link)

    destino = escribir_csv(ENCABEZADOS, [_fila()], carpeta=tmp_path, nombre="a.csv", encoding="cp1252")

    assert falso.llamadas == ["link", "replace"]
    assert [p.name for p in tmp_path.iterdir()] == ["a.csv"]
    assert _leer(destino)[1][9] == "Ñandú áéíóú"


def test_sin_hard_links_no_pisa_un_archivo_que_aparece_mientras_escribe(tmp_path, monkeypatch):
    falso = _SistemaFalso(monkeypatch, "posix", error_link=errno.EXDEV)
    existente = tmp_path / "a.csv"
    _carrera_que_crea(monkeypatch, existente)

    with pytest.raises(ConflictError) as error:
        escribir_csv(ENCABEZADOS, [_fila()], carpeta=tmp_path, nombre="a.csv", encoding="cp1252")

    assert error.value.message == "Ya existe el archivo a.csv"
    assert falso.llamadas == ["link"]
    assert existente.read_bytes() == b"del otro proceso"
    assert [p.name for p in tmp_path.iterdir()] == ["a.csv"]


def test_falla_al_borrar_el_temporal_tras_el_link_no_es_una_falla_de_escritura(
    tmp_path, monkeypatch, caplog
):
    # R3-publicar-unlink-after-link / R4: con el link hecho el archivo ya está
    # publicado; informar una falla haría que el llamador no lo registre.
    falso = _SistemaFalso(monkeypatch, "posix")
    unlink_real = Path.unlink

    def unlink_roto(self, *args, **kwargs):
        if self.name == ".a.csv.tmp":
            raise PermissionError(errno.EACCES, "en uso", str(self))
        return unlink_real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", unlink_roto)

    destino = escribir_csv(ENCABEZADOS, [_fila()], carpeta=tmp_path, nombre="a.csv", encoding="cp1252")

    assert destino == tmp_path / "a.csv"
    assert falso.llamadas == ["link"]
    assert _leer(destino)[1][9] == "Ñandú áéíóú"
    assert sorted(p.name for p in tmp_path.iterdir()) == [".a.csv.tmp", "a.csv"]
    assert ".a.csv.tmp" in caplog.text


def test_borrar_archivo_borra_y_tolera_que_ya_no_exista(tmp_path):
    destino = escribir_csv(ENCABEZADOS, [_fila()], carpeta=tmp_path, nombre="a.csv", encoding="cp1252")
    borrar_archivo(destino)
    assert list(tmp_path.iterdir()) == []
    borrar_archivo(destino)
