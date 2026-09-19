import inspect
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError as PydanticValidationError

from services.presupuestacion.core.exceptions import ValidationError
from services.presupuestacion.extraccion import repository as repo
from services.presupuestacion.extraccion import service
from services.presupuestacion.extraccion.models import (
    EntregaPlanIn,
    FilaOrdenCompraIn,
    OrdenCompraOverride,
)

# =============================================================================
# Helpers in-memory (sin DB) -- mismo criterio que test_grupo_extracciones.py.
# =============================================================================


def _fila(
    *,
    descripcion: str = "Item de test",
    cantidad: str = "10",
    precio: str = "5",
    numero_doc: str | None = None,
    producto_id: str | None = None,
) -> FilaOrdenCompraIn:
    return FilaOrdenCompraIn(
        numero_renglon_documento=numero_doc,
        descripcion=descripcion,
        cantidad=cantidad,
        precio_unitario=precio,
        producto_id=producto_id,
    )


def _entrega(
    *, numero: int = 1, plazo: int | None = None, cantidades: dict[str, str] | None = None
) -> EntregaPlanIn:
    return EntregaPlanIn(numero_entrega=numero, plazo_dias=plazo, cantidades_por_posicion=cantidades)


def _cliente(*, drogueria_id: str = "d1", activo: bool = True) -> dict:
    return {"id": "cli-1", "drogueria_id": drogueria_id, "tipo": "hospital", "activo": activo}


# =============================================================================
# 5.1 -- repartir_cantidad (D8): reparto entero con resto al frente, decimal
# con resto al final, usando Decimal. sum(resultado) == cantidad, siempre.
#
# NOTA sobre el caso (100, 3): el prompt de esta fase listaba
# `(100, 3) -> [34, 34, 32]`, que NO satisface el algoritmo de design.md § D8
# ("las primeras `resto` entregas reciben base+1; las restantes, base" --
# 100 // 3 = 33, resto = 1 -> [34, 33, 33]). Se siguió design.md (autoritativo,
# con alternativas consideradas y rationale explícito) en vez del ejemplo del
# prompt -- ver "Deviations" del reporte de esta fase.
# =============================================================================


@pytest.mark.parametrize(
    "cantidad, entregas, esperado",
    [
        (Decimal("100"), 3, [Decimal("34"), Decimal("33"), Decimal("33")]),
        (Decimal("100"), 1, [Decimal("100")]),
        (Decimal("7"), 2, [Decimal("4"), Decimal("3")]),
        (Decimal("0"), 3, [Decimal("0"), Decimal("0"), Decimal("0")]),
    ],
)
def test_repartir_cantidad_casos_enteros(cantidad, entregas, esperado):
    assert service.repartir_cantidad(cantidad, entregas) == esperado


def test_repartir_cantidad_decimal_resto_al_final():
    resultado = service.repartir_cantidad(Decimal("10.5"), 4)
    assert resultado == [Decimal("2.62"), Decimal("2.62"), Decimal("2.62"), Decimal("2.64")]
    assert sum(resultado) == Decimal("10.5")


@pytest.mark.parametrize("cantidad_raw", ["1", "100", "999.99", "0.03", "50000", "7.77"])
@pytest.mark.parametrize("entregas", [1, 2, 3, 4, 7, 10])
def test_repartir_cantidad_propiedad_suma_exacta(cantidad_raw, entregas):
    # Property test (D8): para un rango generado de cantidad y N>=1, la suma
    # de las partes repartidas SIEMPRE es exactamente igual a la cantidad
    # original -- invariante duro del Success Criteria, sin depender de
    # redondeo de punto flotante (Decimal).
    cantidad = Decimal(cantidad_raw)
    resultado = service.repartir_cantidad(cantidad, entregas)
    assert len(resultado) == entregas
    assert sum(resultado) == cantidad


def test_repartir_cantidad_entregas_menor_a_uno_levanta_value_error():
    with pytest.raises(ValueError):
        service.repartir_cantidad(Decimal("10"), 0)


# =============================================================================
# 5.2 -- _validar_orden_compra_override: corre ANTES del primer write.
# =============================================================================


def test_entregas_vacia_viola_min_length_del_modelo():
    # D7: `entregas: list[EntregaPlanIn]` con min_length=1 -- rechazado por
    # pydantic al construir el modelo, ni siquiera llega a _validar_orden_compra_override.
    with pytest.raises(PydanticValidationError):
        OrdenCompraOverride(
            numero_oc="OC-1", cliente_id="cli-1", filas=[_fila()], entregas=[]
        )


def test_entregas_no_vacia_sin_desglose_valido_no_coincide_con_cantidad(monkeypatch):
    # Lista no vacía, pero el desglose manual cargado no suma la cantidad del renglón.
    monkeypatch.setattr(repo, "buscar_cliente_por_id", lambda client, **kw: _cliente())
    override = OrdenCompraOverride(
        numero_oc="OC-1",
        cliente_id="cli-1",
        filas=[_fila(cantidad="10")],
        entregas=[_entrega(numero=1, cantidades={"1": "3"})],
    )
    with pytest.raises(ValidationError) as excinfo:
        service._validar_orden_compra_override(MagicMock(), drogueria_id="d1", override=override)
    assert "renglón 1" in str(excinfo.value)


def test_suma_de_entregas_por_linea_distinta_de_cantidad_levanta_error(monkeypatch):
    monkeypatch.setattr(repo, "buscar_cliente_por_id", lambda client, **kw: _cliente())
    override = OrdenCompraOverride(
        numero_oc="OC-1",
        cliente_id="cli-1",
        filas=[_fila(cantidad="100")],
        entregas=[
            _entrega(numero=1, cantidades={"1": "40"}),
            _entrega(numero=2, cantidades={"1": "40"}),
        ],
    )
    with pytest.raises(ValidationError) as excinfo:
        service._validar_orden_compra_override(MagicMock(), drogueria_id="d1", override=override)
    assert "no coincide" in str(excinfo.value)


def test_precio_vacio_bloquea_confirmacion(monkeypatch):
    # Threat-matrix: un documento sin precio_unitario detectable NO bloquea la
    # extracción (D6 -- el CSV puede traerlo vacío), pero el editor SÍ lo
    # exige antes de confirmar.
    monkeypatch.setattr(repo, "buscar_cliente_por_id", lambda client, **kw: _cliente())
    override = OrdenCompraOverride(
        numero_oc="OC-1", cliente_id="cli-1", filas=[_fila(precio="")], entregas=[_entrega()]
    )
    with pytest.raises(ValidationError) as excinfo:
        service._validar_orden_compra_override(MagicMock(), drogueria_id="d1", override=override)
    assert "precio_unitario" in str(excinfo.value)


def test_precio_unitario_no_numerico_levanta_error(monkeypatch):
    monkeypatch.setattr(repo, "buscar_cliente_por_id", lambda client, **kw: _cliente())
    override = OrdenCompraOverride(
        numero_oc="OC-1",
        cliente_id="cli-1",
        filas=[_fila(precio="no-es-un-numero")],
        entregas=[_entrega()],
    )
    with pytest.raises(ValidationError) as excinfo:
        service._validar_orden_compra_override(MagicMock(), drogueria_id="d1", override=override)
    assert "precio_unitario" in str(excinfo.value)


def test_clave_de_cantidades_por_posicion_fuera_de_rango(monkeypatch):
    monkeypatch.setattr(repo, "buscar_cliente_por_id", lambda client, **kw: _cliente())
    override = OrdenCompraOverride(
        numero_oc="OC-1",
        cliente_id="cli-1",
        filas=[_fila(cantidad="10")],  # 1 sola fila -> rango válido es solo "1"
        entregas=[_entrega(numero=1, cantidades={"5": "10"})],
    )
    with pytest.raises(ValidationError) as excinfo:
        service._validar_orden_compra_override(MagicMock(), drogueria_id="d1", override=override)
    assert "fuera de rango" in str(excinfo.value)


def test_cliente_id_inexistente_levanta_error_antes_del_primer_write(monkeypatch):
    mock_buscar = MagicMock(return_value=None)
    monkeypatch.setattr(repo, "buscar_cliente_por_id", mock_buscar)
    override = OrdenCompraOverride(
        numero_oc="OC-1", cliente_id="no-existe", filas=[_fila()], entregas=[_entrega()]
    )
    with pytest.raises(ValidationError) as excinfo:
        service._validar_orden_compra_override(MagicMock(), drogueria_id="d1", override=override)
    assert "cliente" in str(excinfo.value)
    mock_buscar.assert_called_once()


def test_cliente_id_de_otra_drogueria_levanta_error(monkeypatch):
    monkeypatch.setattr(repo, "buscar_cliente_por_id", lambda client, **kw: _cliente(drogueria_id="otra"))
    override = OrdenCompraOverride(
        numero_oc="OC-1", cliente_id="cli-1", filas=[_fila()], entregas=[_entrega()]
    )
    with pytest.raises(ValidationError) as excinfo:
        service._validar_orden_compra_override(MagicMock(), drogueria_id="d1", override=override)
    assert "cliente" in str(excinfo.value)


def test_validar_override_acumula_errores_de_multiples_problemas_en_un_solo_422(monkeypatch):
    # Mismo patrón que test_validar_filas_override_acumula_errores_de_multiples_filas
    # (existente, licitación/comparativa) -- todos los errores en un solo ValidationError.
    monkeypatch.setattr(repo, "buscar_cliente_por_id", lambda client, **kw: None)
    override = OrdenCompraOverride(
        numero_oc="OC-1",
        cliente_id="no-existe",
        filas=[_fila(precio="")],
        entregas=[_entrega(numero=1, cantidades={"9": "10"})],
    )
    with pytest.raises(ValidationError) as excinfo:
        service._validar_orden_compra_override(MagicMock(), drogueria_id="d1", override=override)

    mensaje = str(excinfo.value)
    assert "cliente" in mensaje
    assert "precio_unitario" in mensaje
    assert "fuera de rango" in mensaje


def test_no_existe_validacion_de_numero_renglon_duplicado():
    # D13.1: numero_renglon lo asigna el sistema por POSICIÓN (1..N) sobre el
    # conjunto final de filas -- es imposible que se repita, a diferencia de
    # licitación/comparativa. No hay ningún chequeo de esto en la función.
    codigo = inspect.getsource(service._validar_orden_compra_override)
    assert "numero_renglon" not in codigo


# =============================================================================
# 5.3 -- Asignación de numero_renglon por POSICIÓN (D13.1), dentro de
# _materializar_orden_compra. Descarta numero_renglon_documento por completo.
# =============================================================================


def _preparar_mocks_materializacion(monkeypatch):
    """Mockea todos los writes de _materializar_orden_compra -- devuelve la
    lista `items_insertados` para inspeccionar qué numero_renglon se asignó."""
    items_insertados: list[dict] = []

    def _fake_insertar_oc_items(client, filas):
        items_insertados.extend(filas)
        return [
            {"id": f"item-{i}", "numero_renglon": fila["numero_renglon"]}
            for i, fila in enumerate(filas, start=1)
        ]

    monkeypatch.setattr(repo, "crear_orden_compra", lambda client, fila: {"id": "oc-1"})
    monkeypatch.setattr(repo, "insertar_oc_items", _fake_insertar_oc_items)
    monkeypatch.setattr(repo, "crear_entrega_oc", lambda client, fila: {"id": "entrega-1"})
    monkeypatch.setattr(repo, "insertar_entregas_oc_items", lambda client, filas: filas)
    monkeypatch.setattr(service, "registrar_evento_ciclo_vida", lambda *a, **kw: None)
    monkeypatch.setattr(service, "registrar_cambio", lambda *a, **kw: None)
    return items_insertados


def test_numero_renglon_se_asigna_por_posicion_no_del_documento(monkeypatch):
    items_insertados = _preparar_mocks_materializacion(monkeypatch)
    filas = [
        _fila(numero_doc="7", cantidad="10"),
        _fila(numero_doc="3", cantidad="20"),
        _fila(numero_doc=None, cantidad="30"),
    ]
    override = OrdenCompraOverride(
        numero_oc="OC-1", cliente_id="cli-1", filas=filas, entregas=[_entrega(numero=1)]
    )

    service._materializar_orden_compra(
        MagicMock(), extraction={"id": "ext-1"}, drogueria_id="d1", usuario_id="u1", override=override
    )

    assert [f["numero_renglon"] for f in items_insertados] == [1, 2, 3]


def test_filas_con_mismo_numero_renglon_documento_no_generan_conflicto(monkeypatch):
    items_insertados = _preparar_mocks_materializacion(monkeypatch)
    filas = [_fila(numero_doc="5", cantidad="10"), _fila(numero_doc="5", cantidad="20")]
    override = OrdenCompraOverride(
        numero_oc="OC-1", cliente_id="cli-1", filas=filas, entregas=[_entrega(numero=1)]
    )

    service._materializar_orden_compra(
        MagicMock(), extraction={"id": "ext-1"}, drogueria_id="d1", usuario_id="u1", override=override
    )

    assert [f["numero_renglon"] for f in items_insertados] == [1, 2]


def test_todas_las_filas_sin_numero_documento_asignan_1_a_n_igual(monkeypatch):
    items_insertados = _preparar_mocks_materializacion(monkeypatch)
    filas = [
        _fila(numero_doc=None, cantidad="10"),
        _fila(numero_doc=None, cantidad="20"),
        _fila(numero_doc=None, cantidad="30"),
    ]
    override = OrdenCompraOverride(
        numero_oc="OC-1", cliente_id="cli-1", filas=filas, entregas=[_entrega(numero=1)]
    )

    service._materializar_orden_compra(
        MagicMock(), extraction={"id": "ext-1"}, drogueria_id="d1", usuario_id="u1", override=override
    )

    assert [f["numero_renglon"] for f in items_insertados] == [1, 2, 3]


def test_materializar_licitacion_sigue_leyendo_item_sin_fallback_no_regresion():
    # D13.2 -- no-regresión: _materializar_licitacion NO se toca en esta fase,
    # sigue confiando en int(fila["item"].strip()) sin fallback.
    codigo = inspect.getsource(service._materializar_licitacion)
    assert 'int(fila["item"].strip())' in codigo


# =============================================================================
# Bugfix -- decimales con coma sin convertir antes del insert de oc_items
# (bug encontrado en vivo: precio_unitario="890,75" crashea con
# "invalid input syntax for type numeric" porque _materializar_orden_compra
# manda fila.cantidad/fila.precio_unitario crudos, sin pasar por _a_decimal(),
# a diferencia de _validar_orden_compra_override que sí los normaliza).
# =============================================================================


def test_precio_unitario_con_coma_se_convierte_a_punto_antes_del_insert(monkeypatch):
    items_insertados = _preparar_mocks_materializacion(monkeypatch)
    filas = [_fila(cantidad="10,5", precio="890,75")]
    override = OrdenCompraOverride(
        numero_oc="OC-1", cliente_id="cli-1", filas=filas, entregas=[_entrega(numero=1)]
    )

    service._materializar_orden_compra(
        MagicMock(), extraction={"id": "ext-1"}, drogueria_id="d1", usuario_id="u1", override=override
    )

    assert items_insertados[0]["precio_unitario"] == "890.75"
    assert items_insertados[0]["cantidad"] == "10.5"


# =============================================================================
# Bugfix -- no atomicidad entre crear_orden_compra e insertar_oc_items: si el
# segundo insert falla, la fila de ordenes_compra recién creada queda
# huérfana (bloquea reintentos futuros vía uq_oc_por_cliente). Verificado en
# vivo. _materializar_orden_compra debe compensar borrando esa fila antes de
# relanzar la excepción original.
# =============================================================================


def test_falla_en_insertar_oc_items_borra_la_orden_compra_huerfana(monkeypatch):
    _preparar_mocks_materializacion(monkeypatch)

    borrados: list[str] = []
    monkeypatch.setattr(repo, "borrar_orden_compra", lambda client, *, orden_compra_id: borrados.append(orden_compra_id))

    def _falla(*args, **kwargs):
        raise RuntimeError("insert de oc_items falló")

    monkeypatch.setattr(repo, "insertar_oc_items", _falla)

    override = OrdenCompraOverride(
        numero_oc="OC-1", cliente_id="cli-1", filas=[_fila()], entregas=[_entrega(numero=1)]
    )

    with pytest.raises(RuntimeError, match="insert de oc_items falló"):
        service._materializar_orden_compra(
            MagicMock(), extraction={"id": "ext-1"}, drogueria_id="d1", usuario_id="u1", override=override
        )

    assert borrados == ["oc-1"]


# =============================================================================
# GET .../filas para orden_compra agrupada (wiring de _TIPOS_CON_LECTURA_DE_FILAS
# con _leer_filas_grupo, requerido por 5.10 para que el endpoint muestre el
# grupo concatenado en vez de solo el archivo ancla -- ver design.md Data Flow
# § TRAMO 2). numero_oc discrepante NUNCA bloquea el GET, solo advierte.
# =============================================================================


def test_leer_filas_extraccion_orden_compra_agrupada_no_bloquea_por_numero_oc_discrepante(
    monkeypatch,
):
    miembros = [
        {"id": "ext-1", "source_filename": "a.pdf", "csv_disk_path": "/fake/a.csv"},
        {"id": "ext-2", "source_filename": "b.pdf", "csv_disk_path": "/fake/b.csv"},
    ]
    monkeypatch.setattr(repo, "listar_miembros_de_grupo", lambda client, **kw: miembros)

    columnas = ["numero_oc", "descripcion", "cantidad", "precio_unitario"]
    filas_por_archivo = {
        "/fake/a.csv": (columnas, [{"numero_oc": "OC-1", "descripcion": "X", "cantidad": "1", "precio_unitario": "1"}]),
        "/fake/b.csv": (columnas, [{"numero_oc": "OC-2", "descripcion": "Y", "cantidad": "1", "precio_unitario": "1"}]),
    }
    monkeypatch.setattr(
        service, "_leer_filas_csv_con_columnas", lambda path: filas_por_archivo[path]
    )

    extraction = {
        "id": "ext-1",
        "document_type": "orden_compra",
        "csv_disk_path": "/fake/a.csv",
        "source_filename": "a.pdf",
        "row_count": 1,
        "grupo_id": "grupo-1",
    }

    resultado = service.leer_filas_extraccion(extraction, client=MagicMock())

    assert len(resultado.miembros) == 2
    assert resultado.filas_leidas == 2
    assert any(
        "orden de compra distintos" in advertencia for advertencia in resultado.advertencias_cabecera
    )
