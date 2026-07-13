import secrets

import pytest

from presupuestacion.clientes.models import ClienteFormatoDocumentoUpsert, ClienteObservacionCreate
from presupuestacion.clientes.service import (
    crear_observacion,
    listar_formato_documentos,
    listar_observaciones,
    upsert_formato_documento,
)
from presupuestacion.core.exceptions import NotFoundError, ValidationError


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
