from pathlib import Path

_PRESUPUESTACION_DIR = (
    Path(__file__).resolve().parent.parent.parent / "services" / "presupuestacion"
)

# Routers que SÍ pueden usar `get_service_client`, con su justificación. Cualquier otro
# router que lo use rompe el test; un router de esta lista que deje de usarlo también
# (lista obsoleta).
_ROUTERS_CON_SERVICE_CLIENT = {
    "oc_entregas/router.py": (
        "service client + filtro explícito `drogueria_id` en cada query de su repository "
        "(la RLS de DELETE en entregas_oc exige superadmin)"
    ),
    "oc_export/router.py": (
        "service client + filtro explícito `drogueria_id` en cada query de su repository "
        "(el UPDATE de exportación y la lectura del plan no pasan por la RLS de usuario)"
    ),
}


def _routers_que_usan_service_client() -> set[str]:
    return {
        router_path.relative_to(_PRESUPUESTACION_DIR).as_posix()
        for router_path in _PRESUPUESTACION_DIR.rglob("router.py")
        if "get_service_client" in router_path.read_text(encoding="utf-8")
    }


def test_service_client_no_se_importa_en_ningun_router():
    assert _PRESUPUESTACION_DIR.is_dir(), (
        f"{_PRESUPUESTACION_DIR} no existe -- si se movió/renombró el paquete "
        "presupuestacion, actualizá esta ruta. Sin este assert, rglob() sobre un path "
        "inexistente devuelve vacío en silencio y el test de abajo pasa vacuamente "
        "sin revisar ningún router (pasó exactamente esto tras el restructure a services/)."
    )

    usan = _routers_que_usan_service_client()
    no_permitidos = sorted(usan - _ROUTERS_CON_SERVICE_CLIENT.keys())
    assert not no_permitidos, (
        "service_role no debe usarse en routers de usuario, solo en jobs de sistema "
        "(imports/, pricing/service.py, automatizaciones/worker.py, eventos/scheduler.py) "
        "y en los routers de _ROUTERS_CON_SERVICE_CLIENT (con filtro `drogueria_id` "
        f"explícito en su repository): {no_permitidos}"
    )
    obsoletos = sorted(_ROUTERS_CON_SERVICE_CLIENT.keys() - usan)
    assert not obsoletos, (
        "_ROUTERS_CON_SERVICE_CLIENT lista routers que ya no usan get_service_client "
        f"(o que no existen): sacalos de la lista: {obsoletos}"
    )
