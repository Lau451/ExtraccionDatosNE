"""Pipeline de recepción de archivos de Progress (odd/tasks/integracion-progress.md
S3, S4, S5): registrar → descartar duplicados → parsear → entregar → cerrar el registro.

Corre contra el service real del registro con su repository falso en memoria
(`tests/integracion_progress/registro/conftest.py::RepositorioFalso`) y con la
entrega a `services.pcp.api` reemplazada por un doble.
"""

import pytest

from services.integracion_progress.recepcion import service as recepcion
from services.integracion_progress.registro import repository as repo
from services.integracion_progress.tipos.presupuestos import destino
from services.integracion_progress.tipos.presupuestos import parser as parser_presupuestos
from services.shared.exceptions import NotFoundError, ValidationError
from tests.integracion_progress.registro.conftest import METODOS_REPOSITORIO, RepositorioFalso

ENCABEZADO = (
    "codigo_cliente;razon_social_cliente;numero_presupuesto;renglon;"
    "descripcion_producto;cantidad_producto"
)
CSV_VALIDO = "\n".join(
    [
        ENCABEZADO,
        "CLI-1;Farmacia Central;PRE-100;1;Amoxicilina 500mg;10",
        "CLI-1;Farmacia Central;PRE-100;2;Ibuprofeno 400mg;5",
        "CLI-2;Farmacia Sur;PRE-200;1;Paracetamol 500mg;20",
    ]
).encode("cp1252")
CSV_CON_ERRORES = "\n".join(
    [
        ENCABEZADO,
        "CLI-1;Farmacia Central;PRE-100;abc;Amoxicilina 500mg;10",
        "CLI-2;Farmacia Sur;PRE-200;1;Paracetamol 500mg;20",
        ";Farmacia Norte;PRE-300;1;;20",
    ]
).encode("cp1252")

_CLIENTE = object()


class EntregaFalsa:
    def __init__(self):
        self.llamadas: list[dict] = []
        self.error: Exception | None = None

    def __call__(self, client, *, drogueria_id, filas, usuario_id):
        self.llamadas.append(
            {"client": client, "drogueria_id": drogueria_id, "filas": filas, "usuario_id": usuario_id}
        )
        if self.error is not None:
            raise self.error
        numeros = list(dict.fromkeys(f.numero_presupuesto for f in filas))
        return [
            {
                "codigo_legacy": numero,
                "presupuesto_id": f"p-{numero}",
                "accion": "creado",
                "renglones_procesados": sum(1 for f in filas if f.numero_presupuesto == numero),
                "renglones_sin_producto": 0,
            }
            for numero in numeros
        ]


@pytest.fixture
def repo_falso(monkeypatch):
    falso = RepositorioFalso()
    for nombre in METODOS_REPOSITORIO:
        monkeypatch.setattr(repo, nombre, getattr(falso, nombre))
    return falso


@pytest.fixture
def entrega(monkeypatch):
    falsa = EntregaFalsa()
    monkeypatch.setattr(destino, "importar_presupuesto_legacy", falsa)
    return falsa


def _recibir(contenido: bytes, *, origen="manual", nombre="presupuestos.csv"):
    return recepcion.recibir_archivo(
        _CLIENTE,
        drogueria_id="drog-1",
        tipo="presupuestos",
        nombre_archivo=nombre,
        contenido=contenido,
        origen=origen,
        usuario_id="user-1",
    )


def test_archivo_valido_se_entrega_y_queda_procesado(repo_falso, entrega):
    resultado = _recibir(CSV_VALIDO)

    assert resultado.estado == "procesado"
    assert resultado.errores == []
    assert [r["codigo_legacy"] for r in resultado.resultados] == ["PRE-100", "PRE-200"]
    assert resultado.registro.estado == "procesado"
    assert resultado.registro.filas == 3
    assert resultado.registro.origen == "manual"
    assert resultado.registro.nombre_archivo == "presupuestos.csv"

    assert len(entrega.llamadas) == 1
    llamada = entrega.llamadas[0]
    assert llamada["client"] is _CLIENTE
    assert llamada["drogueria_id"] == "drog-1"
    assert llamada["usuario_id"] == "user-1"
    assert [(f.numero_presupuesto, f.renglon) for f in llamada["filas"]] == [
        ("PRE-100", 1),
        ("PRE-100", 2),
        ("PRE-200", 1),
    ]
    assert str(llamada["filas"][0].cantidad_producto) == "10"


def test_mismo_contenido_procesado_es_duplicado_y_no_importa_nada(repo_falso, entrega):
    primero = _recibir(CSV_VALIDO)
    updates_antes = len(repo_falso.updates)

    segundo = _recibir(CSV_VALIDO, origen="carpeta", nombre="otro_nombre.csv")

    assert segundo.estado == "duplicado"
    assert segundo.registro.id == primero.registro.id
    assert segundo.registro.nombre_archivo == "presupuestos.csv"
    assert segundo.errores == []
    assert segundo.resultados == []
    assert len(entrega.llamadas) == 1
    assert len(repo_falso.inserts) == 1
    assert len(repo_falso.updates) == updates_antes


def test_contenido_en_curso_recibido_tambien_es_duplicado(repo_falso, entrega):
    import hashlib
    from datetime import datetime, timezone

    # updated_at reciente: un 'recibido' de hace más de 15 minutos se reprocesa.
    repo_falso.sembrar(
        sha256=hashlib.sha256(CSV_VALIDO).hexdigest(),
        estado="recibido",
        updated_at=datetime.now(timezone.utc).isoformat(),
    )

    resultado = _recibir(CSV_VALIDO)

    assert resultado.estado == "duplicado"
    assert entrega.llamadas == []
    assert repo_falso.updates == []


def test_errores_de_parseo_rechazan_el_archivo_entero(repo_falso, entrega):
    resultado = _recibir(CSV_CON_ERRORES)

    esperados = [
        {"linea": 2, "mensaje": "renglón no es un número entero"},
        {"linea": 4, "mensaje": "falta codigo_cliente; falta descripcion_producto"},
    ]
    assert resultado.estado == "error"
    assert [e.model_dump() for e in resultado.errores] == esperados
    assert resultado.resultados == []
    # La fila válida (PRE-200) tampoco se entrega: todo o nada, igual que la UI.
    assert entrega.llamadas == []
    assert resultado.registro.estado == "error"
    assert resultado.registro.intentos == 1
    assert [e.model_dump() for e in resultado.registro.errores] == esperados
    assert resultado.registro.filas is None


def test_archivo_sin_filas_es_error_y_no_entrega(repo_falso, entrega):
    resultado = _recibir((ENCABEZADO + "\n").encode())

    assert resultado.estado == "error"
    assert [e.model_dump() for e in resultado.errores] == [
        {"linea": 1, "mensaje": "El archivo no tiene filas para importar"}
    ]
    assert entrega.llamadas == []


def test_error_de_dominio_en_la_entrega_marca_error_y_se_propaga(repo_falso, entrega):
    entrega.error = NotFoundError("No se encontró el cliente CLI-9")

    with pytest.raises(NotFoundError, match="No se encontró el cliente CLI-9"):
        _recibir(CSV_VALIDO)

    (fila,) = repo_falso.filas.values()
    assert fila["estado"] == "error"
    assert fila["intentos"] == 1
    assert fila["errores"] == [{"linea": 0, "mensaje": "No se encontró el cliente CLI-9"}]


def test_error_inesperado_en_la_entrega_no_deja_el_registro_trabado(repo_falso, entrega):
    entrega.error = RuntimeError("connection reset by peer: secreto interno")

    with pytest.raises(RuntimeError):
        _recibir(CSV_VALIDO)

    (fila,) = repo_falso.filas.values()
    assert fila["estado"] == "error"
    assert fila["errores"] == [
        {"linea": 0, "mensaje": "Error inesperado al entregar el archivo"}
    ]


def test_un_archivo_en_error_se_reprocesa(repo_falso, entrega):
    entrega.error = NotFoundError("No se encontró el cliente CLI-9")
    with pytest.raises(NotFoundError):
        _recibir(CSV_VALIDO)
    entrega.error = None

    resultado = _recibir(CSV_VALIDO, origen="carpeta")

    assert resultado.estado == "procesado"
    assert len(entrega.llamadas) == 2
    assert len(repo_falso.inserts) == 1
    assert resultado.registro.estado == "procesado"
    assert resultado.registro.errores is None
    assert resultado.registro.intentos == 1
    assert resultado.registro.filas == 3


def test_tipo_desconocido_es_value_error_sin_registrar(repo_falso, entrega):
    with pytest.raises(ValueError, match="productos"):
        recepcion.recibir_archivo(
            _CLIENTE,
            drogueria_id="drog-1",
            tipo="productos",
            nombre_archivo="x.csv",
            contenido=CSV_VALIDO,
            origen="manual",
            usuario_id="user-1",
        )

    assert repo_falso.inserts == []
    assert entrega.llamadas == []


# --- T7: observaciones de las revisiones de T3 y T4 (L11, L13) -------------------


def test_excepcion_inesperada_del_parser_deja_el_registro_en_error(
    repo_falso, entrega, monkeypatch, caplog
):
    # Sin esto el registro quedaba en 'recibido' una hora y la carpeta lo dejaba
    # 'pendiente' en cada escaneo (R1 carpeta.py exception path, R4-stuck-recibido).
    def parser_roto(contenido):
        raise RuntimeError("bug del parser: detalle interno")

    monkeypatch.setattr(parser_presupuestos, "parsear", parser_roto)

    resultado = _recibir(CSV_VALIDO, nombre="roto.csv")

    esperados = [{"linea": 0, "mensaje": "Error inesperado al leer el archivo"}]
    assert resultado.estado == "error"
    assert [e.model_dump() for e in resultado.errores] == esperados
    assert resultado.resultados == []
    assert resultado.registro.estado == "error"
    assert resultado.registro.intentos == 1
    (fila,) = repo_falso.filas.values()
    assert fila["estado"] == "error"
    assert fila["errores"] == esperados
    assert entrega.llamadas == []
    assert "roto.csv" in caplog.text
    assert "detalle interno" in caplog.text


def test_fila_que_no_cumple_el_modelo_de_pcp_es_error_de_validacion(repo_falso, monkeypatch):
    # R3-003: destino.py validaba con pydantic y un ValidationError de pydantic salía
    # como error inesperado (500 en la carga manual).
    importados: list = []
    monkeypatch.setattr(
        destino, "importar_presupuesto_legacy", lambda *a, **k: importados.append(k) or []
    )
    filas = parser_presupuestos.parsear(CSV_VALIDO).filas
    filas[1]["proceso_comercial"] = "9"
    monkeypatch.setattr(
        parser_presupuestos,
        "parsear",
        lambda contenido: parser_presupuestos.ResultadoParseo(filas=filas),
    )

    with pytest.raises(ValidationError) as error:
        _recibir(CSV_VALIDO)

    mensaje = "La fila 2 no tiene el formato que espera PCP (campo proceso_comercial)"
    assert error.value.message == mensaje
    assert importados == []
    (fila,) = repo_falso.filas.values()
    assert fila["estado"] == "error"
    assert fila["intentos"] == 1
    assert fila["errores"] == [{"linea": 0, "mensaje": mensaje}]
