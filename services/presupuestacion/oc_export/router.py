from fastapi import APIRouter, Depends

from services.presupuestacion.core.auth import UsuarioPerfil, require_capacidad
from services.presupuestacion.core.database import get_service_client
from services.presupuestacion.oc_export.models import ResultadoExportacion
from services.presupuestacion.oc_export.service import exportar_orden_compra
from services.shared.config import Settings, get_settings

router = APIRouter()


@router.post(
    "/ordenes-compra/{orden_compra_id}/exportar-progress",
    response_model=ResultadoExportacion,
)
def exportar_progress_endpoint(
    orden_compra_id: str,
    usuario: UsuarioPerfil = Depends(require_capacidad("oc_export.exportar")),
    settings: Settings = Depends(get_settings),
) -> ResultadoExportacion:
    # SERVICE client con filtro explícito por drogueria_id (ver oc_export/repository.py).
    return exportar_orden_compra(
        get_service_client(),
        orden_compra_id=orden_compra_id,
        drogueria_id=usuario.drogueria_id,
        usuario_id=usuario.id,
        settings=settings,
    )
