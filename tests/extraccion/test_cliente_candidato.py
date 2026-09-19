from unittest.mock import MagicMock

import pytest

from services.presupuestacion.core.texto import normalizar_descripcion
from services.presupuestacion.extraccion import repository as repo
from services.presupuestacion.extraccion import service

# =============================================================================
# 3.3 -- _normalizar_cuit (pura) + clave de alias (no-regresión de
# core/texto.py::normalizar_descripcion, que este cambio NO modifica).
# =============================================================================


@pytest.mark.parametrize(
    "cuit_crudo",
    ["30-12345678-9", "30123456789", "30.123.456.78 9"],
)
def test_normalizar_cuit_variantes_dan_los_mismos_11_digitos(cuit_crudo):
    assert service._normalizar_cuit(cuit_crudo) == "30123456789"


def test_normalizar_cuit_menos_de_11_digitos_devuelve_none():
    assert service._normalizar_cuit("1234") is None


def test_normalizar_cuit_none_devuelve_none():
    assert service._normalizar_cuit(None) is None


def test_normalizar_cuit_vacio_devuelve_none():
    assert service._normalizar_cuit("") is None


def test_normalizar_descripcion_produce_la_clave_de_alias_esperada():
    # Test de no-regresión (D3.1): services/presupuestacion/core/texto.py no se
    # toca en este cambio -- esto confirma que sigue produciendo exactamente la
    # clave que oc_cliente_alias necesita.
    #
    # NOTA (deviation from design.md § D3.1): el ejemplo documentado ahí dice
    # `normalizar_descripcion("Hospital Público Ñandú S.A. - Sede Nº2") ==
    # "HOSPITAL PUBLICO NANDU S A SEDE N 2"`, pero la función real (verificada
    # en vivo, sin tocarla) produce "...SEDE NO2": NFKD descompone "º" (U+00BA,
    # masculine ordinal indicator) a la letra "o" (no a un espacio), que
    # `[^\w\s]` no toca porque "o" SÍ es `\w`. El texto del diseño describe mal
    # ese caso puntual; el test de no-regresión abajo confirma el
    # comportamiento REAL, que es lo que le importa a D3.1 (colapsar
    # variantes), no la prosa del documento.
    assert (
        normalizar_descripcion("Hospital Público Ñandú S.A. - Sede Nº2")
        == "HOSPITAL PUBLICO NANDU S A SEDE NO2"
    )


def test_normalizar_descripcion_dos_variantes_tipograficas_colapsan_a_la_misma_clave():
    variante_1 = normalizar_descripcion("Clínica San Roque")
    variante_2 = normalizar_descripcion("  clinica   SAN roque  ")
    assert variante_1 == variante_2 == "CLINICA SAN ROQUE"


# =============================================================================
# Helpers in-memory (sin DB) para armar filas con la forma que devuelven los
# repository nuevos (embeds de PostgREST) -- ver design.md § Interfaces.
# =============================================================================


def _alias_row(
    *,
    cliente_id: str = "cliente-1",
    veces_confirmado: int = 1,
    tipo: str = "hospital",
    activo: bool = True,
    razon_social: str = "Hospital San Roque",
    codigo_interno: str | None = "C-1",
    cuit: str | None = "30712345679",
    cuit_no_exclusivo: bool = False,
) -> dict:
    return {
        "id": "alias-1",
        "cliente_id": cliente_id,
        "veces_confirmado": veces_confirmado,
        "clientes": {
            "id": cliente_id,
            "tipo": tipo,
            "activo": activo,
            "terceros": {
                "razon_social": razon_social,
                "codigo_interno": codigo_interno,
                "cuit": cuit,
                "cuit_no_exclusivo": cuit_no_exclusivo,
            },
        },
    }


def _cuit_row(
    *,
    cliente_id: str = "cliente-2",
    tipo: str = "hospital",
    activo: bool = True,
    razon_social: str = "Clínica del Sol",
    codigo_interno: str | None = None,
    cuit: str = "30555555553",
    cuit_no_exclusivo: bool = False,
    sin_cliente: bool = False,
) -> dict:
    return {
        "id": "tercero-x",
        "razon_social": razon_social,
        "codigo_interno": codigo_interno,
        "cuit": cuit,
        "cuit_no_exclusivo": cuit_no_exclusivo,
        "clientes": None if sin_cliente else {"id": cliente_id, "tipo": tipo, "activo": activo},
    }


# =============================================================================
# 3.1 -- resolver_cliente_candidato: los 3 niveles, su precedencia, y los
# escenarios de error/degradación de D3.
# =============================================================================


def test_nivel1_alias_gana_sobre_nivel2_aunque_ambos_resuelvan_y_difieran(monkeypatch):
    monkeypatch.setattr(
        repo, "buscar_alias_cliente", lambda client, **kw: _alias_row(cliente_id="cliente-alias")
    )
    mock_cuit = MagicMock(return_value=[_cuit_row(cliente_id="cliente-cuit")])
    monkeypatch.setattr(repo, "buscar_clientes_por_cuit", mock_cuit)

    resultado = service.resolver_cliente_candidato(
        MagicMock(),
        drogueria_id="d1",
        cuit_extraido="30555555553",
        texto_extraido="Hospital San Roque",
    )

    assert resultado.origen == "alias"
    assert len(resultado.candidatos) == 1
    assert resultado.candidatos[0].cliente_id == "cliente-alias"
    mock_cuit.assert_not_called()  # cortocircuito -- nivel 2 ni se consulta


def test_nivel2_cuit_exclusivo_devuelve_un_candidato(monkeypatch):
    monkeypatch.setattr(repo, "buscar_alias_cliente", lambda client, **kw: None)
    monkeypatch.setattr(
        repo,
        "buscar_clientes_por_cuit",
        lambda client, **kw: [_cuit_row(cliente_id="cliente-2", cuit_no_exclusivo=False)],
    )

    resultado = service.resolver_cliente_candidato(
        MagicMock(), drogueria_id="d1", cuit_extraido="30-55555555-3", texto_extraido=None
    )

    assert resultado.origen == "cuit"
    assert len(resultado.candidatos) == 1
    assert resultado.candidatos[0].cliente_id == "cliente-2"
    assert resultado.cuit_extraido == "30555555553"


def test_nivel2_cuit_no_exclusivo_devuelve_n_candidatos(monkeypatch):
    monkeypatch.setattr(repo, "buscar_alias_cliente", lambda client, **kw: None)
    filas = [
        _cuit_row(cliente_id="sede-1", cuit_no_exclusivo=True, razon_social="Sede 1"),
        _cuit_row(cliente_id="sede-2", cuit_no_exclusivo=True, razon_social="Sede 2"),
        _cuit_row(cliente_id="sede-3", cuit_no_exclusivo=True, razon_social="Sede 3"),
    ]
    monkeypatch.setattr(repo, "buscar_clientes_por_cuit", lambda client, **kw: filas)

    resultado = service.resolver_cliente_candidato(
        MagicMock(), drogueria_id="d1", cuit_extraido="30555555553", texto_extraido=None
    )

    assert resultado.origen == "cuit_compartido"
    assert len(resultado.candidatos) == 3
    assert {c.cliente_id for c in resultado.candidatos} == {"sede-1", "sede-2", "sede-3"}


def test_sin_match_en_ningun_nivel_devuelve_ninguno_y_lista_vacia_sin_excepcion(monkeypatch):
    monkeypatch.setattr(repo, "buscar_alias_cliente", lambda client, **kw: None)
    monkeypatch.setattr(repo, "buscar_clientes_por_cuit", lambda client, **kw: [])

    resultado = service.resolver_cliente_candidato(
        MagicMock(), drogueria_id="d1", cuit_extraido=None, texto_extraido="Texto sin match"
    )

    assert resultado.origen == "ninguno"
    assert resultado.candidatos == []


def test_cuit_malformado_saltea_nivel2_y_deja_advertencia(monkeypatch):
    monkeypatch.setattr(repo, "buscar_alias_cliente", lambda client, **kw: None)
    mock_cuit = MagicMock()
    monkeypatch.setattr(repo, "buscar_clientes_por_cuit", mock_cuit)

    resultado = service.resolver_cliente_candidato(
        MagicMock(), drogueria_id="d1", cuit_extraido="1234", texto_extraido=None
    )

    assert resultado.origen == "ninguno"
    mock_cuit.assert_not_called()
    assert resultado.cuit_extraido is None
    assert any("CUIT" in advertencia for advertencia in resultado.advertencias)


def test_tercero_con_cuit_pero_sin_fila_en_clientes_se_omite_con_advertencia(monkeypatch):
    monkeypatch.setattr(repo, "buscar_alias_cliente", lambda client, **kw: None)
    monkeypatch.setattr(
        repo, "buscar_clientes_por_cuit", lambda client, **kw: [_cuit_row(sin_cliente=True)]
    )

    resultado = service.resolver_cliente_candidato(
        MagicMock(), drogueria_id="d1", cuit_extraido="30555555553", texto_extraido=None
    )

    assert resultado.origen == "ninguno"
    assert resultado.candidatos == []
    assert any("no es cliente" in advertencia for advertencia in resultado.advertencias)


def test_cliente_inactivo_se_incluye_marcado(monkeypatch):
    monkeypatch.setattr(repo, "buscar_alias_cliente", lambda client, **kw: None)
    monkeypatch.setattr(
        repo, "buscar_clientes_por_cuit", lambda client, **kw: [_cuit_row(activo=False)]
    )

    resultado = service.resolver_cliente_candidato(
        MagicMock(), drogueria_id="d1", cuit_extraido="30555555553", texto_extraido=None
    )

    assert resultado.origen == "cuit"
    assert resultado.candidatos[0].activo is False


def test_resolver_cliente_candidato_nunca_escribe(monkeypatch):
    monkeypatch.setattr(repo, "buscar_alias_cliente", lambda client, **kw: _alias_row())
    mock_upsert = MagicMock()
    monkeypatch.setattr(repo, "upsert_alias_cliente", mock_upsert)

    service.resolver_cliente_candidato(
        MagicMock(),
        drogueria_id="d1",
        cuit_extraido=None,
        texto_extraido="Hospital San Roque",
    )

    mock_upsert.assert_not_called()


# =============================================================================
# 3.2 -- threat matrix de resolución de cliente (D3 / D3.1)
# =============================================================================


def test_alias_no_se_escribe_sin_confirmacion(monkeypatch):
    # resolver_cliente_candidato() corre al ABRIR la pantalla -- nada de lo que
    # haga puede tocar oc_cliente_alias. El único write posible es
    # _registrar_alias_cliente(), y esa función no se invoca desde acá.
    monkeypatch.setattr(repo, "buscar_alias_cliente", lambda client, **kw: None)
    monkeypatch.setattr(repo, "buscar_clientes_por_cuit", lambda client, **kw: [])
    mock_upsert = MagicMock()
    monkeypatch.setattr(repo, "upsert_alias_cliente", mock_upsert)

    service.resolver_cliente_candidato(
        MagicMock(),
        drogueria_id="d1",
        cuit_extraido=None,
        texto_extraido="Hospital San Roque",
    )

    mock_upsert.assert_not_called()


def test_correccion_pisa_y_resetea(monkeypatch):
    monkeypatch.setattr(
        repo,
        "buscar_alias_cliente",
        lambda client, **kw: {"id": "alias-1", "cliente_id": "cliente-viejo", "veces_confirmado": 5},
    )
    mock_client = MagicMock()
    mock_client.table.return_value.upsert.return_value.execute.return_value.data = [{"id": "alias-1"}]

    repo.upsert_alias_cliente(
        mock_client,
        drogueria_id="d1",
        texto_normalizado="HOSPITAL SAN ROQUE",
        texto_original="Hospital San Roque",
        cliente_id="cliente-nuevo",
        usuario_id="u1",
    )

    fila_enviada = mock_client.table.return_value.upsert.call_args.args[0]
    assert fila_enviada["cliente_id"] == "cliente-nuevo"
    assert fila_enviada["veces_confirmado"] == 1


def test_reconfirmacion_identica_incrementa_veces_confirmado(monkeypatch):
    monkeypatch.setattr(
        repo,
        "buscar_alias_cliente",
        lambda client, **kw: {"id": "alias-1", "cliente_id": "cliente-1", "veces_confirmado": 5},
    )
    mock_client = MagicMock()
    mock_client.table.return_value.upsert.return_value.execute.return_value.data = [{"id": "alias-1"}]

    repo.upsert_alias_cliente(
        mock_client,
        drogueria_id="d1",
        texto_normalizado="HOSPITAL SAN ROQUE",
        texto_original="Hospital San Roque",
        cliente_id="cliente-1",
        usuario_id="u1",
    )

    fila_enviada = mock_client.table.return_value.upsert.call_args.args[0]
    assert fila_enviada["veces_confirmado"] == 6


def test_primera_confirmacion_sin_alias_previo_arranca_en_uno(monkeypatch):
    monkeypatch.setattr(repo, "buscar_alias_cliente", lambda client, **kw: None)
    mock_client = MagicMock()
    mock_client.table.return_value.upsert.return_value.execute.return_value.data = [{"id": "alias-1"}]

    repo.upsert_alias_cliente(
        mock_client,
        drogueria_id="d1",
        texto_normalizado="HOSPITAL SAN ROQUE",
        texto_original="Hospital San Roque",
        cliente_id="cliente-1",
        usuario_id="u1",
    )

    fila_enviada = mock_client.table.return_value.upsert.call_args.args[0]
    assert fila_enviada["veces_confirmado"] == 1
    assert fila_enviada["created_by"] == "u1"


def test_texto_vacio_no_genera_alias(monkeypatch):
    mock_upsert = MagicMock()
    monkeypatch.setattr(repo, "upsert_alias_cliente", mock_upsert)

    service._registrar_alias_cliente(
        MagicMock(),
        drogueria_id="d1",
        texto_extraido="---",
        cliente_id="cliente-1",
        usuario_id="u1",
    )

    mock_upsert.assert_not_called()


def test_texto_none_no_genera_alias(monkeypatch):
    mock_upsert = MagicMock()
    monkeypatch.setattr(repo, "upsert_alias_cliente", mock_upsert)

    service._registrar_alias_cliente(
        MagicMock(),
        drogueria_id="d1",
        texto_extraido=None,
        cliente_id="cliente-1",
        usuario_id="u1",
    )

    mock_upsert.assert_not_called()


def test_registrar_alias_cliente_normaliza_y_delega_en_upsert(monkeypatch):
    mock_upsert = MagicMock()
    monkeypatch.setattr(repo, "upsert_alias_cliente", mock_upsert)

    service._registrar_alias_cliente(
        MagicMock(),
        drogueria_id="d1",
        texto_extraido="Hospital Público Ñandú S.A.",
        cliente_id="cliente-1",
        usuario_id="u1",
    )

    mock_upsert.assert_called_once()
    _, kwargs = mock_upsert.call_args
    assert kwargs["texto_normalizado"] == "HOSPITAL PUBLICO NANDU S A"
    assert kwargs["texto_original"] == "Hospital Público Ñandú S.A."
    assert kwargs["cliente_id"] == "cliente-1"
    assert kwargs["drogueria_id"] == "d1"


# =============================================================================
# 3.2 / 3.8 -- aislamiento multi-tenant y los 3 niveles en vivo, contra el
# proyecto Supabase de test.
# =============================================================================


@pytest.mark.integration
def test_alias_aislado_por_drogueria(
    service_client, seed_drogueria, seed_cliente_factory, seed_alias_cliente_factory
):
    cliente_a = seed_cliente_factory("Hospital San Roque", drogueria_id=seed_drogueria["id"])
    seed_alias_cliente_factory(
        cliente_id=cliente_a["cliente_id"],
        texto_original="Hospital San Roque",
        drogueria_id=seed_drogueria["id"],
    )

    otra_drogueria = service_client.table("droguerias").insert(
        {
            "nombre": "Otra Droguería (alias test)",
            "razon_social": "Otra Droguería SA",
            "cuit": "20-11111111-1",
            "ciudad": "Rosario",
            "provincia": "Santa Fe",
            "contacto_email": "otra-alias@seed.local",
            "contacto_telefono": "0000000000",
        }
    ).execute().data[0]

    try:
        resultado = service.resolver_cliente_candidato(
            service_client,
            drogueria_id=otra_drogueria["id"],
            cuit_extraido=None,
            texto_extraido="Hospital San Roque",
        )
        # El alias de la droguería A es invisible desde B -- nivel 1 no matchea,
        # y sin CUIT tampoco hay nivel 2, así que cae al nivel 3.
        assert resultado.origen == "ninguno"
        assert resultado.candidatos == []
    finally:
        service_client.table("droguerias").delete().eq("id", otra_drogueria["id"]).execute()


@pytest.mark.integration
def test_resolver_cliente_candidato_nivel1_alias_en_vivo(
    service_client, seed_drogueria, seed_cliente_factory, seed_alias_cliente_factory
):
    cliente = seed_cliente_factory("Hospital San Roque", drogueria_id=seed_drogueria["id"])
    seed_alias_cliente_factory(
        cliente_id=cliente["cliente_id"],
        texto_original="Hospital San Roque",
        drogueria_id=seed_drogueria["id"],
    )

    resultado = service.resolver_cliente_candidato(
        service_client,
        drogueria_id=seed_drogueria["id"],
        cuit_extraido=None,
        texto_extraido="hospital   SAN roque",  # variante tipográfica -- misma clave normalizada
    )

    assert resultado.origen == "alias"
    assert len(resultado.candidatos) == 1
    assert resultado.candidatos[0].cliente_id == cliente["cliente_id"]


@pytest.mark.integration
def test_resolver_cliente_candidato_nivel2_cuit_exclusivo_en_vivo(
    service_client, seed_drogueria, seed_cliente_factory
):
    cliente = seed_cliente_factory(
        "Clínica del Sol",
        drogueria_id=seed_drogueria["id"],
        cuit="30555555553",
        cuit_no_exclusivo=False,
    )

    resultado = service.resolver_cliente_candidato(
        service_client,
        drogueria_id=seed_drogueria["id"],
        cuit_extraido="30-55555555-3",
        texto_extraido=None,
    )

    assert resultado.origen == "cuit"
    assert len(resultado.candidatos) == 1
    assert resultado.candidatos[0].cliente_id == cliente["cliente_id"]


@pytest.mark.integration
def test_resolver_cliente_candidato_cuit_compartido_en_vivo(
    service_client, seed_drogueria, seed_cliente_factory
):
    cuit_ministerio = "30999999996"
    sede_1 = seed_cliente_factory(
        "Hospital Sede 1",
        drogueria_id=seed_drogueria["id"],
        cuit=cuit_ministerio,
        cuit_no_exclusivo=True,
    )
    sede_2 = seed_cliente_factory(
        "Hospital Sede 2",
        drogueria_id=seed_drogueria["id"],
        cuit=cuit_ministerio,
        cuit_no_exclusivo=True,
    )

    resultado = service.resolver_cliente_candidato(
        service_client,
        drogueria_id=seed_drogueria["id"],
        cuit_extraido=cuit_ministerio,
        texto_extraido=None,
    )

    assert resultado.origen == "cuit_compartido"
    ids = {c.cliente_id for c in resultado.candidatos}
    assert ids == {sede_1["cliente_id"], sede_2["cliente_id"]}


@pytest.mark.integration
def test_upsert_alias_cliente_ciclo_completo_en_vivo(
    service_client, seed_drogueria, seed_cliente_factory, seed_alias_cliente_factory
):
    cliente_1 = seed_cliente_factory("Hospital San Roque", drogueria_id=seed_drogueria["id"])
    cliente_2 = seed_cliente_factory("Hospital San Roque (corregido)", drogueria_id=seed_drogueria["id"])

    # Primera confirmación -- inserta con veces_confirmado=1.
    alias = repo.upsert_alias_cliente(
        service_client,
        drogueria_id=seed_drogueria["id"],
        texto_normalizado=normalizar_descripcion("Hospital San Roque"),
        texto_original="Hospital San Roque",
        cliente_id=cliente_1["cliente_id"],
        usuario_id=None,
    )
    try:
        assert alias["veces_confirmado"] == 1
        assert alias["cliente_id"] == cliente_1["cliente_id"]

        # Reconfirmar el mismo texto y cliente incrementa.
        alias = repo.upsert_alias_cliente(
            service_client,
            drogueria_id=seed_drogueria["id"],
            texto_normalizado=normalizar_descripcion("Hospital San Roque"),
            texto_original="Hospital San Roque",
            cliente_id=cliente_1["cliente_id"],
            usuario_id=None,
        )
        assert alias["veces_confirmado"] == 2

        # Corregir el cliente pisa cliente_id y resetea a 1.
        alias = repo.upsert_alias_cliente(
            service_client,
            drogueria_id=seed_drogueria["id"],
            texto_normalizado=normalizar_descripcion("Hospital San Roque"),
            texto_original="Hospital San Roque",
            cliente_id=cliente_2["cliente_id"],
            usuario_id=None,
        )
        assert alias["veces_confirmado"] == 1
        assert alias["cliente_id"] == cliente_2["cliente_id"]
    finally:
        service_client.table("oc_cliente_alias").delete().eq("id", alias["id"]).execute()
