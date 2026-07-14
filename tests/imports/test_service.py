import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from services.presupuestacion.core.exceptions import ValidationError
from services.presupuestacion.imports.models import (
    ImportClienteRow,
    ImportCostoRow,
    ImportProductoRow,
    ImportProveedorRow,
    ImportStockRow,
)
from services.presupuestacion.imports.service import (
    importar_clientes,
    importar_costos,
    importar_productos,
    importar_proveedores,
    importar_stock,
)


def _codigo() -> str:
    return f"IMP-{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# productos
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_importar_productos_crea_nuevos(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_catalogo_import
):
    cod_a, cod_b = _codigo(), _codigo()
    filas = [
        ImportProductoRow(codigo_interno=cod_a, nombre="Producto A"),
        ImportProductoRow(codigo_interno=cod_b, nombre="Producto B"),
    ]

    resultado = importar_productos(
        service_client,
        drogueria_id=seed_drogueria["id"],
        productos=filas,
        usuario_id=seed_usuario_sistema["id"],
    )

    assert resultado == {"creados": 2, "actualizados": 0, "desactivados": 0}
    filas_db = (
        service_client.table("productos")
        .select("codigo_interno,activo,created_by")
        .eq("drogueria_id", seed_drogueria["id"])
        .execute()
        .data
    )
    assert {f["codigo_interno"] for f in filas_db} == {cod_a, cod_b}
    assert all(f["activo"] for f in filas_db)
    assert all(f["created_by"] == seed_usuario_sistema["id"] for f in filas_db)


@pytest.mark.integration
def test_importar_productos_actualiza_sin_pisar_created_by(
    service_client, seed_drogueria, seed_usuario_sistema, seed_usuario_sistema_2, limpiar_catalogo_import
):
    cod = _codigo()
    importar_productos(
        service_client,
        drogueria_id=seed_drogueria["id"],
        productos=[ImportProductoRow(codigo_interno=cod, nombre="Nombre viejo")],
        usuario_id=seed_usuario_sistema["id"],
    )

    resultado = importar_productos(
        service_client,
        drogueria_id=seed_drogueria["id"],
        productos=[ImportProductoRow(codigo_interno=cod, nombre="Nombre nuevo")],
        usuario_id=seed_usuario_sistema_2["id"],
    )

    assert resultado == {"creados": 0, "actualizados": 1, "desactivados": 0}
    fila = (
        service_client.table("productos")
        .select("nombre,created_by,updated_by")
        .eq("drogueria_id", seed_drogueria["id"])
        .eq("codigo_interno", cod)
        .execute()
        .data[0]
    )
    assert fila["nombre"] == "Nombre nuevo"
    assert fila["created_by"] == seed_usuario_sistema["id"], "no debe pisar el created_by original"
    assert fila["updated_by"] == seed_usuario_sistema_2["id"]


@pytest.mark.integration
def test_importar_productos_desactiva_los_que_no_vienen(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_catalogo_import
):
    cod_a, cod_b = _codigo(), _codigo()
    importar_productos(
        service_client,
        drogueria_id=seed_drogueria["id"],
        productos=[
            ImportProductoRow(codigo_interno=cod_a, nombre="A"),
            ImportProductoRow(codigo_interno=cod_b, nombre="B"),
        ],
        usuario_id=seed_usuario_sistema["id"],
    )

    resultado = importar_productos(
        service_client,
        drogueria_id=seed_drogueria["id"],
        productos=[ImportProductoRow(codigo_interno=cod_a, nombre="A")],
        usuario_id=seed_usuario_sistema["id"],
    )

    assert resultado == {"creados": 0, "actualizados": 1, "desactivados": 1}
    filas_db = {
        f["codigo_interno"]: f["activo"]
        for f in service_client.table("productos")
        .select("codigo_interno,activo")
        .eq("drogueria_id", seed_drogueria["id"])
        .execute()
        .data
    }
    assert filas_db[cod_a] is True
    assert filas_db[cod_b] is False


@pytest.mark.integration
def test_importar_productos_lista_vacia_lanza_validation_error(service_client, seed_drogueria):
    with pytest.raises(ValidationError):
        importar_productos(
            service_client, drogueria_id=seed_drogueria["id"], productos=[], usuario_id="x"
        )


# ---------------------------------------------------------------------------
# costos
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_importar_costos_crea_nuevo_vigente(
    service_client, seed_drogueria, seed_producto_factory, seed_usuario_sistema
):
    producto = seed_producto_factory()

    resultado = importar_costos(
        service_client,
        drogueria_id=seed_drogueria["id"],
        costos=[
            ImportCostoRow(
                codigo_interno=producto["codigo_interno"],
                costo_unitario=Decimal("100.50"),
                fecha_desde=date(2026, 1, 1),
            )
        ],
        usuario_id=seed_usuario_sistema["id"],
    )

    assert resultado["nuevos"] == 1
    assert resultado["actualizados"] == 0
    assert resultado["sin_cambios"] == 0
    assert resultado["no_encontrados"] == []

    filas = (
        service_client.table("costos_productos")
        .select("*")
        .eq("producto_id", producto["id"])
        .execute()
        .data
    )
    assert len(filas) == 1
    assert filas[0]["fecha_hasta"] is None
    assert Decimal(str(filas[0]["costo_unitario"])) == Decimal("100.50")


@pytest.mark.integration
def test_importar_costos_actualiza_si_difiere(
    service_client, seed_drogueria, seed_producto_factory, seed_usuario_sistema
):
    producto = seed_producto_factory()
    importar_costos(
        service_client,
        drogueria_id=seed_drogueria["id"],
        costos=[
            ImportCostoRow(
                codigo_interno=producto["codigo_interno"],
                costo_unitario=Decimal("100.00"),
                fecha_desde=date(2026, 1, 1),
            )
        ],
        usuario_id=seed_usuario_sistema["id"],
    )

    resultado = importar_costos(
        service_client,
        drogueria_id=seed_drogueria["id"],
        costos=[
            ImportCostoRow(
                codigo_interno=producto["codigo_interno"],
                costo_unitario=Decimal("150.00"),
                fecha_desde=date(2026, 2, 1),
            )
        ],
        usuario_id=seed_usuario_sistema["id"],
    )

    assert resultado["actualizados"] == 1
    filas = (
        service_client.table("costos_productos")
        .select("*")
        .eq("producto_id", producto["id"])
        .order("fecha_desde")
        .execute()
        .data
    )
    assert len(filas) == 2
    assert filas[0]["fecha_hasta"] == (date(2026, 2, 1) - timedelta(days=1)).isoformat()
    assert filas[1]["fecha_hasta"] is None
    assert Decimal(str(filas[1]["costo_unitario"])) == Decimal("150.00")


@pytest.mark.integration
def test_importar_costos_no_toca_si_es_igual(
    service_client, seed_drogueria, seed_producto_factory, seed_usuario_sistema
):
    producto = seed_producto_factory()
    fila = ImportCostoRow(
        codigo_interno=producto["codigo_interno"],
        costo_unitario=Decimal("100.00"),
        fecha_desde=date(2026, 1, 1),
    )
    importar_costos(
        service_client, drogueria_id=seed_drogueria["id"], costos=[fila],
        usuario_id=seed_usuario_sistema["id"],
    )

    resultado = importar_costos(
        service_client, drogueria_id=seed_drogueria["id"], costos=[fila],
        usuario_id=seed_usuario_sistema["id"],
    )

    assert resultado == {"nuevos": 0, "actualizados": 0, "sin_cambios": 1, "no_encontrados": []}
    filas = (
        service_client.table("costos_productos")
        .select("id")
        .eq("producto_id", producto["id"])
        .execute()
        .data
    )
    assert len(filas) == 1


@pytest.mark.integration
def test_importar_costos_codigo_no_encontrado_se_reporta(
    service_client, seed_drogueria, seed_usuario_sistema
):
    resultado = importar_costos(
        service_client,
        drogueria_id=seed_drogueria["id"],
        costos=[
            ImportCostoRow(
                codigo_interno="NO-EXISTE", costo_unitario=Decimal("10"), fecha_desde=date(2026, 1, 1)
            )
        ],
        usuario_id=seed_usuario_sistema["id"],
    )

    assert resultado["no_encontrados"] == ["NO-EXISTE"]
    assert resultado["nuevos"] == 0


# ---------------------------------------------------------------------------
# stock
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_importar_stock_upsert_por_producto_y_deposito(
    service_client, seed_drogueria, seed_producto_factory, seed_usuario_sistema
):
    producto = seed_producto_factory()

    importar_stock(
        service_client,
        drogueria_id=seed_drogueria["id"],
        stock=[
            ImportStockRow(
                codigo_interno=producto["codigo_interno"], deposito="D1", cantidad_disponible=Decimal("10")
            )
        ],
        usuario_id=seed_usuario_sistema["id"],
    )
    importar_stock(
        service_client,
        drogueria_id=seed_drogueria["id"],
        stock=[
            ImportStockRow(
                codigo_interno=producto["codigo_interno"], deposito="D1", cantidad_disponible=Decimal("25")
            )
        ],
        usuario_id=seed_usuario_sistema["id"],
    )

    filas = (
        service_client.table("stock_productos")
        .select("*")
        .eq("producto_id", producto["id"])
        .execute()
        .data
    )
    assert len(filas) == 1
    assert Decimal(str(filas[0]["cantidad_disponible"])) == Decimal("25")


@pytest.mark.integration
def test_importar_stock_sin_deposito_usa_sentinel_y_es_idempotente(
    service_client, seed_drogueria, seed_producto_factory, seed_usuario_sistema
):
    """Regresión: verificamos empíricamente que un upsert nativo con deposito=NULL
    crea una fila nueva cada vez (Postgres no dedupea NULLs en un UNIQUE). El fix
    normaliza a un sentinel ('unico') antes de upsertear."""
    producto = seed_producto_factory()

    for cantidad in (Decimal("10"), Decimal("20")):
        importar_stock(
            service_client,
            drogueria_id=seed_drogueria["id"],
            stock=[
                ImportStockRow(codigo_interno=producto["codigo_interno"], cantidad_disponible=cantidad)
            ],
            usuario_id=seed_usuario_sistema["id"],
        )

    filas = (
        service_client.table("stock_productos")
        .select("*")
        .eq("producto_id", producto["id"])
        .execute()
        .data
    )
    assert len(filas) == 1, "no debe duplicar filas cuando el import no trae depósito"
    assert filas[0]["deposito"] == "unico"
    assert Decimal(str(filas[0]["cantidad_disponible"])) == Decimal("20")


@pytest.mark.integration
def test_importar_stock_no_toca_cantidad_comprometida(
    service_client, seed_drogueria, seed_producto_factory, seed_stock_factory, seed_usuario_sistema
):
    producto = seed_producto_factory()
    seed_stock_factory(producto["id"], disponible="10", comprometida="5", deposito="unico")

    importar_stock(
        service_client,
        drogueria_id=seed_drogueria["id"],
        stock=[
            ImportStockRow(codigo_interno=producto["codigo_interno"], cantidad_disponible=Decimal("30"))
        ],
        usuario_id=seed_usuario_sistema["id"],
    )

    fila = (
        service_client.table("stock_productos")
        .select("*")
        .eq("producto_id", producto["id"])
        .execute()
        .data[0]
    )
    assert Decimal(str(fila["cantidad_disponible"])) == Decimal("30")
    assert Decimal(str(fila["cantidad_comprometida"])) == Decimal("5")


@pytest.mark.integration
def test_importar_stock_codigo_no_encontrado_se_reporta(
    service_client, seed_drogueria, seed_usuario_sistema
):
    resultado = importar_stock(
        service_client,
        drogueria_id=seed_drogueria["id"],
        stock=[ImportStockRow(codigo_interno="NO-EXISTE", cantidad_disponible=Decimal("1"))],
        usuario_id=seed_usuario_sistema["id"],
    )

    assert resultado == {"upserted": 0, "no_encontrados": ["NO-EXISTE"]}


# ---------------------------------------------------------------------------
# proveedores
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_importar_proveedores_crea_y_actualiza_por_codigo_interno(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_catalogo_import
):
    cod = _codigo()
    importar_proveedores(
        service_client,
        drogueria_id=seed_drogueria["id"],
        proveedores=[ImportProveedorRow(codigo_interno=cod, razon_social="Prov viejo")],
        usuario_id=seed_usuario_sistema["id"],
    )

    resultado = importar_proveedores(
        service_client,
        drogueria_id=seed_drogueria["id"],
        proveedores=[ImportProveedorRow(codigo_interno=cod, razon_social="Prov nuevo")],
        usuario_id=seed_usuario_sistema["id"],
    )

    assert resultado["creados"] == 0
    assert resultado["actualizados"] == 1
    fila = (
        service_client.table("proveedores")
        .select("razon_social")
        .eq("drogueria_id", seed_drogueria["id"])
        .eq("codigo_interno", cod)
        .execute()
        .data[0]
    )
    assert fila["razon_social"] == "Prov nuevo"


@pytest.mark.integration
def test_importar_proveedores_sin_codigo_interno_siempre_inserta_nuevo(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_catalogo_import
):
    resultado = importar_proveedores(
        service_client,
        drogueria_id=seed_drogueria["id"],
        proveedores=[
            ImportProveedorRow(razon_social="Sin código 1"),
            ImportProveedorRow(razon_social="Sin código 2"),
        ],
        usuario_id=seed_usuario_sistema["id"],
    )

    assert resultado["creados"] == 2
    assert resultado["sin_codigo_interno"] == 2
    filas = (
        service_client.table("proveedores")
        .select("id")
        .eq("drogueria_id", seed_drogueria["id"])
        .is_("codigo_interno", None)
        .execute()
        .data
    )
    assert len(filas) == 2


@pytest.mark.integration
def test_importar_proveedores_desactiva_los_que_no_vienen(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_catalogo_import
):
    cod_a, cod_b = _codigo(), _codigo()
    importar_proveedores(
        service_client,
        drogueria_id=seed_drogueria["id"],
        proveedores=[
            ImportProveedorRow(codigo_interno=cod_a, razon_social="A"),
            ImportProveedorRow(codigo_interno=cod_b, razon_social="B"),
        ],
        usuario_id=seed_usuario_sistema["id"],
    )

    resultado = importar_proveedores(
        service_client,
        drogueria_id=seed_drogueria["id"],
        proveedores=[ImportProveedorRow(codigo_interno=cod_a, razon_social="A")],
        usuario_id=seed_usuario_sistema["id"],
    )

    assert resultado["desactivados"] == 1
    activos = {
        f["codigo_interno"]: f["activo"]
        for f in service_client.table("proveedores")
        .select("codigo_interno,activo")
        .eq("drogueria_id", seed_drogueria["id"])
        .execute()
        .data
    }
    assert activos[cod_a] is True
    assert activos[cod_b] is False


# ---------------------------------------------------------------------------
# clientes
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_importar_clientes_crea_nuevo(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_catalogo_import
):
    cod = _codigo()
    resultado = importar_clientes(
        service_client,
        drogueria_id=seed_drogueria["id"],
        clientes=[ImportClienteRow(codigo_interno=cod, nombre="Hospital Test", tipo="hospital")],
        usuario_id=seed_usuario_sistema["id"],
    )

    assert resultado["creados"] == 1
    fila = (
        service_client.table("clientes")
        .select("nombre,tipo,activo")
        .eq("drogueria_id", seed_drogueria["id"])
        .eq("codigo_interno", cod)
        .execute()
        .data[0]
    )
    assert fila["nombre"] == "Hospital Test"
    assert fila["activo"] is True


@pytest.mark.integration
def test_importar_clientes_nuevo_sin_nombre_lanza_validation_error(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_catalogo_import
):
    with pytest.raises(ValidationError):
        importar_clientes(
            service_client,
            drogueria_id=seed_drogueria["id"],
            clientes=[ImportClienteRow(codigo_interno=_codigo())],
            usuario_id=seed_usuario_sistema["id"],
        )


@pytest.mark.integration
def test_importar_clientes_actualiza_sin_pisar_campos_no_enviados(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_catalogo_import
):
    cod = _codigo()
    importar_clientes(
        service_client,
        drogueria_id=seed_drogueria["id"],
        clientes=[
            ImportClienteRow(
                codigo_interno=cod, nombre="Hospital Test", tipo="hospital",
                condiciones_pago="50% contra entrega",
            )
        ],
        usuario_id=seed_usuario_sistema["id"],
    )

    resultado = importar_clientes(
        service_client,
        drogueria_id=seed_drogueria["id"],
        clientes=[ImportClienteRow(codigo_interno=cod, ciudad="Rosario")],
        usuario_id=seed_usuario_sistema["id"],
    )

    assert resultado["actualizados"] == 1
    fila = (
        service_client.table("clientes")
        .select("ciudad,condiciones_pago,nombre")
        .eq("drogueria_id", seed_drogueria["id"])
        .eq("codigo_interno", cod)
        .execute()
        .data[0]
    )
    assert fila["ciudad"] == "Rosario"
    assert fila["condiciones_pago"] == "50% contra entrega", "no debe pisar un campo que el import no trajo"
    assert fila["nombre"] == "Hospital Test"


@pytest.mark.integration
def test_importar_clientes_desactiva_los_que_no_vienen(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_catalogo_import
):
    cod_a, cod_b = _codigo(), _codigo()
    importar_clientes(
        service_client,
        drogueria_id=seed_drogueria["id"],
        clientes=[
            ImportClienteRow(codigo_interno=cod_a, nombre="A", tipo="hospital"),
            ImportClienteRow(codigo_interno=cod_b, nombre="B", tipo="hospital"),
        ],
        usuario_id=seed_usuario_sistema["id"],
    )

    resultado = importar_clientes(
        service_client,
        drogueria_id=seed_drogueria["id"],
        clientes=[ImportClienteRow(codigo_interno=cod_a, nombre="A", tipo="hospital")],
        usuario_id=seed_usuario_sistema["id"],
    )

    assert resultado["desactivados"] == 1
    activos = {
        f["codigo_interno"]: f["activo"]
        for f in service_client.table("clientes")
        .select("codigo_interno,activo")
        .eq("drogueria_id", seed_drogueria["id"])
        .execute()
        .data
    }
    assert activos[cod_a] is True
    assert activos[cod_b] is False
