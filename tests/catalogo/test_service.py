import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from services.presupuestacion.catalogo.models import (
    CategoriaCreate,
    CategoriaUpdate,
    CostoCreate,
    ProductoCreate,
    ProductoUpdate,
    ProveedorCreate,
    ProveedorUpdate,
    StockAjuste,
)
from services.presupuestacion.catalogo.service import (
    actualizar_categoria,
    actualizar_producto,
    actualizar_proveedor,
    ajustar_stock,
    crear_categoria,
    crear_costo,
    crear_producto,
    crear_proveedor,
    eliminar_producto,
    eliminar_proveedor,
    listar_categorias,
    listar_costos,
    listar_productos,
    listar_proveedores,
    listar_stock,
    obtener_producto,
    obtener_proveedor,
)
from services.presupuestacion.core.exceptions import NotFoundError


def _codigo() -> str:
    return f"CAT-{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# productos
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_crear_producto(service_client, seed_drogueria, seed_usuario_sistema, limpiar_catalogo):
    resultado = crear_producto(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=ProductoCreate(codigo_interno=_codigo(), nombre="Jeringa 5ml"),
        usuario_id=seed_usuario_sistema["id"],
    )

    assert resultado["nombre"] == "Jeringa 5ml"
    assert resultado["activo"] is True


@pytest.mark.integration
def test_listar_productos_filtra_por_activo_y_categoria(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_catalogo
):
    categoria = crear_categoria(
        service_client, drogueria_id=seed_drogueria["id"], body=CategoriaCreate(nombre="Descartables")
    )
    a = crear_producto(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=ProductoCreate(codigo_interno=_codigo(), nombre="A", categoria_id=categoria["id"]),
        usuario_id=seed_usuario_sistema["id"],
    )
    crear_producto(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=ProductoCreate(codigo_interno=_codigo(), nombre="B"),
        usuario_id=seed_usuario_sistema["id"],
    )

    filtrados = listar_productos(
        service_client, drogueria_id=seed_drogueria["id"], categoria_id=categoria["id"]
    )
    assert [p["id"] for p in filtrados] == [a["id"]]


@pytest.mark.integration
def test_obtener_producto_de_otra_drogueria_lanza_not_found(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_catalogo
):
    producto = crear_producto(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=ProductoCreate(codigo_interno=_codigo(), nombre="A"),
        usuario_id=seed_usuario_sistema["id"],
    )
    with pytest.raises(NotFoundError):
        obtener_producto(service_client, producto_id=producto["id"], drogueria_id="otra-drogueria")


@pytest.mark.integration
def test_actualizar_producto_solo_pisa_campos_enviados(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_catalogo
):
    producto = crear_producto(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=ProductoCreate(codigo_interno=_codigo(), nombre="Original", laboratorio="Lab A"),
        usuario_id=seed_usuario_sistema["id"],
    )

    resultado = actualizar_producto(
        service_client,
        producto_id=producto["id"],
        drogueria_id=seed_drogueria["id"],
        body=ProductoUpdate(laboratorio="Lab B"),
        usuario_id=seed_usuario_sistema["id"],
    )

    assert resultado["laboratorio"] == "Lab B"
    assert resultado["nombre"] == "Original"


@pytest.mark.integration
def test_eliminar_producto_soft_delete(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_catalogo
):
    producto = crear_producto(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=ProductoCreate(codigo_interno=_codigo(), nombre="A"),
        usuario_id=seed_usuario_sistema["id"],
    )

    eliminar_producto(
        service_client, producto_id=producto["id"], drogueria_id=seed_drogueria["id"],
        usuario_id=seed_usuario_sistema["id"],
    )

    with pytest.raises(NotFoundError):
        obtener_producto(service_client, producto_id=producto["id"], drogueria_id=seed_drogueria["id"])


# ---------------------------------------------------------------------------
# categorias
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_crear_y_actualizar_categoria(service_client, seed_drogueria, limpiar_catalogo):
    creada = crear_categoria(
        service_client, drogueria_id=seed_drogueria["id"], body=CategoriaCreate(nombre="Medicamentos")
    )
    assert creada["activa"] is True

    actualizada = actualizar_categoria(
        service_client,
        categoria_id=creada["id"],
        drogueria_id=seed_drogueria["id"],
        body=CategoriaUpdate(activa=False),
    )
    assert actualizada["activa"] is False
    assert actualizada["nombre"] == "Medicamentos"


@pytest.mark.integration
def test_listar_categorias(service_client, seed_drogueria, limpiar_catalogo):
    crear_categoria(service_client, drogueria_id=seed_drogueria["id"], body=CategoriaCreate(nombre="A"))
    crear_categoria(service_client, drogueria_id=seed_drogueria["id"], body=CategoriaCreate(nombre="B"))

    todas = listar_categorias(service_client, drogueria_id=seed_drogueria["id"])
    assert {c["nombre"] for c in todas} == {"A", "B"}


# ---------------------------------------------------------------------------
# proveedores (Fase 8, design.md D2/D5: wrapper de compatibilidad sobre
# services.terceros.api -- catalogo/ ya no posee la tabla `proveedores`, ver
# catalogo/service.py y catalogo/models.py::ProveedorCreate)
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_crear_listar_actualizar_y_eliminar_proveedor(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_catalogo
):
    creado = crear_proveedor(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=ProveedorCreate(razon_social="Droguería XYZ"),
        usuario_id=seed_usuario_sistema["id"],
    )
    assert creado["activo"] is True

    # el id del proveedor ES el id del tercero (id compartido, design.md sección 5)
    tercero = (
        service_client.table("terceros").select("razon_social").eq("id", creado["id"]).execute().data[0]
    )
    assert tercero["razon_social"] == "Droguería XYZ"

    obtenido = obtener_proveedor(service_client, proveedor_id=creado["id"], drogueria_id=seed_drogueria["id"])
    assert obtenido["razon_social"] == "Droguería XYZ"

    actualizado = actualizar_proveedor(
        service_client,
        proveedor_id=creado["id"],
        drogueria_id=seed_drogueria["id"],
        body=ProveedorUpdate(es_competidor=False),
        usuario_id=seed_usuario_sistema["id"],
    )
    assert actualizado["es_competidor"] is False
    assert actualizado["razon_social"] == "Droguería XYZ"

    todos = listar_proveedores(service_client, drogueria_id=seed_drogueria["id"])
    assert len(todos) == 1

    eliminar_proveedor(
        service_client, proveedor_id=creado["id"], drogueria_id=seed_drogueria["id"],
        usuario_id=seed_usuario_sistema["id"],
    )
    # D4/D1: eliminar_proveedor desactiva el rol, no el tercero -- obtener_proveedor
    # (lookup directo por id) lo sigue encontrando, solo cambia `activo`.
    encontrado = obtener_proveedor(
        service_client, proveedor_id=creado["id"], drogueria_id=seed_drogueria["id"]
    )
    assert encontrado["activo"] is False
    activos = listar_proveedores(service_client, drogueria_id=seed_drogueria["id"], activo=True)
    assert creado["id"] not in {p["id"] for p in activos}


# ---------------------------------------------------------------------------
# costos
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_crear_costo_manual_versiona_igual_que_import(
    service_client, seed_drogueria, seed_usuario_sistema, seed_producto_factory
):
    producto = seed_producto_factory()

    crear_costo(
        service_client,
        producto_id=producto["id"],
        drogueria_id=seed_drogueria["id"],
        body=CostoCreate(costo_unitario=Decimal("50.00"), fecha_desde=date(2026, 1, 1)),
    )
    resultado = crear_costo(
        service_client,
        producto_id=producto["id"],
        drogueria_id=seed_drogueria["id"],
        body=CostoCreate(costo_unitario=Decimal("60.00"), fecha_desde=date(2026, 2, 1)),
    )

    assert resultado["origen"] == "manual"
    historial = listar_costos(service_client, producto_id=producto["id"], drogueria_id=seed_drogueria["id"])
    assert len(historial) == 2
    vigente = next(c for c in historial if c["fecha_hasta"] is None)
    assert Decimal(str(vigente["costo_unitario"])) == Decimal("60.00")
    cerrado = next(c for c in historial if c["fecha_hasta"] is not None)
    assert cerrado["fecha_hasta"] == (date(2026, 2, 1) - timedelta(days=1)).isoformat()


@pytest.mark.integration
def test_crear_costo_manual_no_duplica_si_es_igual(
    service_client, seed_drogueria, seed_producto_factory
):
    producto = seed_producto_factory()
    body = CostoCreate(costo_unitario=Decimal("100.00"), fecha_desde=date(2026, 1, 1))

    crear_costo(service_client, producto_id=producto["id"], drogueria_id=seed_drogueria["id"], body=body)
    crear_costo(service_client, producto_id=producto["id"], drogueria_id=seed_drogueria["id"], body=body)

    historial = listar_costos(service_client, producto_id=producto["id"], drogueria_id=seed_drogueria["id"])
    assert len(historial) == 1


# ---------------------------------------------------------------------------
# stock
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_ajustar_stock_no_toca_comprometida(
    service_client, seed_drogueria, seed_producto_factory, seed_stock_factory
):
    producto = seed_producto_factory()
    seed_stock_factory(producto["id"], disponible="10", comprometida="4", deposito="unico")

    resultado = ajustar_stock(
        service_client,
        producto_id=producto["id"],
        drogueria_id=seed_drogueria["id"],
        body=StockAjuste(cantidad_disponible=Decimal("50")),
    )

    assert Decimal(str(resultado["cantidad_disponible"])) == Decimal("50")
    assert Decimal(str(resultado["cantidad_comprometida"])) == Decimal("4")


@pytest.mark.integration
def test_ajustar_stock_sin_deposito_es_idempotente(
    service_client, seed_drogueria, seed_producto_factory
):
    producto = seed_producto_factory()

    ajustar_stock(
        service_client, producto_id=producto["id"], drogueria_id=seed_drogueria["id"],
        body=StockAjuste(cantidad_disponible=Decimal("10")),
    )
    ajustar_stock(
        service_client, producto_id=producto["id"], drogueria_id=seed_drogueria["id"],
        body=StockAjuste(cantidad_disponible=Decimal("15")),
    )

    filas = listar_stock(service_client, producto_id=producto["id"], drogueria_id=seed_drogueria["id"])
    assert len(filas) == 1
    assert filas[0]["deposito"] == "unico"
