from fastapi import APIRouter, Depends

from services.presupuestacion.core.auth import UsuarioPerfil, require_capacidad
from services.presupuestacion.imports.models import (
    ImportClientesRequest,
    ImportClientesResultado,
    ImportCostosRequest,
    ImportCostosResultado,
    ImportProductosRequest,
    ImportProductosResultado,
    ImportProveedoresRequest,
    ImportProveedoresResultado,
    ImportStockRequest,
    ImportStockResultado,
)
from services.presupuestacion.imports.service import (
    importar_clientes_para_endpoint,
    importar_costos_para_endpoint,
    importar_productos_para_endpoint,
    importar_proveedores_para_endpoint,
    importar_stock_para_endpoint,
)

router = APIRouter(prefix="/imports")


@router.post("/productos", response_model=ImportProductosResultado)
def importar_productos_endpoint(
    body: ImportProductosRequest,
    usuario: UsuarioPerfil = Depends(require_capacidad("imports.importar")),
) -> ImportProductosResultado:
    resultado = importar_productos_para_endpoint(
        drogueria_id=usuario.drogueria_id, productos=body.productos
    )
    return ImportProductosResultado(**resultado)


@router.post("/costos", response_model=ImportCostosResultado)
def importar_costos_endpoint(
    body: ImportCostosRequest,
    usuario: UsuarioPerfil = Depends(require_capacidad("imports.importar")),
) -> ImportCostosResultado:
    resultado = importar_costos_para_endpoint(drogueria_id=usuario.drogueria_id, costos=body.costos)
    return ImportCostosResultado(**resultado)


@router.post("/stock", response_model=ImportStockResultado)
def importar_stock_endpoint(
    body: ImportStockRequest,
    usuario: UsuarioPerfil = Depends(require_capacidad("imports.importar")),
) -> ImportStockResultado:
    resultado = importar_stock_para_endpoint(drogueria_id=usuario.drogueria_id, stock=body.stock)
    return ImportStockResultado(**resultado)


@router.post("/proveedores", response_model=ImportProveedoresResultado)
def importar_proveedores_endpoint(
    body: ImportProveedoresRequest,
    usuario: UsuarioPerfil = Depends(require_capacidad("imports.importar")),
) -> ImportProveedoresResultado:
    resultado = importar_proveedores_para_endpoint(
        drogueria_id=usuario.drogueria_id, proveedores=body.proveedores
    )
    return ImportProveedoresResultado(**resultado)


@router.post("/clientes", response_model=ImportClientesResultado)
def importar_clientes_endpoint(
    body: ImportClientesRequest,
    usuario: UsuarioPerfil = Depends(require_capacidad("imports.importar")),
) -> ImportClientesResultado:
    resultado = importar_clientes_para_endpoint(drogueria_id=usuario.drogueria_id, clientes=body.clientes)
    return ImportClientesResultado(**resultado)
