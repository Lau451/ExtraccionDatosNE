import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from services.presupuestacion.core.exceptions import NotFoundError
from services.productos.models import (
    CaracteristicaCreate,
    CategoriaCreate,
    CategoriaUpdate,
    CostoCreate,
    EnvaseCreate,
    MarcaCreate,
    ProductoCaracteristicaCreate,
    ProductoCreate,
    ProductoUpdate,
    StockAjuste,
)
from services.productos.service import (
    actualizar_categoria,
    actualizar_producto,
    ajustar_stock,
    asignar_caracteristica_producto,
    crear_caracteristica,
    crear_categoria,
    crear_costo,
    crear_envase,
    crear_marca,
    crear_producto,
    eliminar_producto,
    listar_caracteristicas_producto,
    listar_categorias,
    listar_costos,
    listar_productos,
    listar_productos_paginado,
    listar_stock,
    obtener_producto,
    quitar_caracteristica_producto,
)


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
def test_listar_productos_paginado_devuelve_total_exacto_contra_postgres_real(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_catalogo
):
    for i in range(5):
        crear_producto(
            service_client,
            drogueria_id=seed_drogueria["id"],
            body=ProductoCreate(codigo_interno=_codigo(), nombre=f"Producto Paginado {i}"),
            usuario_id=seed_usuario_sistema["id"],
        )

    primera_pagina, total = listar_productos_paginado(
        service_client, drogueria_id=seed_drogueria["id"], page=1, page_size=2
    )
    segunda_pagina, _ = listar_productos_paginado(
        service_client, drogueria_id=seed_drogueria["id"], page=2, page_size=2
    )

    assert total == 5
    assert len(primera_pagina) == 2
    assert len(segunda_pagina) == 2
    assert {p["id"] for p in primera_pagina}.isdisjoint({p["id"] for p in segunda_pagina})


@pytest.mark.integration
def test_listar_productos_paginado_filtra_por_q_contra_postgres_real(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_catalogo
):
    crear_producto(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=ProductoCreate(codigo_interno=_codigo(), nombre="Amoxicilina 500mg"),
        usuario_id=seed_usuario_sistema["id"],
    )
    crear_producto(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=ProductoCreate(codigo_interno=_codigo(), nombre="Ibuprofeno 400mg"),
        usuario_id=seed_usuario_sistema["id"],
    )

    items, total = listar_productos_paginado(
        service_client, drogueria_id=seed_drogueria["id"], q="amoxicilina"
    )

    assert total == 1
    assert items[0]["nombre"] == "Amoxicilina 500mg"


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
        body=ProductoCreate(codigo_interno=_codigo(), nombre="Original", droga="Droga A"),
        usuario_id=seed_usuario_sistema["id"],
    )

    resultado = actualizar_producto(
        service_client,
        producto_id=producto["id"],
        drogueria_id=seed_drogueria["id"],
        body=ProductoUpdate(droga="Droga B"),
        usuario_id=seed_usuario_sistema["id"],
    )

    assert resultado["droga"] == "Droga B"
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


@pytest.mark.integration
def test_crear_producto_con_marca_envase_y_alicuota(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_catalogo
):
    marca = crear_marca(service_client, drogueria_id=seed_drogueria["id"], body=MarcaCreate(nombre="Raffo"))
    envase = crear_envase(service_client, drogueria_id=seed_drogueria["id"], body=EnvaseCreate(nombre="Caja"))

    resultado = crear_producto(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=ProductoCreate(
            codigo_interno=_codigo(),
            nombre="Paracetamol 500mg",
            marca_id=marca["id"],
            envase_id=envase["id"],
            alicuota_iva=Decimal("21"),
        ),
        usuario_id=seed_usuario_sistema["id"],
    )

    assert resultado["marca_id"] == marca["id"]
    assert resultado["envase_id"] == envase["id"]
    assert Decimal(str(resultado["alicuota_iva"])) == Decimal("21")


@pytest.mark.integration
def test_asignar_y_quitar_caracteristica_producto(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_catalogo
):
    producto = crear_producto(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=ProductoCreate(codigo_interno=_codigo(), nombre="Diazepam 10mg"),
        usuario_id=seed_usuario_sistema["id"],
    )
    caracteristica = crear_caracteristica(
        service_client, drogueria_id=seed_drogueria["id"], body=CaracteristicaCreate(nombre="PSICOTROPICO")
    )

    asignar_caracteristica_producto(
        service_client,
        producto_id=producto["id"],
        drogueria_id=seed_drogueria["id"],
        body=ProductoCaracteristicaCreate(caracteristica_id=caracteristica["id"]),
        usuario_id=seed_usuario_sistema["id"],
    )
    asignadas = listar_caracteristicas_producto(
        service_client, producto_id=producto["id"], drogueria_id=seed_drogueria["id"]
    )
    assert [c["caracteristica_id"] for c in asignadas] == [caracteristica["id"]]

    quitar_caracteristica_producto(
        service_client,
        producto_id=producto["id"],
        caracteristica_id=caracteristica["id"],
        drogueria_id=seed_drogueria["id"],
    )
    asignadas = listar_caracteristicas_producto(
        service_client, producto_id=producto["id"], drogueria_id=seed_drogueria["id"]
    )
    assert asignadas == []


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
