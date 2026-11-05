"""Recepción automática desde la carpeta de entrada (odd/tasks/integracion-progress.md
S4 automática; L6): se enciende solo con carpeta y tenant configurados, escanea
`<entrada>/presupuestos` con el usuario de sistema y origen 'carpeta', y el loop
periódico tolera errores y se cancela limpio. Incluye el arranque de la app de
presupuestación con la recepción apagada."""

import asyncio
import functools
import logging
import os
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services.integracion_progress.recepcion import automatica
from services.integracion_progress.recepcion.service import ResultadoRecepcion
from services.integracion_progress.registro.models import RegistroArchivo
from services.shared.config import Settings

_BASE = {
    "supabase_url": "http://localhost",
    "supabase_anon_key": "anon",
    "supabase_service_key": "service",
    "usuario_sistema_id": "usuario-sistema",
}
_CLIENTE = object()


def _settings(**campos) -> Settings:
    # _env_file=None: el .env del repo no debe decidir si la recepción está encendida.
    return Settings(_env_file=None, **{**_BASE, **campos})


class EscanearFalso:
    def __init__(self):
        self.llamadas: list[dict] = []

    def __call__(self, client, **kwargs):
        self.llamadas.append({"client": client, **kwargs})
        return []


def _escanear_si_configurado(settings, escanear, **kwargs):
    return automatica.escanear_si_configurado(
        settings, client_factory=lambda: _CLIENTE, escanear=escanear, **kwargs
    )


@pytest.mark.parametrize(
    "campos",
    [
        {},
        {"progress_entrada_dir": "C:/entrada"},
        {"progress_drogueria_id": "drog-1"},
        {"progress_entrada_dir": "", "progress_drogueria_id": "drog-1"},
        {"progress_entrada_dir": "C:/entrada", "progress_drogueria_id": "  "},
    ],
)
def test_sin_carpeta_o_tenant_no_escanea_ni_toca_nada(tmp_path, campos):
    if campos.get("progress_entrada_dir") == "C:/entrada":
        campos = {**campos, "progress_entrada_dir": str(tmp_path)}
    escanear = EscanearFalso()

    resultados = _escanear_si_configurado(_settings(**campos), escanear)

    assert resultados == []
    assert escanear.llamadas == []
    assert list(tmp_path.iterdir()) == []


def test_strings_vacios_del_entorno_cuentan_como_no_configurado(monkeypatch):
    for nombre, valor in {k.upper(): v for k, v in _BASE.items()}.items():
        monkeypatch.setenv(nombre, valor)
    monkeypatch.setenv("PROGRESS_ENTRADA_DIR", "")
    monkeypatch.setenv("PROGRESS_DROGUERIA_ID", "")
    # docker-compose pasa `${VAR:-}` vacío si no está definida: no debe romper el arranque.
    monkeypatch.setenv("PROGRESS_ESCANEO_INTERVALO_SEGUNDOS", "")

    settings = Settings(_env_file=None)

    assert settings.progress_entrada_dir is None
    assert settings.progress_drogueria_id is None
    assert settings.progress_escaneo_intervalo_segundos == 300
    assert automatica.motivo_apagada(settings) is not None


def test_configurada_escanea_la_carpeta_del_tipo_con_tenant_y_usuario_de_sistema(tmp_path):
    escanear = EscanearFalso()
    settings = _settings(progress_entrada_dir=str(tmp_path), progress_drogueria_id="drog-1")

    _escanear_si_configurado(settings, escanear)

    assert escanear.llamadas == [
        {
            "client": _CLIENTE,
            "carpeta_tipo": Path(tmp_path) / "presupuestos",
            "tipo": "presupuestos",
            "drogueria_id": "drog-1",
            "usuario_id": "usuario-sistema",
            "detener": None,
        }
    ]
    assert automatica.motivo_apagada(settings) is None


def test_configurada_le_pasa_al_escaneo_el_pedido_de_detener(tmp_path):
    escanear = EscanearFalso()
    detener = threading.Event()
    settings = _settings(progress_entrada_dir=str(tmp_path), progress_drogueria_id="drog-1")

    _escanear_si_configurado(settings, escanear, detener=detener)

    assert [llamada["detener"] for llamada in escanear.llamadas] == [detener]


def _registro_en_error() -> RegistroArchivo:
    return RegistroArchivo.model_validate(
        {
            "id": "reg-1",
            "drogueria_id": "drog-1",
            "sentido": "entrada",
            "tipo": "presupuestos",
            "nombre_archivo": "PRESUPUESTOS_1.csv",
            "sha256": "0" * 64,
            "origen": "carpeta",
            "estado": "error",
            "usuario_id": "usuario-sistema",
            "intentos": 1,
            "created_at": "2026-11-04T12:00:00+00:00",
            "updated_at": "2026-11-04T12:00:00+00:00",
        }
    )


def test_configurada_de_punta_a_punta_mueve_el_archivo(tmp_path):
    carpeta_tipo = tmp_path / "presupuestos"
    carpeta_tipo.mkdir()
    archivo = carpeta_tipo / "PRESUPUESTOS_1.csv"
    archivo.write_bytes(b"x")
    os.utime(archivo, (0, 0))
    recibidos: list[dict] = []

    def recibir_falso(client, **kwargs):
        recibidos.append(kwargs)
        return ResultadoRecepcion(estado="error", registro=_registro_en_error())

    settings = _settings(progress_entrada_dir=str(tmp_path), progress_drogueria_id="drog-1")

    resultados = automatica.escanear_si_configurado(
        settings,
        client_factory=lambda: _CLIENTE,
        escanear=functools.partial(automatica.carpeta.escanear_carpeta, recibir=recibir_falso),
    )

    assert [(r.nombre_archivo, r.estado) for r in resultados] == [("PRESUPUESTOS_1.csv", "error")]
    assert recibidos[0]["origen"] == "carpeta"
    assert recibidos[0]["usuario_id"] == "usuario-sistema"
    assert (carpeta_tipo / "errores" / "PRESUPUESTOS_1.csv").exists()


def test_loop_apagado_loguea_un_info_con_el_motivo_y_termina(caplog):
    escaneos: list = []

    with caplog.at_level(logging.INFO, logger=automatica.logger.name):
        asyncio.run(
            automatica.recepcion_periodica(
                _settings(), escanear=lambda s, **_: escaneos.append(s)
            )
        )

    registros = [r for r in caplog.records if r.name == automatica.logger.name]
    assert len(registros) == 1
    assert registros[0].levelno == logging.INFO
    assert "PROGRESS_ENTRADA_DIR" in registros[0].getMessage()
    assert escaneos == []


def test_loop_escanea_al_arrancar_y_cada_intervalo_tolerando_errores(caplog):
    settings = _settings(
        progress_entrada_dir="C:/entrada",
        progress_drogueria_id="drog-1",
        progress_escaneo_intervalo_segundos=7,
    )
    eventos: list = []

    def escanear(s, **_):
        eventos.append("escaneo")
        if len(eventos) == 1:
            raise RuntimeError("supabase caído")

    async def dormir(segundos):
        eventos.append(("dormir", segundos))
        if eventos.count("escaneo") == 3:
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(automatica.recepcion_periodica(settings, escanear=escanear, dormir=dormir))

    assert eventos == [
        "escaneo", ("dormir", 7), "escaneo", ("dormir", 7), "escaneo", ("dormir", 7),
    ]
    assert "supabase caído" in caplog.text


def test_loop_se_cancela_limpio_mientras_duerme():
    settings = _settings(progress_entrada_dir="C:/entrada", progress_drogueria_id="drog-1")
    escaneos: list = []

    async def correr_y_cancelar():
        tarea = asyncio.create_task(
            automatica.recepcion_periodica(
                settings, escanear=lambda s, **_: escaneos.append(s)
            )
        )
        while not escaneos:
            await asyncio.sleep(0.01)
        tarea.cancel()
        with pytest.raises(asyncio.CancelledError):
            await tarea

    asyncio.run(correr_y_cancelar())

    assert escaneos == [settings]


def test_cancelar_durante_un_escaneo_le_pide_al_thread_que_pare():
    # R4: asyncio no puede cancelar el thread del escaneo; sin el pedido de detener,
    # el apagado esperaba a que terminara la carpeta entera.
    settings = _settings(progress_entrada_dir="C:/entrada", progress_drogueria_id="drog-1")
    arranco = threading.Event()
    vio_detener: list[bool] = []

    def escanear(s, *, detener):
        arranco.set()
        vio_detener.append(detener.wait(timeout=5))

    async def correr_y_cancelar():
        tarea = asyncio.create_task(automatica.recepcion_periodica(settings, escanear=escanear))
        for _ in range(500):
            if arranco.is_set():
                break
            await asyncio.sleep(0.01)
        tarea.cancel()
        with pytest.raises(asyncio.CancelledError):
            await tarea

    asyncio.run(correr_y_cancelar())

    assert vio_detener == [True]


def test_la_app_arranca_y_apaga_con_la_recepcion_apagada(monkeypatch):
    from services.presupuestacion import main
    from services.shared.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "progress_entrada_dir", None)
    monkeypatch.setattr(settings, "progress_drogueria_id", None)

    with TestClient(main.app) as cliente:
        respuesta = cliente.get("/ruta-que-no-existe")

    assert respuesta.status_code == 404
