"""Escaneo de la carpeta de entrada de Progress (odd/tasks/integracion-progress.md S4
automática, S3): qué archivos se toman, a dónde se mueven y que un archivo malo no
corta el escaneo. Con `tmp_path` y un `recibir` falso en lugar del pipeline real."""

import ctypes
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from services.integracion_progress.recepcion import carpeta as carpeta_module
from services.integracion_progress.recepcion.carpeta import escanear_carpeta
from services.integracion_progress.recepcion.service import ResultadoRecepcion
from services.integracion_progress.registro.models import RegistroArchivo

AHORA = datetime(2026, 11, 4, 15, 30, 45, tzinfo=timezone.utc)
SUFIJO = "_20261104153045"
_CLIENTE = object()


def _registro(nombre: str, estado: str = "procesado") -> RegistroArchivo:
    momento = AHORA.isoformat()
    return RegistroArchivo.model_validate(
        {
            "id": f"reg-{nombre}",
            "drogueria_id": "drog-1",
            "sentido": "entrada",
            "tipo": "presupuestos",
            "nombre_archivo": nombre,
            "sha256": "0" * 64,
            "origen": "carpeta",
            "estado": estado,
            "usuario_id": "usuario-sistema",
            "intentos": 0,
            "created_at": momento,
            "updated_at": momento,
        }
    )


class RecibirFalso:
    """Devuelve el estado configurado por nombre de archivo (default `procesado`);
    `excepciones[nombre]` se lanza en lugar de devolver."""

    def __init__(self, estados=None, excepciones=None, antes=None):
        self.estados = estados or {}
        self.excepciones = excepciones or {}
        self.antes = antes or {}
        self.llamadas: list[dict] = []

    def __call__(self, client, **kwargs):
        self.llamadas.append({"client": client, **kwargs})
        nombre = kwargs["nombre_archivo"]
        if nombre in self.antes:
            self.antes[nombre]()
        if nombre in self.excepciones:
            raise self.excepciones[nombre]
        estado = self.estados.get(nombre, "procesado")
        registro_estado = {"duplicado": "procesado"}.get(estado, estado)
        return ResultadoRecepcion(estado=estado, registro=_registro(nombre, registro_estado))


def _archivo(carpeta: Path, nombre: str, contenido: bytes = b"a;b\n", edad: float = 60) -> Path:
    ruta = carpeta / nombre
    ruta.write_bytes(contenido)
    momento = AHORA.timestamp() - edad
    os.utime(ruta, (momento, momento))
    return ruta


@pytest.fixture
def carpeta(tmp_path) -> Path:
    ruta = tmp_path / "presupuestos"
    ruta.mkdir()
    return ruta


class BuscarFalso:
    """Registro que el pipeline dejó para cada contenido (default: ninguno);
    `excepcion` se lanza en lugar de devolver."""

    def __init__(self, registros=None, excepcion=None):
        self.registros = registros or {}
        self.excepcion = excepcion
        self.llamadas: list[dict] = []

    def __call__(self, client, **kwargs):
        self.llamadas.append({"client": client, **kwargs})
        if self.excepcion is not None:
            raise self.excepcion
        return self.registros.get(kwargs["contenido"])


def _escanear(carpeta: Path, recibir, buscar=None) -> list:
    return escanear_carpeta(
        _CLIENTE,
        carpeta_tipo=carpeta,
        tipo="presupuestos",
        drogueria_id="drog-1",
        usuario_id="usuario-sistema",
        ahora=AHORA,
        recibir=recibir,
        buscar=buscar or BuscarFalso(),
    )


def _nombres(ruta: Path) -> list[str]:
    return sorted(p.name for p in ruta.iterdir()) if ruta.exists() else []


def test_archivo_viejo_se_procesa_y_se_mueve_a_procesados(carpeta):
    _archivo(carpeta, "PRESUPUESTOS_1.csv", b"contenido-1")
    recibir = RecibirFalso()

    resultados = _escanear(carpeta, recibir)

    assert recibir.llamadas == [
        {
            "client": _CLIENTE,
            "drogueria_id": "drog-1",
            "tipo": "presupuestos",
            "nombre_archivo": "PRESUPUESTOS_1.csv",
            "contenido": b"contenido-1",
            "origen": "carpeta",
            "usuario_id": "usuario-sistema",
        }
    ]
    assert [(r.nombre_archivo, r.estado, r.registro_id) for r in resultados] == [
        ("PRESUPUESTOS_1.csv", "procesado", "reg-PRESUPUESTOS_1.csv")
    ]
    assert resultados[0].movido_a == carpeta / "procesados" / "PRESUPUESTOS_1.csv"
    assert _nombres(carpeta) == ["procesados"]
    assert (carpeta / "procesados" / "PRESUPUESTOS_1.csv").read_bytes() == b"contenido-1"


def test_se_saltean_ocultos_tmp_jovenes_y_subcarpetas(carpeta):
    _archivo(carpeta, ".oculto.csv")
    _archivo(carpeta, "a_medio_escribir.csv.tmp")
    _archivo(carpeta, "MAYUSCULAS.TMP")
    _archivo(carpeta, "recien_llegado.csv", edad=29)
    (carpeta / "otra_carpeta").mkdir()
    _archivo(carpeta, "listo.csv", edad=30)
    recibir = RecibirFalso()

    resultados = _escanear(carpeta, recibir)

    assert [r.nombre_archivo for r in resultados] == ["listo.csv"]
    assert [c["nombre_archivo"] for c in recibir.llamadas] == ["listo.csv"]
    assert _nombres(carpeta) == [
        ".oculto.csv",
        "MAYUSCULAS.TMP",
        "a_medio_escribir.csv.tmp",
        "otra_carpeta",
        "procesados",
        "recien_llegado.csv",
    ]


@pytest.mark.parametrize(
    ("estado", "subcarpeta"),
    [("procesado", "procesados"), ("duplicado", "procesados"), ("error", "errores")],
)
def test_el_estado_decide_la_subcarpeta(carpeta, estado, subcarpeta):
    _archivo(carpeta, "archivo.csv")

    resultados = _escanear(carpeta, RecibirFalso(estados={"archivo.csv": estado}))

    assert resultados[0].estado == estado
    assert resultados[0].movido_a == carpeta / subcarpeta / "archivo.csv"
    assert _nombres(carpeta / subcarpeta) == ["archivo.csv"]
    assert not (carpeta / "archivo.csv").exists()


def test_excepcion_con_el_registro_en_error_va_a_errores_y_sigue_con_el_resto(carpeta, caplog):
    # La entrega falló: el pipeline dejó el registro en error y propagó la excepción.
    _archivo(carpeta, "a.csv", b"contenido-a")
    _archivo(carpeta, "b.csv", b"contenido-b")
    _archivo(carpeta, "c.csv", b"contenido-c")
    recibir = RecibirFalso(excepciones={"b.csv": RuntimeError("falló la entrega")})
    buscar = BuscarFalso(registros={b"contenido-b": _registro("b.csv", "error")})

    resultados = _escanear(carpeta, recibir, buscar)

    assert [(r.nombre_archivo, r.estado, r.registro_id) for r in resultados] == [
        ("a.csv", "procesado", "reg-a.csv"),
        ("b.csv", "error", "reg-b.csv"),
        ("c.csv", "procesado", "reg-c.csv"),
    ]
    assert buscar.llamadas == [
        {
            "client": _CLIENTE,
            "drogueria_id": "drog-1",
            "tipo": "presupuestos",
            "contenido": b"contenido-b",
        }
    ]
    assert _nombres(carpeta / "procesados") == ["a.csv", "c.csv"]
    assert _nombres(carpeta / "errores") == ["b.csv"]
    assert "b.csv" in caplog.text
    assert "falló la entrega" in caplog.text


@pytest.mark.parametrize(
    "buscar",
    [
        BuscarFalso(),
        BuscarFalso(registros={b"contenido-b": _registro("b.csv", "recibido")}),
        BuscarFalso(excepcion=RuntimeError("supabase caído")),
    ],
    ids=["sin-registro", "registro-recibido", "busqueda-falla"],
)
def test_excepcion_sin_registro_en_error_deja_el_archivo_para_el_proximo_escaneo(
    carpeta, caplog, buscar
):
    # Supabase caído antes de registrar (o de cerrar el registro): moverlo a errores/
    # lo sacaría del circuito sin que el registro muestre nada.
    _archivo(carpeta, "a.csv", b"contenido-a")
    _archivo(carpeta, "b.csv", b"contenido-b")
    recibir = RecibirFalso(excepciones={"b.csv": RuntimeError("supabase caído")})

    resultados = _escanear(carpeta, recibir, buscar)

    assert [(r.nombre_archivo, r.estado, r.movido_a) for r in resultados] == [
        ("a.csv", "procesado", carpeta / "procesados" / "a.csv"),
        ("b.csv", "pendiente", None),
    ]
    assert _nombres(carpeta) == ["b.csv", "procesados"]
    assert (carpeta / "b.csv").read_bytes() == b"contenido-b"
    assert "b.csv" in caplog.text
    assert "supabase caído" in caplog.text


def test_archivo_bloqueado_al_leerlo_queda_y_sigue_con_el_resto(carpeta, monkeypatch, caplog):
    _archivo(carpeta, "a.csv", b"contenido-a")
    _archivo(carpeta, "b.csv", b"contenido-b")
    leer_real = Path.read_bytes

    def leer_bloqueado(self):
        if self.name == "a.csv":
            raise PermissionError("el archivo está en uso por otro proceso")
        return leer_real(self)

    monkeypatch.setattr(Path, "read_bytes", leer_bloqueado)
    recibir = RecibirFalso()

    resultados = _escanear(carpeta, recibir)

    assert [(r.nombre_archivo, r.estado) for r in resultados] == [("b.csv", "procesado")]
    assert [c["nombre_archivo"] for c in recibir.llamadas] == ["b.csv"]
    assert _nombres(carpeta) == ["a.csv", "procesados"]
    assert "a.csv" in caplog.text


def test_archivo_que_no_se_puede_inspeccionar_se_saltea(carpeta, monkeypatch):
    _archivo(carpeta, "a.csv")
    _archivo(carpeta, "b.csv")
    marcador_real = carpeta_module._marcador

    def marcador_que_falla_con_a(archivo):
        if archivo.name == "a.csv":
            raise PermissionError("acceso denegado")
        return marcador_real(archivo)

    monkeypatch.setattr(carpeta_module, "_marcador", marcador_que_falla_con_a)

    resultados = _escanear(carpeta, RecibirFalso())

    assert [r.nombre_archivo for r in resultados] == ["b.csv"]
    assert (carpeta / "a.csv").exists()


@pytest.mark.skipif(sys.platform != "win32", reason="atributo oculto de Windows")
def test_archivo_con_atributo_oculto_de_windows_se_saltea(carpeta):
    oculto = _archivo(carpeta, "oculto.csv")
    _archivo(carpeta, "visible.csv")
    file_attribute_hidden = 0x2
    assert ctypes.windll.kernel32.SetFileAttributesW(str(oculto), file_attribute_hidden)

    resultados = _escanear(carpeta, RecibirFalso())

    assert [r.nombre_archivo for r in resultados] == ["visible.csv"]
    assert oculto.exists()


def test_si_falla_el_movimiento_de_un_archivo_sigue_con_el_resto(carpeta, monkeypatch):
    _archivo(carpeta, "a.csv")
    _archivo(carpeta, "b.csv")
    mover_real = carpeta_module._mover

    def mover_que_falla_con_a(origen, destino_dir, ahora):
        if origen.name == "a.csv":
            raise PermissionError("bloqueado por otro proceso")
        return mover_real(origen, destino_dir, ahora)

    monkeypatch.setattr(carpeta_module, "_mover", mover_que_falla_con_a)

    resultados = _escanear(carpeta, RecibirFalso())

    assert [(r.nombre_archivo, r.movido_a) for r in resultados] == [
        ("a.csv", None),
        ("b.csv", carpeta / "procesados" / "b.csv"),
    ]
    assert (carpeta / "a.csv").exists()


def test_colision_de_nombre_agrega_sufijo_y_no_pisa_nada(carpeta):
    procesados = carpeta / "procesados"
    procesados.mkdir()
    (procesados / "archivo.csv").write_bytes(b"viejo")
    (procesados / f"archivo{SUFIJO}.csv").write_bytes(b"viejo-2")
    _archivo(carpeta, "archivo.csv", b"nuevo")

    resultados = _escanear(carpeta, RecibirFalso())

    assert resultados[0].movido_a == procesados / f"archivo{SUFIJO}_2.csv"
    assert (procesados / "archivo.csv").read_bytes() == b"viejo"
    assert (procesados / f"archivo{SUFIJO}.csv").read_bytes() == b"viejo-2"
    assert (procesados / f"archivo{SUFIJO}_2.csv").read_bytes() == b"nuevo"


def test_archivo_que_desaparece_antes_de_moverse_se_ignora(carpeta):
    # Otro proceso (otro worker de uvicorn) lo tomó y lo movió mientras este lo recibía:
    # su registro ya existía, así que para este es un duplicado.
    ruta = _archivo(carpeta, "archivo.csv")
    _archivo(carpeta, "otro.csv")
    otro_proceso = carpeta / "procesados_del_otro"
    otro_proceso.mkdir()
    recibir = RecibirFalso(
        estados={"archivo.csv": "duplicado"},
        antes={"archivo.csv": lambda: ruta.rename(otro_proceso / ruta.name)},
    )

    resultados = _escanear(carpeta, recibir)

    assert [(r.nombre_archivo, r.estado, r.movido_a) for r in resultados] == [
        ("archivo.csv", "duplicado", None),
        ("otro.csv", "procesado", carpeta / "procesados" / "otro.csv"),
    ]
    assert _nombres(otro_proceso) == ["archivo.csv"]
    assert _nombres(carpeta / "procesados") == ["otro.csv"]


def test_archivo_que_desaparece_antes_de_leerse_se_ignora(carpeta, monkeypatch):
    ruta = _archivo(carpeta, "archivo.csv")
    leer_real = Path.read_bytes

    def leer_despues_de_que_otro_lo_movio(self):
        if self == ruta:
            ruta.unlink()
        return leer_real(self)

    monkeypatch.setattr(Path, "read_bytes", leer_despues_de_que_otro_lo_movio)
    recibir = RecibirFalso()

    resultados = _escanear(carpeta, recibir)

    assert resultados == []
    assert recibir.llamadas == []


def test_dos_escaneos_del_mismo_archivo_no_fallan(carpeta):
    _archivo(carpeta, "archivo.csv")
    primero = _escanear(carpeta, RecibirFalso())

    segundo = _escanear(carpeta, RecibirFalso())

    assert [r.estado for r in primero] == ["procesado"]
    assert segundo == []
    assert _nombres(carpeta / "procesados") == ["archivo.csv"]


def test_marcador_ok_acepta_un_archivo_joven_y_se_mueve_con_el(carpeta):
    _archivo(carpeta, "joven.csv", b"x", edad=1)
    _archivo(carpeta, "joven.csv.ok", b"", edad=1)
    recibir = RecibirFalso()

    resultados = _escanear(carpeta, recibir)

    assert [c["nombre_archivo"] for c in recibir.llamadas] == ["joven.csv"]
    assert resultados[0].movido_a == carpeta / "procesados" / "joven.csv"
    assert _nombres(carpeta / "procesados") == ["joven.csv", "joven.csv.ok"]
    assert _nombres(carpeta) == ["procesados"]


def test_marcador_ok_sigue_al_archivo_renombrado_por_colision(carpeta):
    errores = carpeta / "errores"
    errores.mkdir()
    (errores / "archivo.csv").write_bytes(b"viejo")
    (errores / "archivo.csv.ok").write_bytes(b"viejo-ok")
    _archivo(carpeta, "archivo.csv", b"nuevo")
    _archivo(carpeta, "archivo.csv.ok", b"3")

    _escanear(carpeta, RecibirFalso(estados={"archivo.csv": "error"}))

    assert _nombres(errores) == [
        "archivo.csv",
        "archivo.csv.ok",
        f"archivo{SUFIJO}.csv",
        f"archivo{SUFIJO}.csv.ok",
    ]
    assert (errores / "archivo.csv.ok").read_bytes() == b"viejo-ok"
    assert (errores / f"archivo{SUFIJO}.csv.ok").read_bytes() == b"3"


def test_marcador_ok_huerfano_no_se_procesa_ni_se_mueve(carpeta):
    _archivo(carpeta, "sin_archivo.csv.ok", b"")
    recibir = RecibirFalso()

    resultados = _escanear(carpeta, recibir)

    assert resultados == []
    assert recibir.llamadas == []
    assert _nombres(carpeta) == ["sin_archivo.csv.ok"]


def test_ok_no_es_obligatorio(carpeta):
    _archivo(carpeta, "sin_marcador.csv")

    resultados = _escanear(carpeta, RecibirFalso())

    assert [r.estado for r in resultados] == ["procesado"]


def test_carpeta_inexistente_no_falla_ni_la_crea(tmp_path):
    carpeta_tipo = tmp_path / "presupuestos"

    resultados = _escanear(carpeta_tipo, RecibirFalso())

    assert resultados == []
    assert not carpeta_tipo.exists()


def test_duplicado_en_curso_queda_en_la_carpeta_para_el_proximo_escaneo(carpeta):
    # Otro proceso está procesando este mismo contenido (registro en `recibido`): si
    # este escaneo lo moviera a procesados/ y el otro proceso fallara, el archivo
    # quedaría en procesados/ con el registro en error.
    _archivo(carpeta, "PRESUPUESTOS_1.csv", b"contenido-1")

    def recibir(client, **kwargs):
        return ResultadoRecepcion(
            estado="duplicado", registro=_registro(kwargs["nombre_archivo"], "recibido")
        )

    resultados = _escanear(carpeta, recibir)

    assert [(r.nombre_archivo, r.estado, r.movido_a) for r in resultados] == [
        ("PRESUPUESTOS_1.csv", "duplicado", None)
    ]
    assert _nombres(carpeta) == ["PRESUPUESTOS_1.csv"]
