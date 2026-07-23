import secrets
import uuid

import pytest

from pydantic import ValidationError as PydanticValidationError

from services.presupuestacion.core.exceptions import ConflictError, NotFoundError
from services.presupuestacion.droguerias.models import DrogueriaCreate, DrogueriaUpdate
from services.presupuestacion.droguerias.service import (
    actualizar_drogueria,
    crear_drogueria,
    eliminar_drogueria,
)


def _body(**overrides) -> DrogueriaCreate:
    base = {
        "nombre": "Droguería de test",
        "razon_social": "Droguería de test SA",
        "cuit": f"20-{secrets.randbelow(99_999_999):08d}-9",
        "ciudad": "Rosario",
        "provincia": "Santa Fe",
        "contacto_email": f"drog-{uuid.uuid4()}@seed.local",
        "contacto_telefono": "0000000000",
    }
    base.update(overrides)
    return DrogueriaCreate(**base)


@pytest.mark.integration
def test_crear_drogueria(service_client, limpiar_drogueria_creada):
    resultado = crear_drogueria(service_client, body=_body(nombre="Nueva SA"))
    limpiar_drogueria_creada.append(resultado["id"])

    assert resultado["nombre"] == "Nueva SA"
    assert resultado["activa"] is True
    assert resultado["plan_id"] is None


@pytest.mark.integration
def test_actualizar_drogueria_solo_toca_campos_provistos(service_client, limpiar_drogueria_creada):
    creada = crear_drogueria(service_client, body=_body())
    limpiar_drogueria_creada.append(creada["id"])

    resultado = actualizar_drogueria(
        service_client, drogueria_id=creada["id"], body=DrogueriaUpdate(activa=False)
    )

    assert resultado["activa"] is False
    assert resultado["nombre"] == creada["nombre"]


@pytest.mark.integration
def test_actualizar_drogueria_asigna_plan(service_client, limpiar_drogueria_creada):
    creada = crear_drogueria(service_client, body=_body())
    limpiar_drogueria_creada.append(creada["id"])

    plan = service_client.table("planes").insert({"nombre": "Plan de test"}).execute().data[0]
    try:
        resultado = actualizar_drogueria(
            service_client, drogueria_id=creada["id"], body=DrogueriaUpdate(plan_id=plan["id"])
        )
        assert resultado["plan_id"] == plan["id"]
    finally:
        # borrar la droguería ANTES que el plan (FK) — el teardown de
        # limpiar_drogueria_creada corre después y es un no-op si ya no existe.
        service_client.table("droguerias").delete().eq("id", creada["id"]).execute()
        service_client.table("planes").delete().eq("id", plan["id"]).execute()


@pytest.mark.integration
def test_actualizar_drogueria_inexistente_lanza_not_found(service_client):
    with pytest.raises(NotFoundError):
        actualizar_drogueria(
            service_client,
            drogueria_id="00000000-0000-0000-0000-000000000000",
            body=DrogueriaUpdate(nombre="X"),
        )


def test_crear_drogueria_rechaza_cuit_con_formato_invalido():
    with pytest.raises(PydanticValidationError):
        _body(cuit="20999999991")


def test_actualizar_drogueria_rechaza_cuit_con_formato_invalido():
    with pytest.raises(PydanticValidationError):
        DrogueriaUpdate(cuit="no-es-un-cuit")


@pytest.mark.integration
def test_eliminar_drogueria(service_client):
    creada = crear_drogueria(service_client, body=_body())

    eliminar_drogueria(service_client, drogueria_id=creada["id"])

    resultado = service_client.table("droguerias").select("id").eq("id", creada["id"]).execute()
    assert resultado.data == []


@pytest.mark.integration
def test_eliminar_drogueria_inexistente_lanza_not_found(service_client):
    with pytest.raises(NotFoundError):
        eliminar_drogueria(service_client, drogueria_id="00000000-0000-0000-0000-000000000000")


@pytest.mark.integration
def test_eliminar_drogueria_con_usuarios_lanza_conflict(service_client, limpiar_drogueria_creada):
    creada = crear_drogueria(service_client, body=_body())
    limpiar_drogueria_creada.append(creada["id"])

    auth_response = service_client.auth.admin.create_user(
        {"email": f"{uuid.uuid4()}@seed.local", "password": secrets.token_urlsafe(24), "email_confirm": True}
    )
    uid = auth_response.user.id
    service_client.table("usuarios").insert(
        {"id": uid, "drogueria_id": creada["id"], "rol": "admin", "nombre": "FK", "apellido": "Test"}
    ).execute()

    try:
        with pytest.raises(ConflictError):
            eliminar_drogueria(service_client, drogueria_id=creada["id"])
    finally:
        service_client.table("usuarios").delete().eq("id", uid).execute()
        service_client.auth.admin.delete_user(uid)
