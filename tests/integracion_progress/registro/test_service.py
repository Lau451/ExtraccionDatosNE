"""tests/integracion_progress/registro/test_service.py -- registro de archivos de
Progress (odd/tasks/integracion-progress.md S3): duplicados, reproceso de errores,
carrera de inserción y conteo de intentos. Unitarios con el repository falso de
conftest.py."""

import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from postgrest.exceptions import APIError

from services.integracion_progress.registro import service
from services.integracion_progress.registro.models import ErrorLinea
from services.shared.exceptions import ConflictError, NotFoundError, ValidationError

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


def _hace(minutos: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutos)).isoformat()


@pytest.mark.parametrize("estado", ["procesado", "recibido"])
def test_mismo_contenido_es_duplicado_y_no_escribe_nada(repo_falso, estado):
    procesado_at = "2026-11-04T12:05:00+00:00" if estado == "procesado" else None
    # updated_at reciente: un 'recibido' viejo se reprocesa (ver tests de abajo).
    existente = repo_falso.sembrar(
        sha256=SHA, estado=estado, procesado_at=procesado_at, updated_at=_hace(1)
    )

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

    # Lo reclama volviéndolo a 'recibido' (CAS): un segundo proceso que llegue con el
    # mismo contenido lo ve como en curso. Errores e intentos quedan hasta el cierre.
    assert es_duplicado is False
    assert registro.id == existente["id"]
    assert registro.estado == "recibido"
    assert registro.intentos == 1
    assert registro.errores == [ErrorLinea(linea=2, mensaje="x")]
    assert repo_falso.inserts == []
    assert repo_falso.updates == [(existente["id"], {"estado": "recibido"})]


def test_recibido_reciente_es_duplicado_porque_se_esta_procesando(repo_falso):
    existente = repo_falso.sembrar(sha256=SHA, estado="recibido", updated_at=_hace(59))

    registro, es_duplicado = _registrar()

    assert es_duplicado is True
    assert registro.id == existente["id"]
    assert repo_falso.inserts == []
    assert repo_falso.updates == []


def test_recibido_viejo_se_devuelve_para_reprocesar(repo_falso):
    # Un 'recibido' que no avanzó en más de una hora quedó colgado por un crash.
    existente = repo_falso.sembrar(sha256=SHA, estado="recibido", updated_at=_hace(61))

    registro, es_duplicado = _registrar()

    assert es_duplicado is False
    assert registro.id == existente["id"]
    assert registro.estado == "recibido"
    assert registro.updated_at > datetime.now(timezone.utc) - timedelta(minutes=1)
    assert repo_falso.inserts == []
    assert repo_falso.updates == [(existente["id"], {"estado": "recibido"})]


@pytest.mark.parametrize("estado", ["error", "recibido"])
def test_si_otro_proceso_ya_reclamo_el_reproceso_es_duplicado(repo_falso, estado):
    existente = repo_falso.sembrar(sha256=SHA, estado=estado, updated_at=_hace(61))

    def otro_proceso_lo_reclamo():
        repo_falso.filas[existente["id"]]["updated_at"] = _hace(0)
        repo_falso.filas[existente["id"]]["estado"] = "recibido"

    repo_falso.antes_de_actualizar = otro_proceso_lo_reclamo

    registro, es_duplicado = _registrar()

    assert es_duplicado is True
    assert registro.id == existente["id"]
    assert registro.estado == "recibido"
    assert repo_falso.updates == []


def test_carrera_que_relee_un_recibido_viejo_lo_devuelve_para_reprocesar(repo_falso):
    def otro_proceso_dejo_un_recibido_colgado():
        repo_falso.sembrar(sha256=SHA, estado="recibido", updated_at=_hace(90))

    repo_falso.antes_de_insertar = otro_proceso_dejo_un_recibido_colgado

    _, es_duplicado = _registrar()

    assert es_duplicado is False


def test_carrera_de_insercion_relee_la_ganadora_como_duplicado(repo_falso):
    ganadora = {}

    def otro_proceso_inserta_primero():
        ganadora.update(repo_falso.sembrar(sha256=SHA, origen="manual", updated_at=_hace(0)))

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


def _marcar_error(registro_id, errores, drogueria_id="drog-1"):
    return service.marcar_error(
        MagicMock(), drogueria_id=drogueria_id, registro_id=registro_id, errores=errores
    )


def _marcar_procesado(registro_id, filas, drogueria_id="drog-1"):
    return service.marcar_procesado(
        MagicMock(), drogueria_id=drogueria_id, registro_id=registro_id, filas=filas
    )


def test_marcar_error_incrementa_intentos_y_guarda_errores(repo_falso):
    existente = repo_falso.sembrar(sha256=SHA)
    errores = [ErrorLinea(linea=3, mensaje="Falta el cliente"), {"linea": 7, "mensaje": "Fecha inválida"}]

    primero = _marcar_error(existente["id"], errores)
    # Un reproceso lo vuelve a 'recibido' antes del segundo fallo.
    repo_falso.filas[existente["id"]]["estado"] = "recibido"
    segundo = _marcar_error(existente["id"], [{"linea": 1, "mensaje": "otra"}])

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
    existente = repo_falso.sembrar(sha256=SHA, estado="recibido", intentos=1)

    def otro_proceso_marca_error():
        repo_falso.filas[existente["id"]]["intentos"] = 2

    repo_falso.antes_de_actualizar = otro_proceso_marca_error

    registro = _marcar_error(existente["id"], [])

    assert registro.intentos == 3


def test_marcar_error_de_registro_inexistente(repo_falso):
    with pytest.raises(NotFoundError):
        _marcar_error("no-existe", [])


def test_marcar_procesado_guarda_filas_y_fecha(repo_falso):
    # Reproceso de un archivo que falló: reclamado, vuelve a 'recibido' con los errores viejos.
    existente = repo_falso.sembrar(
        sha256=SHA, estado="recibido", intentos=1, errores=[{"linea": 1, "mensaje": "x"}]
    )

    registro = _marcar_procesado(existente["id"], 12)

    assert registro.estado == "procesado"
    assert registro.filas == 12
    assert registro.procesado_at is not None
    assert registro.errores is None
    assert registro.intentos == 1


def test_marcar_procesado_de_registro_inexistente(repo_falso):
    with pytest.raises(NotFoundError):
        _marcar_procesado("no-existe", 0)


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


# --- T7: observaciones de la revisión de T2 (L13) ------------------------------


@pytest.mark.parametrize("marcar", ["procesado", "error"])
def test_cerrar_un_registro_de_otra_drogueria_no_lo_toca(repo_falso, marcar):
    # R1-tenant-unscoped-mutations: las escrituras por id filtran también por droguería.
    existente = repo_falso.sembrar(sha256=SHA, drogueria_id="drog-2")

    with pytest.raises(NotFoundError) as error:
        if marcar == "procesado":
            _marcar_procesado(existente["id"], 3, drogueria_id="drog-1")
        else:
            _marcar_error(existente["id"], [], drogueria_id="drog-1")

    assert error.value.message == f"No se encontró el registro de archivo '{existente['id']}'"
    assert repo_falso.updates == []
    assert repo_falso.filas[existente["id"]]["estado"] == "recibido"
    assert repo_falso.filas[existente["id"]]["intentos"] == 0


def test_reclamar_solo_ve_registros_de_la_propia_drogueria(repo_falso):
    existente = repo_falso.sembrar(sha256=SHA, estado="error", drogueria_id="drog-2")

    registro, es_duplicado = _registrar(drogueria_id="drog-1")

    assert es_duplicado is False
    assert registro.id != existente["id"]
    assert registro.drogueria_id == "drog-1"
    assert repo_falso.filas[existente["id"]]["estado"] == "error"
    assert repo_falso.updates == []


@pytest.mark.parametrize("estado", ["procesado", "error"])
def test_marcar_procesado_solo_cierra_un_registro_en_curso(repo_falso, estado):
    # R3-state-transition-unguarded: solo 'recibido' -> 'procesado'.
    procesado_at = "2026-11-04T12:05:00+00:00" if estado == "procesado" else None
    existente = repo_falso.sembrar(sha256=SHA, estado=estado, procesado_at=procesado_at, filas=4)

    with pytest.raises(ConflictError) as error:
        _marcar_procesado(existente["id"], 9)

    assert error.value.message == (
        f"El registro de archivo '{existente['id']}' no está en curso (estado {estado})"
    )
    assert repo_falso.updates == []
    assert repo_falso.filas[existente["id"]]["estado"] == estado
    assert repo_falso.filas[existente["id"]]["filas"] == 4


@pytest.mark.parametrize("estado", ["procesado", "error"])
def test_marcar_error_solo_cierra_un_registro_en_curso(repo_falso, estado):
    # R4-no-state-guard-transitions: solo 'recibido' -> 'error'; un 'procesado' no se
    # pisa y un 'error' no suma un intento que no ocurrió.
    procesado_at = "2026-11-04T12:05:00+00:00" if estado == "procesado" else None
    existente = repo_falso.sembrar(
        sha256=SHA, estado=estado, procesado_at=procesado_at, intentos=1
    )

    with pytest.raises(ConflictError) as error:
        _marcar_error(existente["id"], [{"linea": 1, "mensaje": "x"}])

    assert error.value.message == (
        f"El registro de archivo '{existente['id']}' no está en curso (estado {estado})"
    )
    assert repo_falso.updates == []
    assert repo_falso.filas[existente["id"]]["estado"] == estado
    assert repo_falso.filas[existente["id"]]["intentos"] == 1
    assert repo_falso.filas[existente["id"]]["procesado_at"] == procesado_at


def test_unique_sin_fila_visible_es_conflicto_y_no_inserta(repo_falso, monkeypatch):
    # R3-conflict-paths-untested: 23505 y la ganadora ya no existe al releer.
    def choca(client, fila):
        raise APIError({"code": "23505", "message": "duplicate key uq_parch_contenido"})

    monkeypatch.setattr(service.repo, "insertar", choca)

    with pytest.raises(ConflictError) as error:
        _registrar()

    assert error.value.message == (
        "El archivo 'PRESUPUESTOS_20261104120000.csv' chocó con un registro que ya no existe"
    )
    assert repo_falso.filas == {}
    assert repo_falso.updates == []


def test_reclamo_perdido_contra_un_registro_borrado_es_conflicto(repo_falso):
    # R3-conflict-paths-untested: el reclamo falla porque la fila desapareció.
    existente = repo_falso.sembrar(sha256=SHA, estado="error")

    def otro_proceso_lo_borra():
        del repo_falso.filas[existente["id"]]

    repo_falso.antes_de_actualizar = otro_proceso_lo_borra

    with pytest.raises(ConflictError) as error:
        _registrar(nombre_archivo="REPROCESO.csv")

    assert error.value.message == "El archivo 'REPROCESO.csv' chocó con un registro que ya no existe"
    assert repo_falso.inserts == []
    assert repo_falso.updates == []


def test_registrar_salida_con_filas_negativas_no_escribe(repo_falso):
    # R3-salida-filas-unvalidated: mismo criterio que marcar_procesado.
    with pytest.raises(ValidationError) as error:
        service.registrar_salida(
            MagicMock(), drogueria_id="drog-1", tipo="oc", nombre_archivo="OC_1.csv",
            contenido=b"OC;1\n", usuario_id="usuario-1", filas=-1,
        )

    assert error.value.message == "'filas' no puede ser negativo"
    assert repo_falso.inserts == []
    assert repo_falso.filas == {}


def test_registrar_salida_guarda_las_filas(repo_falso):
    registro = service.registrar_salida(
        MagicMock(), drogueria_id="drog-1", tipo="oc", nombre_archivo="OC_1.csv",
        contenido=b"OC;1\n", usuario_id="usuario-1", filas=0,
    )

    assert registro.filas == 0
    assert repo_falso.inserts[0]["filas"] == 0
