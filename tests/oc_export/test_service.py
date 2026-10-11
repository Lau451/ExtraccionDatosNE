"""tests/oc_export/test_service.py -- exportar_orden_compra (openspec/changes/
oc-export-progress, D2/D3/D6/D8). Sin red: el repository se reemplaza con
monkeypatch y el CSV se escribe de verdad en `tmp_path`."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from services.presupuestacion.oc_export import repository as repo
from services.presupuestacion.oc_export import service
from services.presupuestacion.oc_export.models import ResultadoExportacion
from services.shared.exceptions import (
    ConflictError,
    IntegracionNoConfigurada,
    NotFoundError,
    ValidationError,
)

OC_ID = "oc-1"
DROG = "d1"
USUARIO = "6f0d4f0e-0000-4000-8000-000000000001"


def _oc(**kw):
    base = dict(
        id=OC_ID,
        drogueria_id=DROG,
        cliente_id="cli-1",
        numero_oc="4500-1",
        estado="emitida",
        es_vigente=True,
        deleted_at=None,
        version_numero=1,
        fecha_emision="2026-10-05",
        direccion_entrega=None,
        exportado_at=None,
        exportado_por=None,
        archivo_exportado=None,
    )
    base.update(kw)
    return base


def _item(id_, n, cantidad="10", producto_id="p1", presupuesto_item_id="pi-1", descartado=False):
    return dict(
        presupuesto_item_id=presupuesto_item_id,
        vinculo_descartado=descartado,
        id=id_,
        numero_renglon=n,
        descripcion=f"Renglón {n}",
        cantidad=cantidad,
        precio_unitario="5",
        producto_id=producto_id,
    )


class Escenario:
    """Estado por defecto válido: 1 renglón de 10, 2 entregas de 4 + 6."""

    def __init__(self, monkeypatch, tmp_path):
        self.oc = _oc()
        self.items = [_item("i1", 1)]
        self.codigos_producto = {"p1": "ART-1"}
        self.entregas = [
            dict(id="e1", numero_entrega=1, fecha_entrega_planificada="2026-10-15"),
            dict(id="e2", numero_entrega=2, fecha_entrega_planificada="2026-11-15"),
        ]
        self.entregas_items = [
            dict(entrega_oc_id="e1", oc_item_id="i1", cantidad_planificada="4"),
            dict(entrega_oc_id="e2", oc_item_id="i1", cantidad_planificada="6"),
        ]
        self.codigos_cliente = ["C01"]
        self.marcar = lambda **kw: "ok"
        self.plan_hash = "hash-plan-1"
        self.hash_llamadas: list[dict] = []
        self.auditoria = MagicMock()
        self.marcar_llamadas: list[dict] = []
        self.settings = SimpleNamespace(progress_docs_dir=str(tmp_path), oc_export_encoding="cp1252")
        self.tmp_path = tmp_path

        monkeypatch.setattr(repo, "buscar_orden_compra", lambda c, **kw: self.oc)
        monkeypatch.setattr(repo, "listar_oc_items", lambda c, **kw: self.items)
        monkeypatch.setattr(repo, "listar_codigos_productos", lambda c, **kw: self.codigos_producto)
        monkeypatch.setattr(repo, "listar_entregas", lambda c, **kw: self.entregas)
        monkeypatch.setattr(repo, "listar_entregas_items", lambda c, **kw: self.entregas_items)
        monkeypatch.setattr(repo, "listar_codigos_cliente", lambda c, **kw: self.codigos_cliente)
        monkeypatch.setattr(repo, "buscar_cuit_tercero", lambda c, **kw: "30-11111111-1")
        monkeypatch.setattr(repo, "buscar_nombre_usuario", lambda c, **kw: "Ana")
        monkeypatch.setattr(repo, "marcar_exportada", self._marcar)
        monkeypatch.setattr(repo, "hash_plan", self._hash_plan)
        monkeypatch.setattr(service, "registrar_cambio", self.auditoria)

    def _hash_plan(self, client, **kw):
        self.hash_llamadas.append(kw)
        return self.plan_hash

    def _marcar(self, client, **kw):
        self.marcar_llamadas.append(kw)
        return self.marcar(**kw)

    def exportar(self):
        return service.exportar_orden_compra(
            MagicMock(),
            orden_compra_id=OC_ID,
            drogueria_id=DROG,
            usuario_id=USUARIO,
            settings=self.settings,
        )

    def archivos(self):
        carpeta = self.tmp_path / "oc"
        return sorted(carpeta.iterdir()) if carpeta.exists() else []


@pytest.fixture
def esc(monkeypatch, tmp_path):
    return Escenario(monkeypatch, tmp_path)


def _mensaje_422(esc) -> str:
    with pytest.raises(ValidationError) as exc:
        esc.exportar()
    return exc.value.message


# --- camino feliz -----------------------------------------------------------


def test_exporta_escribe_archivo_marca_y_audita(esc):
    resultado = esc.exportar()

    assert isinstance(resultado, ResultadoExportacion)
    assert resultado.filas == 2
    assert str(resultado.exportado_por) == USUARIO
    assert isinstance(resultado.exportado_at, datetime)
    (archivo,) = esc.archivos()
    assert resultado.archivo == archivo.name
    assert archivo.name.startswith("OC_C01_4500-1_v1_")
    contenido = archivo.read_bytes().decode("cp1252")
    assert "ART-1" in contenido and "30-11111111-1" in contenido
    (llamada,) = esc.marcar_llamadas
    assert llamada["archivo_exportado"] == archivo.name
    assert llamada["drogueria_id"] == DROG
    assert llamada["usuario_id"] == USUARIO
    assert llamada["plan_hash"] == "hash-plan-1"
    esc.auditoria.assert_called_once()
    kw = esc.auditoria.call_args.kwargs
    assert kw["entidad"] == "orden_compra" and kw["entidad_id"] == OC_ID
    assert kw["campo"] == "exportado_at" and kw["usuario_id"] == USUARIO


# --- D8 / lookup ------------------------------------------------------------


def test_sin_progress_docs_dir_da_503_y_no_toca_nada(esc):
    esc.settings.progress_docs_dir = None
    with pytest.raises(IntegracionNoConfigurada):
        esc.exportar()
    assert esc.marcar_llamadas == []


def test_oc_inexistente_o_de_otra_drogueria_da_not_found(esc):
    esc.oc = None
    with pytest.raises(NotFoundError):
        esc.exportar()


# --- D2 ---------------------------------------------------------------------


def test_ya_exportada_da_conflict_con_fecha_y_usuario(esc):
    esc.oc = _oc(exportado_at="2026-10-01T12:00:00+00:00", exportado_por=USUARIO, archivo_exportado="x.csv")
    with pytest.raises(ConflictError) as exc:
        esc.exportar()
    assert "2026-10-01" in exc.value.message or "01/10/2026" in exc.value.message
    assert "Ana" in exc.value.message
    assert esc.archivos() == []


@pytest.mark.parametrize(
    "cambio, texto",
    [
        (dict(estado="cancelada"), "cancelada"),
        (dict(deleted_at="2026-10-01T00:00:00+00:00"), "eliminada"),
        (dict(es_vigente=False), "vigente"),
        (dict(cliente_id=None), "cliente"),
    ],
)
def test_precondiciones_de_cabecera(esc, cambio, texto):
    esc.oc = _oc(**cambio)
    assert texto in _mensaje_422(esc)
    assert esc.archivos() == [] and esc.marcar_llamadas == []


def test_renglon_sin_producto_lista_numero_renglon(esc):
    esc.items = [_item("i1", 1), _item("i2", 7, producto_id=None)]
    esc.entregas_items.append(dict(entrega_oc_id="e1", oc_item_id="i2", cantidad_planificada="10"))
    mensaje = _mensaje_422(esc)
    assert "producto" in mensaje and "7" in mensaje


def test_renglon_con_producto_sin_codigo_interno_lista_numero_renglon(esc):
    esc.items = [_item("i1", 1), _item("i2", 9, producto_id="p2")]
    esc.codigos_producto = {"p1": "ART-1", "p2": None}
    esc.entregas_items.append(dict(entrega_oc_id="e1", oc_item_id="i2", cantidad_planificada="10"))
    mensaje = _mensaje_422(esc)
    assert "código" in mensaje and "9" in mensaje


def test_sin_entregas(esc):
    esc.entregas, esc.entregas_items = [], []
    assert "entrega" in _mensaje_422(esc)


def test_entrega_sin_fecha(esc):
    esc.entregas[1]["fecha_entrega_planificada"] = None
    mensaje = _mensaje_422(esc)
    assert "fecha" in mensaje and "2" in mensaje


def test_suma_planificada_distinta_de_cantidad_lista_renglones(esc):
    esc.entregas_items[1]["cantidad_planificada"] = "5"
    mensaje = _mensaje_422(esc)
    assert "renglón 1" in mensaje


def test_item_de_entrega_huerfano_se_rechaza(esc):
    esc.entregas_items.append(dict(entrega_oc_id="e1", oc_item_id="fantasma", cantidad_planificada="3"))
    mensaje = _mensaje_422(esc)
    assert "fantasma" in mensaje


def test_varios_errores_se_reportan_juntos(esc):
    esc.oc = _oc(cliente_id=None, estado="cancelada")
    esc.codigos_cliente = []
    esc.items = [_item("i1", 1, producto_id=None)]
    esc.entregas[0]["fecha_entrega_planificada"] = None
    mensaje = _mensaje_422(esc)
    for fragmento in ("cancelada", "cliente", "producto", "fecha"):
        assert fragmento in mensaje


# --- D3 ---------------------------------------------------------------------


def test_cero_codigos_de_cliente_da_validation(esc):
    esc.codigos_cliente = []
    assert "código de cliente" in _mensaje_422(esc)


def test_dos_codigos_de_cliente_es_ambiguo_y_no_elige(esc):
    esc.codigos_cliente = ["C01", "C02"]
    mensaje = _mensaje_422(esc)
    assert "C01" in mensaje and "C02" in mensaje
    assert esc.archivos() == []


def test_un_codigo_de_cliente_se_usa_en_el_nombre(esc):
    esc.codigos_cliente = ["ZZ9"]
    assert esc.exportar().archivo.startswith("OC_ZZ9_")


# --- D6 ---------------------------------------------------------------------


def test_ya_exportada_en_el_cas_borra_el_archivo_y_da_conflict(esc):
    esc.marcar = lambda **kw: "ya_exportada"
    with pytest.raises(ConflictError, match="ya fue exportada"):
        esc.exportar()
    assert esc.archivos() == []
    esc.auditoria.assert_not_called()


def test_plan_cambiado_borra_el_archivo_y_da_conflict(esc):
    esc.marcar = lambda **kw: "plan_cambiado"
    with pytest.raises(ConflictError, match="plan cambió mientras se exportaba"):
        esc.exportar()
    assert esc.archivos() == []
    esc.auditoria.assert_not_called()


def test_el_hash_del_plan_se_lee_antes_que_las_entregas(esc, monkeypatch):
    orden: list[str] = []
    monkeypatch.setattr(repo, "hash_plan", lambda c, **kw: orden.append("hash") or "h")
    original = repo.listar_entregas
    monkeypatch.setattr(
        repo, "listar_entregas", lambda c, **kw: orden.append("entregas") or original(c, **kw)
    )
    esc.exportar()
    assert orden[0] == "hash" and "entregas" in orden


def test_update_que_falla_y_no_quedo_marcada_borra_el_archivo_y_relanza(esc):
    def _falla(**kw):
        raise RuntimeError("db caída")

    esc.marcar = _falla
    with pytest.raises(RuntimeError, match="db caída"):
        esc.exportar()
    assert esc.archivos() == []
    esc.auditoria.assert_not_called()


def test_update_ambiguo_que_si_se_aplico_conserva_el_archivo_y_da_exito(esc, monkeypatch):
    """La respuesta del UPDATE se perdió pero la OC quedó marcada con ESTE archivo."""

    def _falla(**kw):
        nombre = kw["archivo_exportado"]
        monkeypatch.setattr(
            repo,
            "buscar_orden_compra",
            lambda c, **k: _oc(
                exportado_at="2026-10-05T12:00:00+00:00", exportado_por=USUARIO, archivo_exportado=nombre
            ),
        )
        raise RuntimeError("respuesta perdida")

    esc.marcar = _falla
    resultado = esc.exportar()
    (archivo,) = esc.archivos()
    assert resultado.archivo == archivo.name
    esc.auditoria.assert_called_once()


def test_update_ambiguo_con_otro_archivo_marcado_borra_el_nuestro_y_relanza(esc, monkeypatch):
    def _falla(**kw):
        monkeypatch.setattr(
            repo,
            "buscar_orden_compra",
            lambda c, **k: _oc(
                exportado_at="2026-10-05T12:00:00+00:00",
                exportado_por=USUARIO,
                archivo_exportado="OC_otro.csv",
            ),
        )
        raise RuntimeError("respuesta perdida")

    esc.marcar = _falla
    with pytest.raises(RuntimeError, match="respuesta perdida"):
        esc.exportar()
    assert esc.archivos() == []


def test_update_ambiguo_y_la_relectura_tambien_falla_borra_el_archivo_y_relanza_el_original(
    esc, monkeypatch
):
    def _falla(**kw):
        def _relectura_falla(c, **k):
            raise ConnectionError("sigue caída")

        monkeypatch.setattr(repo, "buscar_orden_compra", _relectura_falla)
        raise RuntimeError("db caída")

    esc.marcar = _falla
    with pytest.raises(RuntimeError, match="db caída"):
        esc.exportar()
    assert esc.archivos() == []


def test_falla_de_auditoria_no_deshace_la_exportacion(esc):
    esc.auditoria.side_effect = RuntimeError("audit caída")
    resultado = esc.exportar()
    assert len(esc.archivos()) == 1 and resultado.filas == 2


# --- renglones descartados / pendientes (misma clasificación que oc_entregas) ---


def test_renglon_descartado_se_excluye_de_d2_y_del_csv(esc):
    esc.items = [_item("i1", 1), _item("i3", 3, producto_id=None, presupuesto_item_id=None, descartado=True)]
    resultado = esc.exportar()
    assert resultado.filas == 2
    (archivo,) = esc.archivos()
    filas = archivo.read_bytes().decode("cp1252").splitlines()
    assert all(f.split(",")[7] == "1" for f in filas[1:])


def test_renglon_pendiente_de_matching_da_validation(esc):
    esc.items = [_item("i1", 1), _item("i2", 2, presupuesto_item_id=None)]
    esc.entregas_items.append(dict(entrega_oc_id="e1", oc_item_id="i2", cantidad_planificada="10"))
    mensaje = _mensaje_422(esc)
    assert "pendiente" in mensaje and "2" in mensaje
    assert esc.archivos() == []


def test_sin_renglones_confirmados_da_validation(esc):
    esc.items = [_item("i1", 1, presupuesto_item_id=None, descartado=True)]
    assert "confirmado" in _mensaje_422(esc)
