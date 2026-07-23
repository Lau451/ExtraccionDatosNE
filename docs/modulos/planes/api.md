# API pública — Planes

Firmas verificadas contra el código real en esta sesión.

## `planes/models.py`

```python
class PlanOut(BaseModel):
    id: str
    nombre: str
    max_usuarios: int | None
    max_documentos_mes: int | None
    almacenamiento_mb: int | None
    funcionalidades: dict
    activo: bool
# models.py:4-11
```

No hay `PlanCreate` ni `PlanUpdate` — solo el modelo de salida, consistente con que el
módulo no expone escritura (ver [`decisiones.md`](./decisiones.md)).

## `planes/router.py`

```python
router = APIRouter()
# router.py:8

@router.get("/planes", response_model=list[PlanOut])
def listar_planes_endpoint(
    usuario: UsuarioPerfil = Depends(get_current_user),
    user_client: Client = Depends(get_user_client),
) -> list[PlanOut]: ...
# router.py:11-18
# SELECT * FROM planes WHERE activo=True ORDER BY nombre, con user_client (RLS planes_sel).
```

| Método | Path | Request | Response | Roles requeridos | Cliente Supabase | Archivo |
|---|---|---|---|---|---|---|
| GET | `/planes` | — | `list[PlanOut]` | cualquier autenticado | `user_client` | `router.py:11-18` |

No hay `repository.py` ni `service.py` en este módulo — el router consulta la tabla
directo, sin capas intermedias (mismo patrón que los `GET` de
[`../droguerias/`](../droguerias/), ver D-DROGUERIAS-004 en
[`../droguerias/decisiones.md`](../droguerias/decisiones.md)).

No hay excepciones de dominio propias de este módulo: `router.py` no levanta ningún
`DomainError` de `core/exceptions.py` en ningún punto.
