"""Fachada unidireccional de `services/terceros/` (design.md D5).

`services/presupuestacion/**` importa EXCLUSIVAMENTE este módulo — nunca un
`repository` o `service` interno de `services/terceros/*`. Este archivo no
define lógica propia: reexporta los modelos y funciones de servicio de cada
subdominio (identidad, catálogos, direcciones, contactos) que
`services/presupuestacion/` necesita. Las funciones reexportadas siguen
aceptando un `client: Client` explícito (RLS via `get_user_client` o
`get_service_client`, a elección del caller, igual que el resto de los
módulos de presupuestación) salvo las variantes `*_para_endpoint`, que ya
resuelven `get_service_client()` internamente.

`tests/terceros/test_dependencias.py` (Fase 2, D5) verifica con `ast` que
ningún `.py` bajo `services/terceros/` importa `services.presupuestacion` —
este módulo tampoco lo hace, la dependencia es de una sola dirección.
"""

from services.terceros.catalogos.models import (
    CondicionPagoCreate,
    CondicionPagoOut,
    CondicionPagoUpdate,
    FormaPagoCreate,
    FormaPagoOut,
    FormaPagoUpdate,
    SectorContactoCreate,
    SectorContactoOut,
    SectorContactoUpdate,
)
from services.terceros.catalogos.service import (
    actualizar_condicion_pago,
    actualizar_condicion_pago_para_endpoint,
    actualizar_forma_pago,
    actualizar_forma_pago_para_endpoint,
    actualizar_sector,
    actualizar_sector_para_endpoint,
    crear_condicion_pago,
    crear_condicion_pago_para_endpoint,
    crear_forma_pago,
    crear_forma_pago_para_endpoint,
    crear_sector,
    crear_sector_para_endpoint,
    listar_condiciones_pago,
    listar_formas_pago,
    listar_sectores,
    obtener_condicion_pago,
    obtener_forma_pago,
    obtener_sector,
)
from services.terceros.contactos.models import (
    TerceroContactoCreate,
    TerceroContactoOut,
    TerceroContactoUpdate,
)
from services.terceros.contactos.service import (
    actualizar_contacto,
    actualizar_contacto_para_endpoint,
    crear_contacto,
    crear_contacto_para_endpoint,
    listar_contactos,
    obtener_contacto,
)
from services.terceros.direcciones.models import (
    DireccionUsoCreate,
    DireccionUsoOut,
    TerceroDireccionCreate,
    TerceroDireccionOut,
    TerceroDireccionUpdate,
)
from services.terceros.direcciones.service import (
    actualizar_direccion,
    actualizar_direccion_para_endpoint,
    asignar_uso,
    asignar_uso_para_endpoint,
    crear_direccion,
    crear_direccion_para_endpoint,
    eliminar_direccion,
    eliminar_direccion_para_endpoint,
    eliminar_uso,
    eliminar_uso_para_endpoint,
    listar_direcciones,
    listar_usos,
    obtener_direccion,
)
from services.terceros.identidad.models import (
    ClienteRolCreate,
    ClienteRolOut,
    ClienteRolUpdate,
    ProveedorRolCreate,
    ProveedorRolOut,
    ProveedorRolUpdate,
    TerceroCreate,
    TerceroOut,
    TerceroUpdate,
)
from services.terceros.identidad.service import (
    actualizar_rol_cliente,
    actualizar_rol_cliente_para_endpoint,
    actualizar_rol_proveedor,
    actualizar_rol_proveedor_para_endpoint,
    actualizar_tercero,
    actualizar_tercero_para_endpoint,
    asignar_rol_cliente,
    asignar_rol_cliente_para_endpoint,
    asignar_rol_proveedor,
    asignar_rol_proveedor_para_endpoint,
    crear_tercero,
    crear_tercero_para_endpoint,
    listar_clientes_con_tercero,
    listar_proveedores_con_tercero,
    listar_terceros,
    obtener_cliente_con_tercero,
    obtener_proveedor_con_tercero,
    obtener_rol_cliente,
    obtener_rol_proveedor,
    obtener_tercero,
)

__all__ = [
    # identidad — modelos
    "TerceroCreate",
    "TerceroUpdate",
    "TerceroOut",
    "ClienteRolCreate",
    "ClienteRolUpdate",
    "ClienteRolOut",
    "ProveedorRolCreate",
    "ProveedorRolUpdate",
    "ProveedorRolOut",
    # identidad — tercero
    "crear_tercero",
    "crear_tercero_para_endpoint",
    "listar_terceros",
    "obtener_tercero",
    "actualizar_tercero",
    "actualizar_tercero_para_endpoint",
    # identidad — rol cliente
    "asignar_rol_cliente",
    "asignar_rol_cliente_para_endpoint",
    "obtener_rol_cliente",
    "actualizar_rol_cliente",
    "actualizar_rol_cliente_para_endpoint",
    "listar_clientes_con_tercero",
    "obtener_cliente_con_tercero",
    # identidad — rol proveedor
    "asignar_rol_proveedor",
    "asignar_rol_proveedor_para_endpoint",
    "obtener_rol_proveedor",
    "actualizar_rol_proveedor",
    "actualizar_rol_proveedor_para_endpoint",
    "listar_proveedores_con_tercero",
    "obtener_proveedor_con_tercero",
    # catalogos — modelos
    "SectorContactoCreate",
    "SectorContactoUpdate",
    "SectorContactoOut",
    "CondicionPagoCreate",
    "CondicionPagoUpdate",
    "CondicionPagoOut",
    "FormaPagoCreate",
    "FormaPagoUpdate",
    "FormaPagoOut",
    # catalogos — funciones
    "crear_sector",
    "crear_sector_para_endpoint",
    "listar_sectores",
    "obtener_sector",
    "actualizar_sector",
    "actualizar_sector_para_endpoint",
    "crear_condicion_pago",
    "crear_condicion_pago_para_endpoint",
    "listar_condiciones_pago",
    "obtener_condicion_pago",
    "actualizar_condicion_pago",
    "actualizar_condicion_pago_para_endpoint",
    "crear_forma_pago",
    "crear_forma_pago_para_endpoint",
    "listar_formas_pago",
    "obtener_forma_pago",
    "actualizar_forma_pago",
    "actualizar_forma_pago_para_endpoint",
    # direcciones — modelos
    "TerceroDireccionCreate",
    "TerceroDireccionUpdate",
    "TerceroDireccionOut",
    "DireccionUsoCreate",
    "DireccionUsoOut",
    # direcciones — funciones
    "crear_direccion",
    "crear_direccion_para_endpoint",
    "listar_direcciones",
    "obtener_direccion",
    "actualizar_direccion",
    "actualizar_direccion_para_endpoint",
    "eliminar_direccion",
    "eliminar_direccion_para_endpoint",
    "asignar_uso",
    "asignar_uso_para_endpoint",
    "listar_usos",
    "eliminar_uso",
    "eliminar_uso_para_endpoint",
    # contactos — modelos
    "TerceroContactoCreate",
    "TerceroContactoUpdate",
    "TerceroContactoOut",
    # contactos — funciones
    "crear_contacto",
    "crear_contacto_para_endpoint",
    "listar_contactos",
    "obtener_contacto",
    "actualizar_contacto",
    "actualizar_contacto_para_endpoint",
]
