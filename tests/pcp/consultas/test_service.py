"""9.3-9.4, 9.6 (openspec/changes/gestor-pcp/tasks.md Fase 9) --
pcp-consultas-agrupadas: agrupar renglones de un mismo proveedor -- desde un
único PCP o varios -- en una sola consulta; cada renglón sigue trazando a su
PCP de origen; el PDF generado lista cada renglón agrupado e identifica al
proveedor como destinatario.

RED hasta que 9.7 cree services/pcp/consultas/service.py (9.3/9.4) y 9.5 cree
el renderer real (9.6).
"""

from io import BytesIO

import pytest
from pypdf import PdfReader

from services.pcp.consultas.models import AgruparConsultaCreate, SeleccionParaAgrupar
from services.pcp.consultas.service import (
    agrupar_renglones,
    generar_pdf_consulta,
    listar_renglones_consulta,
)
from services.pcp.gestion.models import PcpCreate
from services.pcp.gestion.service import crear_pcp
from services.pcp.renglones.models import PcpRenglonCreate
from services.pcp.renglones.service import crear_renglon, seleccionar_proveedores
from services.shared.exceptions import NotFoundError, ValidationError


def _crear_pcp_renglon_seleccionado(
    service_client, *, drogueria_id, presupuesto_id, item_proceso_id, usuario_id, proveedor_ids
):
    pcp = crear_pcp(
        service_client,
        drogueria_id=drogueria_id,
        body=PcpCreate(presupuesto_id=presupuesto_id),
        usuario_id=usuario_id,
    )
    renglon = crear_renglon(
        service_client,
        drogueria_id=drogueria_id,
        pcp_id=pcp["id"],
        body=PcpRenglonCreate(item_proceso_id=item_proceso_id),
        usuario_id=usuario_id,
    )
    seleccionar_proveedores(
        service_client,
        renglon_id=renglon["id"],
        drogueria_id=drogueria_id,
        proveedor_ids=proveedor_ids,
    )
    return pcp, renglon


# ---------------------------------------------------------------------------
# 9.3 -- agrupar renglones de un único PCP crea una sola consulta con todos
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_agrupar_renglones_de_un_solo_pcp_crea_una_consulta_con_todos(
    service_client,
    seed_drogueria,
    seed_usuario_sistema,
    seed_item_proceso_factory,
    seed_presupuesto_factory,
    seed_proveedor_pcp,
):
    item_a = seed_item_proceso_factory(numero_renglon=1)
    item_b = seed_item_proceso_factory(numero_renglon=2)
    item_c = seed_item_proceso_factory(numero_renglon=3)
    presupuesto = seed_presupuesto_factory()

    pcp = crear_pcp(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=PcpCreate(presupuesto_id=presupuesto["id"]),
        usuario_id=seed_usuario_sistema["id"],
    )
    renglones = []
    for item in (item_a, item_b, item_c):
        renglon = crear_renglon(
            service_client,
            drogueria_id=seed_drogueria["id"],
            pcp_id=pcp["id"],
            body=PcpRenglonCreate(item_proceso_id=item["id"]),
            usuario_id=seed_usuario_sistema["id"],
        )
        seleccionar_proveedores(
            service_client,
            renglon_id=renglon["id"],
            drogueria_id=seed_drogueria["id"],
            proveedor_ids=[seed_proveedor_pcp["id"]],
        )
        renglones.append(renglon)

    try:
        consultas = agrupar_renglones(
            service_client,
            drogueria_id=seed_drogueria["id"],
            body=AgruparConsultaCreate(
                selecciones=[
                    SeleccionParaAgrupar(pcp_renglon_id=r["id"], proveedor_id=seed_proveedor_pcp["id"])
                    for r in renglones
                ]
            ),
            usuario_id=seed_usuario_sistema["id"],
        )

        # Un único proveedor en la request -> una única consulta (nunca una
        # por renglón, nunca una que descarte renglones).
        assert len(consultas) == 1
        consulta = consultas[0]
        assert consulta["proveedor_id"] == seed_proveedor_pcp["id"]
        assert consulta["estado"] == "borrador"
        assert consulta["fecha_envio"] is None

        filas = listar_renglones_consulta(
            service_client, consulta_id=consulta["id"], drogueria_id=seed_drogueria["id"]
        )
        assert {f["pcp_renglon_id"] for f in filas} == {r["id"] for r in renglones}
    finally:
        service_client.table("pcp").delete().eq("id", pcp["id"]).execute()
        service_client.table("pcp_consultas").delete().eq(
            "proveedor_id", seed_proveedor_pcp["id"]
        ).execute()


# ---------------------------------------------------------------------------
# 9.4 -- agrupar renglones de dos PCPs abiertos crea una sola consulta; cada
# renglón sigue trazando a su PCP de origen
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_agrupar_renglones_de_dos_pcp_abiertos_crea_una_sola_consulta_y_conserva_trazabilidad(
    service_client,
    seed_drogueria,
    seed_usuario_sistema,
    seed_item_proceso_factory,
    seed_presupuesto_factory,
    seed_proveedor_pcp,
):
    item_1 = seed_item_proceso_factory(numero_renglon=1)
    item_2 = seed_item_proceso_factory(numero_renglon=2)
    presupuesto_1 = seed_presupuesto_factory()
    presupuesto_2 = seed_presupuesto_factory()

    pcp_1, renglon_1 = _crear_pcp_renglon_seleccionado(
        service_client,
        drogueria_id=seed_drogueria["id"],
        presupuesto_id=presupuesto_1["id"],
        item_proceso_id=item_1["id"],
        usuario_id=seed_usuario_sistema["id"],
        proveedor_ids=[seed_proveedor_pcp["id"]],
    )
    pcp_2, renglon_2 = _crear_pcp_renglon_seleccionado(
        service_client,
        drogueria_id=seed_drogueria["id"],
        presupuesto_id=presupuesto_2["id"],
        item_proceso_id=item_2["id"],
        usuario_id=seed_usuario_sistema["id"],
        proveedor_ids=[seed_proveedor_pcp["id"]],
    )
    assert pcp_1["id"] != pcp_2["id"]

    try:
        consultas = agrupar_renglones(
            service_client,
            drogueria_id=seed_drogueria["id"],
            body=AgruparConsultaCreate(
                selecciones=[
                    SeleccionParaAgrupar(
                        pcp_renglon_id=renglon_1["id"], proveedor_id=seed_proveedor_pcp["id"]
                    ),
                    SeleccionParaAgrupar(
                        pcp_renglon_id=renglon_2["id"], proveedor_id=seed_proveedor_pcp["id"]
                    ),
                ]
            ),
            usuario_id=seed_usuario_sistema["id"],
        )

        assert len(consultas) == 1
        consulta = consultas[0]

        filas = listar_renglones_consulta(
            service_client, consulta_id=consulta["id"], drogueria_id=seed_drogueria["id"]
        )
        assert {f["pcp_renglon_id"] for f in filas} == {renglon_1["id"], renglon_2["id"]}

        # Cada renglón sigue trazando a su PCP de origen -- distinto por
        # renglón, nunca se pierde ni se fusiona en la agrupación.
        renglon_1_en_bd = (
            service_client.table("pcp_renglones")
            .select("pcp_id")
            .eq("id", renglon_1["id"])
            .execute()
            .data[0]
        )
        renglon_2_en_bd = (
            service_client.table("pcp_renglones")
            .select("pcp_id")
            .eq("id", renglon_2["id"])
            .execute()
            .data[0]
        )
        assert renglon_1_en_bd["pcp_id"] == pcp_1["id"]
        assert renglon_2_en_bd["pcp_id"] == pcp_2["id"]
    finally:
        service_client.table("pcp").delete().eq("id", pcp_1["id"]).execute()
        service_client.table("pcp").delete().eq("id", pcp_2["id"]).execute()
        service_client.table("pcp_consultas").delete().eq(
            "proveedor_id", seed_proveedor_pcp["id"]
        ).execute()


# ---------------------------------------------------------------------------
# Agrupamiento por proveedor: dos proveedores en una sola request nunca se
# resuelven descartando uno -- se crea una consulta por proveedor distinto.
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_agrupar_renglones_de_dos_proveedores_distintos_crea_una_consulta_por_proveedor(
    service_client,
    seed_drogueria,
    seed_usuario_sistema,
    seed_item_proceso_factory,
    seed_presupuesto_factory,
    seed_proveedores_pcp_factory,
):
    proveedor_p, proveedor_q = seed_proveedores_pcp_factory(2)
    item_p = seed_item_proceso_factory(numero_renglon=1)
    item_q = seed_item_proceso_factory(numero_renglon=2)
    presupuesto = seed_presupuesto_factory()

    pcp = crear_pcp(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=PcpCreate(presupuesto_id=presupuesto["id"]),
        usuario_id=seed_usuario_sistema["id"],
    )
    renglon_p = crear_renglon(
        service_client,
        drogueria_id=seed_drogueria["id"],
        pcp_id=pcp["id"],
        body=PcpRenglonCreate(item_proceso_id=item_p["id"]),
        usuario_id=seed_usuario_sistema["id"],
    )
    seleccionar_proveedores(
        service_client,
        renglon_id=renglon_p["id"],
        drogueria_id=seed_drogueria["id"],
        proveedor_ids=[proveedor_p["id"]],
    )
    renglon_q = crear_renglon(
        service_client,
        drogueria_id=seed_drogueria["id"],
        pcp_id=pcp["id"],
        body=PcpRenglonCreate(item_proceso_id=item_q["id"]),
        usuario_id=seed_usuario_sistema["id"],
    )
    seleccionar_proveedores(
        service_client,
        renglon_id=renglon_q["id"],
        drogueria_id=seed_drogueria["id"],
        proveedor_ids=[proveedor_q["id"]],
    )

    try:
        consultas = agrupar_renglones(
            service_client,
            drogueria_id=seed_drogueria["id"],
            body=AgruparConsultaCreate(
                selecciones=[
                    SeleccionParaAgrupar(pcp_renglon_id=renglon_p["id"], proveedor_id=proveedor_p["id"]),
                    SeleccionParaAgrupar(pcp_renglon_id=renglon_q["id"], proveedor_id=proveedor_q["id"]),
                ]
            ),
            usuario_id=seed_usuario_sistema["id"],
        )

        assert len(consultas) == 2
        proveedores_en_consultas = {c["proveedor_id"] for c in consultas}
        assert proveedores_en_consultas == {proveedor_p["id"], proveedor_q["id"]}

        for consulta in consultas:
            filas = listar_renglones_consulta(
                service_client, consulta_id=consulta["id"], drogueria_id=seed_drogueria["id"]
            )
            assert len(filas) == 1
    finally:
        service_client.table("pcp").delete().eq("id", pcp["id"]).execute()
        service_client.table("pcp_consultas").delete().eq(
            "proveedor_id", proveedor_p["id"]
        ).execute()
        service_client.table("pcp_consultas").delete().eq(
            "proveedor_id", proveedor_q["id"]
        ).execute()


@pytest.mark.integration
def test_agrupar_renglones_sin_selecciones_lanza_validation_error(
    service_client, seed_drogueria, seed_usuario_sistema
):
    with pytest.raises(ValidationError):
        agrupar_renglones(
            service_client,
            drogueria_id=seed_drogueria["id"],
            body=AgruparConsultaCreate(selecciones=[]),
            usuario_id=seed_usuario_sistema["id"],
        )


@pytest.mark.integration
def test_agrupar_renglon_no_asignado_al_proveedor_lanza_not_found_error(
    service_client,
    seed_drogueria,
    seed_usuario_sistema,
    seed_item_proceso,
    seed_presupuesto_factory,
    seed_proveedor_pcp,
):
    """Un renglón nunca seleccionado para negociar con el proveedor P (sin
    fila pcp_renglon_resultados para ese par) no puede agruparse en una
    consulta para P -- la única prueba de "asignado" en el esquema es esa
    fila (D4)."""
    presupuesto = seed_presupuesto_factory()
    pcp = crear_pcp(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=PcpCreate(presupuesto_id=presupuesto["id"]),
        usuario_id=seed_usuario_sistema["id"],
    )
    renglon = crear_renglon(
        service_client,
        drogueria_id=seed_drogueria["id"],
        pcp_id=pcp["id"],
        body=PcpRenglonCreate(item_proceso_id=seed_item_proceso["id"]),
        usuario_id=seed_usuario_sistema["id"],
    )
    # Deliberadamente NO se llama seleccionar_proveedores.

    try:
        with pytest.raises(NotFoundError):
            agrupar_renglones(
                service_client,
                drogueria_id=seed_drogueria["id"],
                body=AgruparConsultaCreate(
                    selecciones=[
                        SeleccionParaAgrupar(
                            pcp_renglon_id=renglon["id"], proveedor_id=seed_proveedor_pcp["id"]
                        )
                    ]
                ),
                usuario_id=seed_usuario_sistema["id"],
            )

        en_bd = (
            service_client.table("pcp_consultas")
            .select("id")
            .eq("proveedor_id", seed_proveedor_pcp["id"])
            .execute()
            .data
        )
        assert en_bd == []
    finally:
        service_client.table("pcp").delete().eq("id", pcp["id"]).execute()


# ---------------------------------------------------------------------------
# 9.6 -- el PDF generado lista cada renglón agrupado e identifica al
# proveedor como destinatario
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_generar_pdf_consulta_lista_cada_renglon_agrupado_e_identifica_al_proveedor(
    service_client,
    seed_drogueria,
    seed_producto,
    seed_usuario_sistema,
    seed_item_proceso,
    seed_presupuesto_factory,
    seed_proveedor_pcp,
):
    presupuesto = seed_presupuesto_factory()
    pcp, renglon = _crear_pcp_renglon_seleccionado(
        service_client,
        drogueria_id=seed_drogueria["id"],
        presupuesto_id=presupuesto["id"],
        item_proceso_id=seed_item_proceso["id"],
        usuario_id=seed_usuario_sistema["id"],
        proveedor_ids=[seed_proveedor_pcp["id"]],
    )

    try:
        consultas = agrupar_renglones(
            service_client,
            drogueria_id=seed_drogueria["id"],
            body=AgruparConsultaCreate(
                selecciones=[
                    SeleccionParaAgrupar(
                        pcp_renglon_id=renglon["id"], proveedor_id=seed_proveedor_pcp["id"]
                    )
                ]
            ),
            usuario_id=seed_usuario_sistema["id"],
        )
        consulta = consultas[0]

        pdf_bytes = generar_pdf_consulta(
            service_client, consulta_id=consulta["id"], drogueria_id=seed_drogueria["id"]
        )

        assert pdf_bytes[:4] == b"%PDF"

        lector = PdfReader(BytesIO(pdf_bytes))
        texto = "\n".join(pagina.extract_text() or "" for pagina in lector.pages)

        # Lista el renglón agrupado (por nombre de producto, D2/D9).
        assert seed_producto["nombre"] in texto
        # Identifica al proveedor P como destinatario (razón social de
        # seed_proveedor_pcp, tests/pcp/conftest.py).
        assert "Proveedor PCP Test" in texto
    finally:
        service_client.table("pcp").delete().eq("id", pcp["id"]).execute()
        service_client.table("pcp_consultas").delete().eq(
            "proveedor_id", seed_proveedor_pcp["id"]
        ).execute()
