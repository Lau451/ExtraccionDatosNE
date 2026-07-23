from pydantic import BaseModel


class PlanOut(BaseModel):
    id: str
    nombre: str
    max_usuarios: int | None
    max_documentos_mes: int | None
    almacenamiento_mb: int | None
    funcionalidades: dict
    activo: bool
