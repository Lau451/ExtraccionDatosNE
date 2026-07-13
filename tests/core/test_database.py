from pathlib import Path

_PRESUPUESTACION_DIR = Path(__file__).resolve().parent.parent.parent / "presupuestacion"


def test_service_client_no_se_importa_en_ningun_router():
    routers_con_problema = [
        router_path
        for router_path in _PRESUPUESTACION_DIR.rglob("router.py")
        if "get_service_client" in router_path.read_text(encoding="utf-8")
    ]
    assert not routers_con_problema, (
        "service_role no debe usarse en routers de usuario, solo en jobs de sistema "
        f"(imports/, pricing/service.py, automatizaciones/worker.py, eventos/scheduler.py): "
        f"{routers_con_problema}"
    )
