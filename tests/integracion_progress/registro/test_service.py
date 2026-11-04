"""tests/integracion_progress/registro/test_service.py -- registro de archivos de
Progress (odd/tasks/integracion-progress.md S3): duplicados, reproceso de errores,
carrera de inserción y conteo de intentos. Unitarios con el repository falso de
conftest.py."""

import hashlib
from unittest.mock import MagicMock

import pytest
from postgrest.exceptions import APIError

from services.integracion_progress.registro import service
from services.integracion_progress.registro.models import ErrorLinea
from services.shared.exceptions import NotFoundError, ValidationError

CONTENIDO = "numero;cliente\n1;ACME\n".encode("utf-8")
SHA = hashlib.sha256(CONTENIDO).hexdigest()


def _registrar(contenido=CONTENIDO, **kwargs):
    params = {
        "drogueria_id": "drog-1",
        "tipo": "presupuestos",
        "nombre_archivo": "PRESUPUESTOS_20261104120000.csv",
        "contenido": contenido,
        "origen": "carpeta",
        "usuario_id": "usuario-sistema",
    }
    params.update(kwargs)
    return service.registrar_entrada(MagicMock(), **params)


def test_archivo_nuevo_se_inserta_como_recibido(repo_falso):
    registro, es_duplicado = _registrar()

    assert es_duplicado is False
    assert registro.estado == "recibido"
    assert registro.sentido == "entrada"
    assert registro.sha256 == SHA
    assert registro.intentos == 0
    assert repo_falso.inserts == [
        {
            "drogueria_id": "drog-1",
            "sentido": "entrada",
            "tipo": "presupuestos",
            "nombre_archivo": "PRESUPUESTOS_20261104120000.csv",
            "sha256": SHA,
            "origen": "carpeta",
            "estado": "recibido",
            "usuario_id": "usuario-sistema",
        }
    ]


@pytest.mark.parametrize("estado", ["procesado", "recibido"])
def test_mismo_contenido_es_duplicado_y_no_escribe_nada(repo_falso, estado):
    procesado_at = "2026-11-04T12:05:00+00:00" if estado == "procesado" else None
    existente = repo_falso.sembrar(sha256=SHA, estado=estado, procesado_at=procesado_at)

    registro, es_duplicado = _registrar(nombre_archivo="OTRO_NOMBRE.csv", origen="manual")

    assert es_duplicado is True
    assert registro.id == existente["id"]
    assert registro.nombre_archivo == existente["nombre_archivo"]
    assert repo_falso.inserts == []
    assert repo_falso.updates == []
    assert len(repo_falso.filas) == 1


def test_mismo_contenido_de_otro_tipo_o_droguerias_no_es_duplicado(repo_falso):
    repo_falso.sembrar(sha256=SHA, estado="procesado", procesado_at="2026-11-04T12:05:00+00:00")

    _, dup_otro_tipo = _registrar(tipo="stock")
    _, dup_otra_drog = _registrar(drogueria_id="drog-2")

    assert dup_otro_tipo is False
    assert dup_otra_drog is False
    assert len(repo_falso.inserts) == 2


def test_registro_en_error_se_devuelve_para_reprocesar(repo_falso):
    existente = repo_falso.sembrar(
        sha256=SHA, estado="error", intentos=1, errores=[{"linea": 2, "mensaje": "x"}]
    )

    registro, es_duplicado = _registrar()

    assert es_duplicado is False
    assert registro.id == existente["id"]
    assert registro.estado == "error"
    assert registro.errores == [ErrorLinea(linea=2, mensaje="x")]
    assert repo_falso.inserts == []
    assert repo_falso.updates == []


def test_carrera_de_insercion_relee_la_ganadora_como_duplicado(repo_falso):
    ganadora = {}

    def otro_proceso_inserta_primero():
        ganadora.update(repo_falso.sembrar(sha256=SHA, origen="manual"))

    repo_falso.antes_de_insertar = otro_proceso_inserta_primero

    registro, es_duplicado = _registrar()

    assert es_duplicado is True
    assert registro.id == ganadora["id"]
    assert registro.origen == "manual"
    assert repo_falso.inserts == []
    assert len(repo_falso.filas) == 1


def test_error_de_insercion_que_no_es_unique_se_propaga(repo_falso, monkeypatch):
    def falla(client, fila):
        raise APIError({"code": "23503", "message": "fk violation"})

    monkeypatch.setattr(service.repo, "insertar", falla)

    with pytest.raises(APIError):
        _registrar()


def test_sha256_es_de_los_bytes_crudos(repo_falso):
    con_bom = b"\xef\xbb\xbf" + CONTENIDO
    cp1252 = "descripción;1\n".encode("cp1252")

    registro_bom, _ = _registrar(contenido=con_bom)
    registro_cp, _ = _registrar(contenido=cp1252)
    registro_plano, _ = _registrar()

    assert registro_bom.sha256 == hashlib.sha256(con_bom).hexdigest()
    assert registro_cp.sha256 == hashlib.sha256(cp1252).hexdigest()
    assert registro_plano.sha256 == SHA
    assert len({registro_bom.sha256, registro_cp.sha256, registro_plano.sha256}) == 3


@pytest.mark.parametrize(
    ("campo", "valor"), [("origen", "ftp"), ("tipo", ""), ("nombre_archivo", "  ")]
)
def test_entrada_invalida_no_escribe(repo_falso, campo, valor):
    with pytest.raises(ValidationError):
        _registrar(**{campo: valor})

    assert repo_falso.inserts == []


def test_marcar_error_incrementa_intentos_y_guarda_errores(repo_falso):
    existente = repo_falso.sembrar(sha256=SHA)
    errores = [ErrorLinea(linea=3, mensaje="Falta el cliente"), {"linea": 7, "mensaje": "Fecha inválida"}]

    primero = service.marcar_error(MagicMock(), registro_id=existente["id"], errores=errores)
    segundo = service.marcar_error(
        MagicMock(), registro_id=existente["id"], errores=[{"linea": 1, "mensaje": "otra"}]
    )

    assert primero.estado == "error"
    assert primero.intentos == 1
    assert primero.errores == [
        ErrorLinea(linea=3, mensaje="Falta el cliente"),
        ErrorLinea(linea=7, mensaje="Fecha inválida"),
    ]
    assert primero.procesado_at is None
    assert segundo.intentos == 2
    assert segundo.errores == [ErrorLinea(linea=1, mensaje="otra")]
    assert repo_falso.updates[0][1]["errores"] == [
        {"linea": 3, "mensaje": "Falta el cliente"},
        {"linea": 7, "mensaje": "Fecha inválida"},
    ]


def test_marcar_error_reintenta_si_otro_proceso_cambio_intentos(repo_falso):
    existente = repo_falso.sembrar(sha256=SHA, estado="error", intentos=1)

    def otro_proceso_marca_error():
        repo_falso.filas[existente["id"]]["intentos"] = 2

    repo_falso.antes_de_actualizar = otro_proceso_marca_error

    registro = service.marcar_error(MagicMock(), registro_id=existente["id"], errores=[])

    assert registro.intentos == 3


def test_marcar_error_de_registro_inexistente(repo_falso):
    with pytest.raises(NotFoundError):
        service.marcar_error(MagicMock(), registro_id="no-existe", errores=[])


def test_marcar_procesado_guarda_filas_y_fecha(repo_falso):
    existente = repo_falso.sembrar(sha256=SHA, estado="error", intentos=1, errores=[{"linea": 1, "mensaje": "x"}])

    registro = service.marcar_procesado(MagicMock(), registro_id=existente["id"], filas=12)

    assert registro.estado == "procesado"
    assert registro.filas == 12
    assert registro.procesado_at is not None
    assert registro.errores is None
    assert registro.intentos == 1


def test_marcar_procesado_de_registro_inexistente(repo_falso):
    with pytest.raises(NotFoundError):
        service.marcar_procesado(MagicMock(), registro_id="no-existe", filas=0)


def test_registrar_salida_queda_procesada_sin_origen(repo_falso):
    contenido = b"OC;1\n"

    registro = service.registrar_salida(
        MagicMock(),
        drogueria_id="drog-1",
        tipo="oc",
        nombre_archivo="OC_ACME_1_v1_20261104120000.csv",
        contenido=contenido,
        usuario_id="usuario-1",
    )

    assert registro.sentido == "salida"
    assert registro.origen is None
    assert registro.estado == "procesado"
    assert registro.procesado_at is not None
    assert registro.sha256 == hashlib.sha256(contenido).hexdigest()
    assert len(repo_falso.inserts) == 1


def test_registrar_salida_con_contenido_repetido_devuelve_el_existente(repo_falso):
    contenido = b"OC;1\n"
    existente = repo_falso.sembrar(
        sentido="salida", tipo="oc", origen=None, estado="procesado",
        sha256=hashlib.sha256(contenido).hexdigest(), procesado_at="2026-11-04T12:05:00+00:00",
    )

    registro = service.registrar_salida(
        MagicMock(), drogueria_id="drog-1", tipo="oc", nombre_archivo="OC_otro.csv",
        contenido=contenido, usuario_id="usuario-1",
    )

    assert registro.id == existente["id"]
    assert repo_falso.inserts == []


def test_listar_pasa_filtros_y_paginacion(repo_falso):
    repo_falso.sembrar(sha256=SHA)

    registros = service.listar(
        MagicMock(), drogueria_id="drog-1", sentido="entrada", estado="error", limit=20, offset=40
    )

    assert len(registros) == 1
    assert repo_falso.listar_kwargs == {
        "drogueria_id": "drog-1",
        "sentido": "entrada",
        "estado": "error",
        "limit": 20,
        "offset": 40,
    }


@pytest.mark.parametrize(("limit", "offset"), [(0, 0), (-1, 0), (10, -1), (501, 0)])
def test_listar_rechaza_paginacion_invalida(repo_falso, limit, offset):
    with pytest.raises(ValidationError):
        service.listar(MagicMock(), drogueria_id="drog-1", limit=limit, offset=offset)
