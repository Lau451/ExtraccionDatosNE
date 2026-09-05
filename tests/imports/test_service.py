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
from services.terceros.api import TerceroCreate, crear_tercero


def _codigo() -> str:
    return f"IMP-{uuid.uuid4().hex[:8]}"


def _cuit() -> str:
    """11 dígitos, formato exigido por ck_terceros_cuit (0008_terceros_modelo.sql)."""
    return f"{uuid.uuid4().int % 10**11:011d}"


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
# proveedores (Fase 9: RPC upsert_terceros_legacy, design.md sección 7)
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_importar_proveedores_crea_y_actualiza_por_codigo_interno(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_catalogo_import
):
    cod = _codigo()
    resultado_1 = importar_proveedores(
        service_client,
        drogueria_id=seed_drogueria["id"],
        proveedores=[ImportProveedorRow(codigo_interno=cod, razon_social="Prov viejo")],
        usuario_id=seed_usuario_sistema["id"],
    )
    assert resultado_1 == {"creados": 1, "actualizados": 0, "desactivados": 0}

    resultado_2 = importar_proveedores(
        service_client,
        drogueria_id=seed_drogueria["id"],
        proveedores=[ImportProveedorRow(codigo_interno=cod, razon_social="Prov nuevo")],
        usuario_id=seed_usuario_sistema["id"],
    )

    assert resultado_2["creados"] == 0
    assert resultado_2["actualizados"] == 1
    fila = (
        service_client.table("terceros")
        .select("razon_social")
        .eq("drogueria_id", seed_drogueria["id"])
        .eq("codigo_interno", cod)
        .execute()
        .data[0]
    )
    assert fila["razon_social"] == "Prov nuevo"


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
    filas = {
        f["codigo_interno"]: f["id"]
        for f in service_client.table("terceros")
        .select("codigo_interno,id")
        .eq("drogueria_id", seed_drogueria["id"])
        .in_("codigo_interno", [cod_a, cod_b])
        .execute()
        .data
    }
    activos_rol = {
        f["id"]: f["activo"]
        for f in service_client.table("proveedores")
        .select("id,activo")
        .in_("id", list(filas.values()))
        .execute()
        .data
    }
    assert activos_rol[filas[cod_a]] is True
    assert activos_rol[filas[cod_b]] is False, "la fila de ROL se desactiva, no se borra"
    tercero_b = (
        service_client.table("terceros")
        .select("activo")
        .eq("id", filas[cod_b])
        .execute()
        .data[0]
    )
    assert tercero_b["activo"] is True, "el tercero no se desactiva, solo su rol proveedor (D1/D4)"


# ---------------------------------------------------------------------------
# clientes (Fase 9: RPC upsert_terceros_legacy)
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_importar_clientes_crea_nuevo(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_catalogo_import
):
    cod = _codigo()
    resultado = importar_clientes(
        service_client,
        drogueria_id=seed_drogueria["id"],
        clientes=[ImportClienteRow(codigo_interno=cod, razon_social="Hospital Test", tipo="hospital")],
        usuario_id=seed_usuario_sistema["id"],
    )

    assert resultado == {"creados": 1, "actualizados": 0, "desactivados": 0}
    tercero = (
        service_client.table("terceros")
        .select("razon_social,activo")
        .eq("drogueria_id", seed_drogueria["id"])
        .eq("codigo_interno", cod)
        .execute()
        .data[0]
    )
    assert tercero["razon_social"] == "Hospital Test"
    assert tercero["activo"] is True
    rol = (
        service_client.table("clientes")
        .select("tipo,activo")
        .eq("drogueria_id", seed_drogueria["id"])
        .execute()
        .data
    )
    assert any(r["tipo"] == "hospital" and r["activo"] for r in rol)


@pytest.mark.integration
def test_importar_clientes_lista_vacia_lanza_validation_error(service_client, seed_drogueria):
    with pytest.raises(ValidationError):
        importar_clientes(
            service_client, drogueria_id=seed_drogueria["id"], clientes=[], usuario_id="x"
        )


# ---------------------------------------------------------------------------
# 9.4/9.5 — idempotencia: reimportar el mismo CSV no duplica terceros ni roles
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_reimportar_mismo_csv_actualiza_tercero_en_vez_de_duplicarlo(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_catalogo_import
):
    cod = _codigo()
    fila = ImportClienteRow(codigo_interno=cod, razon_social="Hospital Reimport", tipo="hospital")

    importar_clientes(
        service_client, drogueria_id=seed_drogueria["id"], clientes=[fila],
        usuario_id=seed_usuario_sistema["id"],
    )
    importar_clientes(
        service_client, drogueria_id=seed_drogueria["id"], clientes=[fila],
        usuario_id=seed_usuario_sistema["id"],
    )

    terceros = (
        service_client.table("terceros")
        .select("id")
        .eq("drogueria_id", seed_drogueria["id"])
        .eq("codigo_interno", cod)
        .execute()
        .data
    )
    assert len(terceros) == 1


@pytest.mark.integration
def test_reimportar_no_duplica_fila_de_rol_clientes(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_catalogo_import
):
    cod = _codigo()
    fila = ImportClienteRow(codigo_interno=cod, razon_social="Hospital Reimport 2", tipo="hospital")

    importar_clientes(
        service_client, drogueria_id=seed_drogueria["id"], clientes=[fila],
        usuario_id=seed_usuario_sistema["id"],
    )
    importar_clientes(
        service_client, drogueria_id=seed_drogueria["id"], clientes=[fila],
        usuario_id=seed_usuario_sistema["id"],
    )

    tercero_id = (
        service_client.table("terceros")
        .select("id")
        .eq("drogueria_id", seed_drogueria["id"])
        .eq("codigo_interno", cod)
        .execute()
        .data[0]["id"]
    )
    roles = service_client.table("clientes").select("id").eq("id", tercero_id).execute().data
    assert len(roles) == 1


# ---------------------------------------------------------------------------
# 9.6/9.7 — split identidad/rol entre las dos fuentes legadas
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_registro_en_ambas_fuentes_produce_un_tercero_y_dos_roles(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_catalogo_import
):
    cuit = _cuit()
    importar_clientes(
        service_client,
        drogueria_id=seed_drogueria["id"],
        clientes=[
            ImportClienteRow(codigo_interno=_codigo(), razon_social="Doble Rol SA", cuit=cuit, tipo="hospital")
        ],
        usuario_id=seed_usuario_sistema["id"],
    )
    importar_proveedores(
        service_client,
        drogueria_id=seed_drogueria["id"],
        proveedores=[ImportProveedorRow(codigo_interno=_codigo(), razon_social="Doble Rol SA", cuit=cuit)],
        usuario_id=seed_usuario_sistema["id"],
    )

    terceros = (
        service_client.table("terceros")
        .select("id")
        .eq("drogueria_id", seed_drogueria["id"])
        .eq("cuit", cuit)
        .execute()
        .data
    )
    assert len(terceros) == 1
    tercero_id = terceros[0]["id"]
    assert service_client.table("clientes").select("id").eq("id", tercero_id).execute().data
    assert service_client.table("proveedores").select("id").eq("id", tercero_id).execute().data


@pytest.mark.integration
def test_registro_solo_cliente_no_crea_proveedor(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_catalogo_import
):
    cod = _codigo()
    importar_clientes(
        service_client,
        drogueria_id=seed_drogueria["id"],
        clientes=[ImportClienteRow(codigo_interno=cod, razon_social="Solo Cliente SA", tipo="hospital")],
        usuario_id=seed_usuario_sistema["id"],
    )

    tercero_id = (
        service_client.table("terceros")
        .select("id")
        .eq("drogueria_id", seed_drogueria["id"])
        .eq("codigo_interno", cod)
        .execute()
        .data[0]["id"]
    )
    assert not service_client.table("proveedores").select("id").eq("id", tercero_id).execute().data


# ---------------------------------------------------------------------------
# 9.8/9.9 — trazabilidad legada (terceros_legacy_map)
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_primer_import_crea_fila_en_legacy_map(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_catalogo_import
):
    cod = _codigo()
    importar_clientes(
        service_client,
        drogueria_id=seed_drogueria["id"],
        clientes=[ImportClienteRow(codigo_interno=cod, razon_social="Trazabilidad SA", tipo="hospital")],
        usuario_id=seed_usuario_sistema["id"],
    )

    mapa = (
        service_client.table("terceros_legacy_map")
        .select("id,entidad_legacy,codigo_legacy")
        .eq("drogueria_id", seed_drogueria["id"])
        .eq("codigo_legacy", cod)
        .execute()
        .data
    )
    assert len(mapa) == 1
    assert mapa[0]["entidad_legacy"] == "cliente"


@pytest.mark.integration
def test_reimportar_no_duplica_fila_de_legacy_map(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_catalogo_import
):
    cod = _codigo()
    fila = ImportClienteRow(codigo_interno=cod, razon_social="Trazabilidad SA 2", tipo="hospital")

    importar_clientes(
        service_client, drogueria_id=seed_drogueria["id"], clientes=[fila],
        usuario_id=seed_usuario_sistema["id"],
    )
    importar_clientes(
        service_client, drogueria_id=seed_drogueria["id"], clientes=[fila],
        usuario_id=seed_usuario_sistema["id"],
    )

    mapa = (
        service_client.table("terceros_legacy_map")
        .select("id")
        .eq("drogueria_id", seed_drogueria["id"])
        .eq("codigo_legacy", cod)
        .execute()
        .data
    )
    assert len(mapa) == 1


# ---------------------------------------------------------------------------
# 9.10 — desactivación por ausencia (solo la fila de ROL, D1/D4)
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_import_desactiva_la_fila_de_rol_ausente_sin_eliminar_el_tercero(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_catalogo_import
):
    cod_a, cod_b = _codigo(), _codigo()
    importar_clientes(
        service_client,
        drogueria_id=seed_drogueria["id"],
        clientes=[
            ImportClienteRow(codigo_interno=cod_a, razon_social="Se queda", tipo="hospital"),
            ImportClienteRow(codigo_interno=cod_b, razon_social="Desaparece del CSV", tipo="hospital"),
        ],
        usuario_id=seed_usuario_sistema["id"],
    )

    resultado = importar_clientes(
        service_client,
        drogueria_id=seed_drogueria["id"],
        clientes=[ImportClienteRow(codigo_interno=cod_a, razon_social="Se queda", tipo="hospital")],
        usuario_id=seed_usuario_sistema["id"],
    )

    assert resultado["desactivados"] == 1
    tercero_b = (
        service_client.table("terceros")
        .select("id,activo")
        .eq("drogueria_id", seed_drogueria["id"])
        .eq("codigo_interno", cod_b)
        .execute()
        .data[0]
    )
    assert tercero_b["activo"] is True, "el tercero NO se borra ni se desactiva por ausencia (design.md sección 7)"
    rol_b = service_client.table("clientes").select("activo").eq("id", tercero_b["id"]).execute().data[0]
    assert rol_b["activo"] is False, "la fila de ROL cliente sí se desactiva"


# ---------------------------------------------------------------------------
# 9.11 — coexistencia nativo + import
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_import_actualiza_tercero_creado_nativamente_en_vez_de_duplicarlo(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_catalogo_import
):
    cod = _codigo()
    cuit = _cuit()
    nativo = crear_tercero(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=TerceroCreate(codigo_interno=cod, razon_social="Nativo SA", cuit=cuit),
        usuario_id=seed_usuario_sistema["id"],
    )

    resultado = importar_clientes(
        service_client,
        drogueria_id=seed_drogueria["id"],
        clientes=[ImportClienteRow(codigo_interno=cod, razon_social="Nativo SA (import)", cuit=cuit, tipo="hospital")],
        usuario_id=seed_usuario_sistema["id"],
    )

    assert resultado["creados"] == 0
    assert resultado["actualizados"] == 1
    terceros = (
        service_client.table("terceros")
        .select("id")
        .eq("drogueria_id", seed_drogueria["id"])
        .eq("cuit", cuit)
        .execute()
        .data
    )
    assert len(terceros) == 1
    assert terceros[0]["id"] == nativo["id"]
    mapa = (
        service_client.table("terceros_legacy_map")
        .select("tercero_id")
        .eq("drogueria_id", seed_drogueria["id"])
        .eq("codigo_legacy", cod)
        .execute()
        .data
    )
    assert len(mapa) == 1
    assert mapa[0]["tercero_id"] == nativo["id"]


# ---------------------------------------------------------------------------
# 9.12 — D1 doble rol: mismo CUIT como cliente y luego como proveedor
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_mismo_cuit_como_cliente_y_luego_proveedor_produce_un_tercero_con_dos_roles(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_catalogo_import
):
    cuit = _cuit()
    importar_clientes(
        service_client,
        drogueria_id=seed_drogueria["id"],
        clientes=[
            ImportClienteRow(codigo_interno=_codigo(), razon_social="Doble Rol Secuencial SA", cuit=cuit, tipo="hospital")
        ],
        usuario_id=seed_usuario_sistema["id"],
    )
    importar_proveedores(
        service_client,
        drogueria_id=seed_drogueria["id"],
        proveedores=[
            ImportProveedorRow(codigo_interno=_codigo(), razon_social="Doble Rol Secuencial SA", cuit=cuit)
        ],
        usuario_id=seed_usuario_sistema["id"],
    )

    terceros = (
        service_client.table("terceros")
        .select("id")
        .eq("drogueria_id", seed_drogueria["id"])
        .eq("cuit", cuit)
        .execute()
        .data
    )
    assert len(terceros) == 1
    tercero_id = terceros[0]["id"]
    assert service_client.table("clientes").select("id").eq("id", tercero_id).execute().data
    assert service_client.table("proveedores").select("id").eq("id", tercero_id).execute().data


# ---------------------------------------------------------------------------
# 9.13 — D1 colisión de códigos entre espacios legados (cliente vs proveedor)
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.xfail(
    strict=True,
    reason=(
        "Defecto descubierto en Fase 9 (ver supabase/migrations/0009_fix_upsert_terceros_"
        "legacy_ambiguous_column.sql y openspec/changes/terceros-modelo/tasks.md 9.13): "
        "uq_terceros_codigo es UNIQUE(drogueria_id, codigo_interno) SIN componente de "
        "entidad_legacy (0008_terceros_modelo.sql, sección 2). El RPC upsert_terceros_legacy "
        "solo desambigua colisiones vía terceros_legacy_map (por entidad_legacy) o CUIT — "
        "nunca por codigo_interno. Cuando dos empresas DISTINTAS (sin CUIT en común) "
        "comparten el mismo codigo_legacy en el CSV de clientes y en el de proveedores, el "
        "segundo INSERT en `terceros` viola uq_terceros_codigo y el RPC entero falla "
        "(postgrest.exceptions.APIError, unique_violation), en lugar de crear dos terceros "
        "distintos como exige D1 (design.md). Nota: hasta que se aplique la migración 0009 "
        "(fix de un bug DISTINTO y previo — 'column reference codigo_legacy is ambiguous', "
        "que hoy rompe TODA llamada al RPC) este test falla por esa causa anterior, no por "
        "la colisión de uq_terceros_codigo en sí; de todos modos permanece xfail porque, aun "
        "con 0009 aplicado, la colisión de uq_terceros_codigo seguiría reproduciéndose. "
        "Requiere una migración de seguimiento (fuera del alcance de esta fase/PR) que "
        "relaje uq_terceros_codigo, p.ej. condicionándolo a los terceros creados nativamente "
        "(sin origen legado) o agregando una dimensión de entidad/origen al índice."
    ),
)
def test_codigo_legacy_colisiona_entre_cliente_y_proveedor_produce_dos_terceros_distintos(
    service_client, seed_drogueria, seed_usuario_sistema, limpiar_catalogo_import
):
    codigo_compartido = _codigo()
    importar_clientes(
        service_client,
        drogueria_id=seed_drogueria["id"],
        clientes=[
            ImportClienteRow(codigo_interno=codigo_compartido, razon_social="Empresa Cliente SA", tipo="hospital")
        ],
        usuario_id=seed_usuario_sistema["id"],
    )
    importar_proveedores(
        service_client,
        drogueria_id=seed_drogueria["id"],
        proveedores=[
            ImportProveedorRow(codigo_interno=codigo_compartido, razon_social="Empresa Proveedor SA")
        ],
        usuario_id=seed_usuario_sistema["id"],
    )

    terceros = (
        service_client.table("terceros")
        .select("id,razon_social")
        .eq("drogueria_id", seed_drogueria["id"])
        .eq("codigo_interno", codigo_compartido)
        .execute()
        .data
    )
    assert len(terceros) == 2, "codigo_legacy='...' en clientes y en proveedores no debe fusionar dos empresas (D1)"
