import uuid
from datetime import date
from decimal import Decimal

import pytest

from services.presupuestacion.core.exceptions import NotFoundError
from services.productos.api import CostoAVersionar, versionar_costos
from services.productos.models import (
    CaracteristicaCreate,
    CategoriaCreate,
    CategoriaUpdate,
    ProductoCaracteristicaCreate,
)
from services.productos.service import (
    actualizar_categoria,
    asignar_caracteristica_producto,
    crear_caracteristica,
    crear_categoria,
    listar_caracteristicas_producto,
    listar_categorias,
    listar_costos,
    listar_productos,
    listar_productos_paginado,
    obtener_producto,
    quitar_caracteristica_producto,
)


def _codigo() -> str:
    return f"CAT-{uuid.uuid4().hex[:8]}"


def _seed_producto(service_client, drogueria_id: str, nombre: str, **campos) -> dict:
    """Los productos los da de alta Progress (etapa 7): se siembran directo en la
    tabla. `limpiar_catalogo` los borra por droguería."""
    fila = {"drogueria_id": drogueria_id, "codigo_interno": _codigo(), "nombre": nombre, **campos}
    return service_client.table("productos").insert(fila).execute().data[0]


# ---------------------------------------------------------------------------
# productos
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_listar_productos_filtra_por_activo_y_categoria(
    service_client, seed_drogueria, limpiar_catalogo
):
    categoria = crear_categoria(
        service_client, drogueria_id=seed_drogueria["id"], body=CategoriaCreate(nombre="Descartables")
    )
    a = _seed_producto(service_client, seed_drogueria["id"], "A", categoria_id=categoria["id"])
    _seed_producto(service_client, seed_drogueria["id"], "B")

    filtrados = listar_productos(
        service_client, drogueria_id=seed_drogueria["id"], categoria_id=categoria["id"]
    )
    assert [p["id"] for p in filtrados] == [a["id"]]


@pytest.mark.integration
def test_listar_productos_paginado_devuelve_total_exacto_contra_postgres_real(
    service_client, seed_drogueria, limpiar_catalogo
):
    for i in range(5):
        _seed_producto(service_client, seed_drogueria["id"], f"Producto Paginado {i}")

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
    service_client, seed_drogueria, limpiar_catalogo
):
    _seed_producto(service_client, seed_drogueria["id"], "Amoxicilina 500mg")
    _seed_producto(service_client, seed_drogueria["id"], "Ibuprofeno 400mg")

    items, total = listar_productos_paginado(
        service_client, drogueria_id=seed_drogueria["id"], q="amoxicilina"
    )

    assert total == 1
    assert items[0]["nombre"] == "Amoxicilina 500mg"


@pytest.mark.integration
def test_obtener_producto_de_otra_drogueria_lanza_not_found(
    service_client, seed_drogueria, limpiar_catalogo
):
    producto = _seed_producto(service_client, seed_drogueria["id"], "A")
    with pytest.raises(NotFoundError):
        obtener_producto(service_client, producto_id=producto["id"], drogueria_id="otra-drogueria")


@pytest.mark.integration
def test_asignar_y_quitar_caracteristica_producto(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_catalogo
):
    producto = _seed_producto(service_client, seed_drogueria["id"], "Diazepam 10mg")
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
def test_versionar_costos_en_lote_aplica_la_misma_regla(
    service_client, seed_drogueria, seed_producto_factory
):
    nuevo, cambia, igual = seed_producto_factory(), seed_producto_factory(), seed_producto_factory()
    for producto in (cambia, igual):
        service_client.table("costos_productos").insert(
            {
                "producto_id": producto["id"],
                "drogueria_id": seed_drogueria["id"],
                "costo_unitario": "10.00",
                "fecha_desde": "2026-01-01",
                "origen": "manual",
            }
        ).execute()

    resultado = versionar_costos(
        service_client,
        drogueria_id=seed_drogueria["id"],
        costos=[
            CostoAVersionar(producto_id=nuevo["id"], costo_unitario=Decimal("5.00"), fecha_desde=date(2026, 3, 1)),
            CostoAVersionar(producto_id=cambia["id"], costo_unitario=Decimal("12.00"), fecha_desde=date(2026, 3, 1)),
            CostoAVersionar(producto_id=igual["id"], costo_unitario=Decimal("10.00"), fecha_desde=date(2026, 3, 1)),
        ],
        origen="import_sistema",
    )

    assert resultado == {"nuevos": 1, "actualizados": 1, "sin_cambios": 1}
    historial_nuevo = listar_costos(service_client, producto_id=nuevo["id"], drogueria_id=seed_drogueria["id"])
    assert [(c["origen"], c["fecha_hasta"]) for c in historial_nuevo] == [("import_sistema", None)]
    historial_cambia = listar_costos(service_client, producto_id=cambia["id"], drogueria_id=seed_drogueria["id"])
    assert [(c["origen"], Decimal(str(c["costo_unitario"])), c["fecha_hasta"]) for c in historial_cambia] == [
        ("import_sistema", Decimal("12.00"), None),
        ("manual", Decimal("10.00"), "2026-02-28"),
    ]
    historial_igual = listar_costos(service_client, producto_id=igual["id"], drogueria_id=seed_drogueria["id"])
    assert [(c["origen"], c["fecha_hasta"]) for c in historial_igual] == [("manual", None)]
