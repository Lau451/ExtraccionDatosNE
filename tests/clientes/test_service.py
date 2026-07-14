import secrets

import pytest

from services.presupuestacion.clientes.models import (
    ClienteContactoCreate,
    ClienteContactoUpdate,
    ClienteCreate,
    ClienteFormatoDocumentoUpsert,
    ClienteObservacionCreate,
    ClienteUpdate,
)
from services.presupuestacion.clientes.service import (
    actualizar_cliente,
    actualizar_contacto,
    crear_cliente,
    crear_contacto,
    crear_observacion,
    eliminar_cliente,
    listar_clientes,
    listar_contactos,
    listar_formato_documentos,
    listar_observaciones,
    obtener_cliente,
    upsert_formato_documento,
)
from services.presupuestacion.core.exceptions import NotFoundError, ValidationError


@pytest.mark.integration
def test_upsert_formato_documento_crea_si_no_existe(
    service_client, seed_drogueria, seed_cliente_factory, seed_usuario_sistema
):
    cliente = seed_cliente_factory()

    resultado = upsert_formato_documento(
        service_client,
        cliente_id=cliente["id"],
        drogueria_id=seed_drogueria["id"],
        body=ClienteFormatoDocumentoUpsert(
            doc_type="licitacion",
            instrucciones_prompt="Los renglones vienen numerados con letras, no números.",
        ),
        usuario_id=seed_usuario_sistema["id"],
    )

    assert resultado["doc_type"] == "licitacion"
    assert resultado["instrucciones_prompt"] == (
        "Los renglones vienen numerados con letras, no números."
    )
    assert resultado["actualizado_por"] == seed_usuario_sistema["id"]


@pytest.mark.integration
def test_upsert_formato_documento_actualiza_si_ya_existe(
    service_client, seed_drogueria, seed_cliente_factory, seed_usuario_sistema
):
    cliente = seed_cliente_factory()
    primero = upsert_formato_documento(
        service_client,
        cliente_id=cliente["id"],
        drogueria_id=seed_drogueria["id"],
        body=ClienteFormatoDocumentoUpsert(doc_type="licitacion", instrucciones_prompt="v1"),
        usuario_id=seed_usuario_sistema["id"],
    )

    segundo = upsert_formato_documento(
        service_client,
        cliente_id=cliente["id"],
        drogueria_id=seed_drogueria["id"],
        body=ClienteFormatoDocumentoUpsert(doc_type="licitacion", instrucciones_prompt="v2"),
        usuario_id=seed_usuario_sistema["id"],
    )

    assert segundo["id"] == primero["id"]
    assert segundo["instrucciones_prompt"] == "v2"

    todos = listar_formato_documentos(service_client, cliente_id=cliente["id"])
    assert len(todos) == 1


@pytest.mark.integration
def test_upsert_formato_documento_no_pisa_otro_doc_type(
    service_client, seed_drogueria, seed_cliente_factory, seed_usuario_sistema
):
    cliente = seed_cliente_factory()
    upsert_formato_documento(
        service_client,
        cliente_id=cliente["id"],
        drogueria_id=seed_drogueria["id"],
        body=ClienteFormatoDocumentoUpsert(doc_type="licitacion", instrucciones_prompt="lic"),
        usuario_id=seed_usuario_sistema["id"],
    )
    upsert_formato_documento(
        service_client,
        cliente_id=cliente["id"],
        drogueria_id=seed_drogueria["id"],
        body=ClienteFormatoDocumentoUpsert(doc_type="comparativa", instrucciones_prompt="comp"),
        usuario_id=seed_usuario_sistema["id"],
    )

    todos = listar_formato_documentos(service_client, cliente_id=cliente["id"])
    assert len(todos) == 2
    por_tipo = {f["doc_type"]: f["instrucciones_prompt"] for f in todos}
    assert por_tipo == {"licitacion": "lic", "comparativa": "comp"}


@pytest.mark.integration
def test_upsert_formato_documento_cliente_inexistente(
    service_client, seed_drogueria, seed_usuario_sistema
):
    with pytest.raises(NotFoundError):
        upsert_formato_documento(
            service_client,
            cliente_id="00000000-0000-0000-0000-000000000000",
            drogueria_id=seed_drogueria["id"],
            body=ClienteFormatoDocumentoUpsert(doc_type="licitacion"),
            usuario_id=seed_usuario_sistema["id"],
        )


@pytest.mark.integration
def test_upsert_formato_documento_cliente_de_otra_drogueria_falla(
    service_client, seed_drogueria, seed_cliente_factory, seed_usuario_sistema
):
    cliente = seed_cliente_factory()
    otra_drogueria = service_client.table("droguerias").insert(
        {
            "nombre": "Otra Droguería",
            "razon_social": "Otra Droguería SA",
            "cuit": f"20-{secrets.randbelow(99_999_999):08d}-9",
            "ciudad": "Rosario",
            "provincia": "Santa Fe",
            "contacto_email": "otra-clientes@seed.local",
            "contacto_telefono": "0000000000",
        }
    ).execute().data[0]

    try:
        with pytest.raises(ValidationError):
            upsert_formato_documento(
                service_client,
                cliente_id=cliente["id"],
                drogueria_id=otra_drogueria["id"],
                body=ClienteFormatoDocumentoUpsert(doc_type="licitacion"),
                usuario_id=seed_usuario_sistema["id"],
            )
    finally:
        service_client.table("droguerias").delete().eq("id", otra_drogueria["id"]).execute()


@pytest.mark.integration
def test_crear_observacion_y_listar(
    service_client, seed_drogueria, seed_cliente_factory, seed_usuario_sistema
):
    cliente = seed_cliente_factory()

    creada = crear_observacion(
        service_client,
        cliente_id=cliente["id"],
        drogueria_id=seed_drogueria["id"],
        body=ClienteObservacionCreate(categoria="pago", observacion="Paga siempre con demora."),
        usuario_id=seed_usuario_sistema["id"],
    )

    assert creada["categoria"] == "pago"
    assert creada["creado_por"] == seed_usuario_sistema["id"]

    observaciones = listar_observaciones(service_client, cliente_id=cliente["id"])
    assert len(observaciones) == 1
    assert observaciones[0]["id"] == creada["id"]


@pytest.mark.integration
def test_crear_observacion_cliente_inexistente(
    service_client, seed_drogueria, seed_usuario_sistema
):
    with pytest.raises(NotFoundError):
        crear_observacion(
            service_client,
            cliente_id="00000000-0000-0000-0000-000000000000",
            drogueria_id=seed_drogueria["id"],
            body=ClienteObservacionCreate(observacion="x"),
            usuario_id=seed_usuario_sistema["id"],
        )


# ---------------------------------------------------------------------------
# CRUD básico de clientes
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_crear_cliente(service_client, seed_drogueria, seed_usuario_sistema):
    resultado = crear_cliente(
        service_client,
        drogueria_id=seed_drogueria["id"],
        body=ClienteCreate(nombre="Hospital Nuevo", tipo="hospital", ciudad="Rosario"),
        usuario_id=seed_usuario_sistema["id"],
    )

    assert resultado["nombre"] == "Hospital Nuevo"
    assert resultado["activo"] is True

    service_client.table("clientes").delete().eq("id", resultado["id"]).execute()


@pytest.mark.integration
def test_listar_clientes_filtra_por_drogueria_y_activo(
    service_client, seed_drogueria, seed_cliente_factory
):
    activo = seed_cliente_factory(nombre="Activo")
    inactivo = seed_cliente_factory(nombre="Inactivo", activo=False)

    todos = listar_clientes(service_client, drogueria_id=seed_drogueria["id"])
    assert {c["id"] for c in todos} == {activo["id"], inactivo["id"]}

    solo_activos = listar_clientes(service_client, drogueria_id=seed_drogueria["id"], activo=True)
    assert {c["id"] for c in solo_activos} == {activo["id"]}


@pytest.mark.integration
def test_obtener_cliente_de_otra_drogueria_lanza_not_found(
    service_client, seed_drogueria, seed_cliente_factory
):
    cliente = seed_cliente_factory()
    with pytest.raises(NotFoundError):
        obtener_cliente(service_client, cliente_id=cliente["id"], drogueria_id="otra-drogueria")


@pytest.mark.integration
def test_actualizar_cliente_solo_pisa_campos_enviados(
    service_client, seed_drogueria, seed_usuario_sistema, seed_cliente_factory
):
    cliente = seed_cliente_factory(nombre="Original", ciudad="Rosario")

    resultado = actualizar_cliente(
        service_client,
        cliente_id=cliente["id"],
        drogueria_id=seed_drogueria["id"],
        body=ClienteUpdate(ciudad="Santa Fe"),
        usuario_id=seed_usuario_sistema["id"],
    )

    assert resultado["ciudad"] == "Santa Fe"
    assert resultado["nombre"] == "Original"


@pytest.mark.integration
def test_eliminar_cliente_soft_delete(
    service_client, seed_drogueria, seed_usuario_sistema, seed_cliente_factory
):
    cliente = seed_cliente_factory()

    eliminar_cliente(
        service_client,
        cliente_id=cliente["id"],
        drogueria_id=seed_drogueria["id"],
        usuario_id=seed_usuario_sistema["id"],
    )

    with pytest.raises(NotFoundError):
        obtener_cliente(service_client, cliente_id=cliente["id"], drogueria_id=seed_drogueria["id"])

    fila = (
        service_client.table("clientes").select("deleted_at,deleted_by,activo")
        .eq("id", cliente["id"]).execute().data[0]
    )
    assert fila["deleted_at"] is not None
    assert fila["deleted_by"] == seed_usuario_sistema["id"]
    assert fila["activo"] is False


# ---------------------------------------------------------------------------
# contactos
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_crear_y_listar_contactos(service_client, seed_drogueria, seed_cliente_factory):
    cliente = seed_cliente_factory()

    creado = crear_contacto(
        service_client,
        cliente_id=cliente["id"],
        drogueria_id=seed_drogueria["id"],
        body=ClienteContactoCreate(nombre="Juan Pérez", cargo="Compras", es_principal=True),
    )

    assert creado["nombre"] == "Juan Pérez"
    assert creado["es_principal"] is True

    contactos = listar_contactos(service_client, cliente_id=cliente["id"])
    assert len(contactos) == 1
    assert contactos[0]["id"] == creado["id"]


@pytest.mark.integration
def test_actualizar_contacto_de_otro_cliente_lanza_not_found(
    service_client, seed_drogueria, seed_cliente_factory
):
    cliente_a = seed_cliente_factory(nombre="A")
    cliente_b = seed_cliente_factory(nombre="B")
    contacto = crear_contacto(
        service_client,
        cliente_id=cliente_a["id"],
        drogueria_id=seed_drogueria["id"],
        body=ClienteContactoCreate(nombre="Contacto A"),
    )

    with pytest.raises(NotFoundError):
        actualizar_contacto(
            service_client,
            cliente_id=cliente_b["id"],
            contacto_id=contacto["id"],
            body=ClienteContactoUpdate(nombre="Hackeado"),
        )


@pytest.mark.integration
def test_actualizar_contacto_solo_pisa_campos_enviados(
    service_client, seed_drogueria, seed_cliente_factory
):
    cliente = seed_cliente_factory()
    contacto = crear_contacto(
        service_client,
        cliente_id=cliente["id"],
        drogueria_id=seed_drogueria["id"],
        body=ClienteContactoCreate(nombre="Juan Pérez", email="juan@test.com"),
    )

    resultado = actualizar_contacto(
        service_client,
        cliente_id=cliente["id"],
        contacto_id=contacto["id"],
        body=ClienteContactoUpdate(telefono="123456"),
    )

    assert resultado["telefono"] == "123456"
    assert resultado["email"] == "juan@test.com"
    assert resultado["nombre"] == "Juan Pérez"
