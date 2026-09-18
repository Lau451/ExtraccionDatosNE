import uuid as uuid_module
from unittest.mock import MagicMock

import pytest

from services.presupuestacion.core.exceptions import (
    ConflictError,
    ExtraccionNoDisponibleError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from services.presupuestacion.extraccion import repository as repo
from services.presupuestacion.extraccion import service
from services.presupuestacion.extraccion.models import MAX_FILAS_EDITABLES

# =============================================================================
# Helpers in-memory (sin DB) para armar miembros/extracciones con la forma que
# devuelven repo.buscar_extraction_result / repo.listar_miembros_de_grupo.
# =============================================================================


def _extraccion(
    *,
    id: str = "ext-1",
    drogueria_id: str = "d1",
    document_type: str = "orden_compra",
    validado: bool = False,
    grupo_id: str | None = None,
) -> dict:
    return {
        "id": id,
        "drogueria_id": drogueria_id,
        "document_type": document_type,
        "validado": validado,
        "grupo_id": grupo_id,
    }


def _miembro(*, id: str, archivo: str) -> dict:
    return {"id": id, "source_filename": archivo, "csv_disk_path": f"/fake/{id}.csv"}


# =============================================================================
# 4.1 -- _leer_filas_grupo: concatenación sin transformación (D13/D13.1).
# =============================================================================


def test_leer_filas_grupo_grupo_id_null_se_comporta_como_archivo_suelto(monkeypatch):
    extraction = {
        "id": "ext-1",
        "source_filename": "archivo1.pdf",
        "csv_disk_path": "/fake/ext-1.csv",
        "grupo_id": None,
    }
    columnas_csv = ["numero_renglon", "descripcion", "cantidad"]
    filas_csv = [
        {"numero_renglon": "1", "descripcion": "Item A", "cantidad": "10"},
        {"numero_renglon": "2", "descripcion": "Item B", "cantidad": "20"},
    ]
    monkeypatch.setattr(
        service,
        "_leer_filas_csv_con_columnas",
        lambda path: (columnas_csv, filas_csv) if path == "/fake/ext-1.csv" else pytest.fail(
            f"path inesperado: {path}"
        ),
    )
    mock_listar_grupo = MagicMock()
    monkeypatch.setattr(repo, "listar_miembros_de_grupo", mock_listar_grupo)

    columnas, filas, miembros = service._leer_filas_grupo(MagicMock(), extraction=extraction)

    mock_listar_grupo.assert_not_called()  # grupo_id NULL -> no consulta miembros de grupo
    assert miembros == [extraction]
    assert columnas == columnas_csv
    assert len(filas) == 2
    assert filas[0]["_archivo"] == "archivo1.pdf"
    assert filas[0]["_extraction_id"] == "ext-1"
    assert filas[0]["descripcion"] == "Item A"
    assert filas[1]["descripcion"] == "Item B"


def test_leer_filas_grupo_tres_miembros_concatena_en_orden_de_grupo(monkeypatch):
    miembros = [
        _miembro(id="ext-1", archivo="a.pdf"),
        _miembro(id="ext-2", archivo="b.pdf"),
        _miembro(id="ext-3", archivo="c.pdf"),
    ]
    monkeypatch.setattr(repo, "listar_miembros_de_grupo", lambda client, **kw: miembros)

    columnas = ["numero_renglon", "descripcion", "cantidad"]
    filas_por_archivo = {
        "/fake/ext-1.csv": (columnas, [{"numero_renglon": "1", "descripcion": "A1", "cantidad": "10"}]),
        "/fake/ext-2.csv": (
            columnas,
            [
                {"numero_renglon": "1", "descripcion": "B1", "cantidad": "5"},
                {"numero_renglon": "2", "descripcion": "B2", "cantidad": "7"},
            ],
        ),
        "/fake/ext-3.csv": (columnas, [{"numero_renglon": "1", "descripcion": "C1", "cantidad": "3"}]),
    }
    monkeypatch.setattr(service, "_leer_filas_csv_con_columnas", lambda path: filas_por_archivo[path])

    extraction = {
        "id": "ext-1",
        "grupo_id": "grupo-1",
        "csv_disk_path": "/fake/ext-1.csv",
        "source_filename": "a.pdf",
    }
    columnas_out, filas, miembros_out = service._leer_filas_grupo(MagicMock(), extraction=extraction)

    assert columnas_out == columnas
    assert len(filas) == 4  # 1 + 2 + 1 -- suma exacta, orden de grupo
    assert [f["_archivo"] for f in filas] == ["a.pdf", "b.pdf", "b.pdf", "c.pdf"]
    assert [f["_extraction_id"] for f in filas] == ["ext-1", "ext-2", "ext-2", "ext-3"]
    assert filas[1]["descripcion"] == "B1"
    assert filas[2]["descripcion"] == "B2"
    assert miembros_out == miembros


def test_renglones_repetidos_no_se_suman(monkeypatch):
    # C10/D13.1: los 3 archivos declaran el MISMO conjunto de numero_renglon
    # (1, 2) -- ninguna heurística de "conjuntos idénticos" debe fusionar ni
    # sumar cantidades entre archivos. Satisface también 4.1 (aserción
    # explícita de que no transforma) y 4.4 (threat-matrix).
    miembros = [
        _miembro(id="ext-1", archivo="a.pdf"),
        _miembro(id="ext-2", archivo="b.pdf"),
        _miembro(id="ext-3", archivo="c.pdf"),
    ]
    monkeypatch.setattr(repo, "listar_miembros_de_grupo", lambda client, **kw: miembros)

    columnas = ["numero_renglon", "descripcion", "cantidad"]

    def _filas(archivo: str) -> list[dict[str, str]]:
        return [
            {"numero_renglon": "1", "descripcion": f"Item 1 ({archivo})", "cantidad": "10"},
            {"numero_renglon": "2", "descripcion": f"Item 2 ({archivo})", "cantidad": "20"},
        ]

    filas_por_archivo = {
        "/fake/ext-1.csv": (columnas, _filas("a")),
        "/fake/ext-2.csv": (columnas, _filas("b")),
        "/fake/ext-3.csv": (columnas, _filas("c")),
    }
    monkeypatch.setattr(service, "_leer_filas_csv_con_columnas", lambda path: filas_por_archivo[path])

    extraction = {
        "id": "ext-1",
        "grupo_id": "grupo-1",
        "csv_disk_path": "/fake/ext-1.csv",
        "source_filename": "a.pdf",
    }
    _, filas, _ = service._leer_filas_grupo(MagicMock(), extraction=extraction)

    assert len(filas) == 6  # 2 + 2 + 2, ninguna se fusiona pese al numero_renglon repetido
    assert [f["cantidad"] for f in filas] == ["10", "20", "10", "20", "10", "20"]
    assert [f["numero_renglon"] for f in filas] == ["1", "2", "1", "2", "1", "2"]


def test_leer_filas_grupo_editable_se_evalua_sobre_el_total_concatenado(monkeypatch):
    # 3 miembros con 200 filas cada uno (total 600) superan MAX_FILAS_EDITABLES
    # (500) aunque ningún miembro individual lo supere -- editable se evalúa
    # sobre la CONCATENACIÓN, no por archivo.
    miembros = [_miembro(id=f"ext-{i}", archivo=f"{i}.pdf") for i in range(3)]
    monkeypatch.setattr(repo, "listar_miembros_de_grupo", lambda client, **kw: miembros)

    columnas = ["numero_renglon", "descripcion", "cantidad"]
    filas_por_archivo = {
        f"/fake/ext-{i}.csv": (
            columnas,
            [
                {"numero_renglon": str(n), "descripcion": f"Item {n}", "cantidad": "1"}
                for n in range(200)
            ],
        )
        for i in range(3)
    }
    monkeypatch.setattr(service, "_leer_filas_csv_con_columnas", lambda path: filas_por_archivo[path])

    extraction = {
        "id": "ext-0",
        "grupo_id": "grupo-1",
        "csv_disk_path": "/fake/ext-0.csv",
        "source_filename": "0.pdf",
    }
    _, filas, _ = service._leer_filas_grupo(MagicMock(), extraction=extraction)

    assert len(filas) == 600
    editable = len(filas) <= MAX_FILAS_EDITABLES
    assert editable is False


def test_grupo_sin_numero_de_renglon_se_materializa(monkeypatch):
    # documento sin número de línea en un grupo de N archivos: no bloquea ni
    # se rellena (D6/C10) -- la celda queda vacía tal cual.
    miembros = [_miembro(id="ext-1", archivo="a.pdf"), _miembro(id="ext-2", archivo="b.pdf")]
    monkeypatch.setattr(repo, "listar_miembros_de_grupo", lambda client, **kw: miembros)
    columnas = ["numero_renglon", "descripcion", "cantidad"]
    filas_por_archivo = {
        "/fake/ext-1.csv": (columnas, [{"numero_renglon": "", "descripcion": "Gasa", "cantidad": "40"}]),
        "/fake/ext-2.csv": (columnas, [{"numero_renglon": "", "descripcion": "Alcohol", "cantidad": "25"}]),
    }
    monkeypatch.setattr(service, "_leer_filas_csv_con_columnas", lambda path: filas_por_archivo[path])

    extraction = {
        "id": "ext-1",
        "grupo_id": "grupo-1",
        "csv_disk_path": "/fake/ext-1.csv",
        "source_filename": "a.pdf",
    }
    _, filas, _ = service._leer_filas_grupo(MagicMock(), extraction=extraction)

    assert len(filas) == 2
    assert [f["numero_renglon"] for f in filas] == ["", ""]  # vacío, no rellenado


def test_miembro_sin_csv_aborta(tmp_path, monkeypatch):
    # Un miembro sin CSV en disco (volumen no montado) levanta
    # ExtraccionNoDisponibleError en la primera lectura que falle -- antes de
    # cualquier write (esta función no escribe nada).
    ruta_inexistente = str(tmp_path / "no-existe.csv")
    miembros = [
        {"id": "ext-1", "source_filename": "a.pdf", "csv_disk_path": ruta_inexistente},
        {"id": "ext-2", "source_filename": "b.pdf", "csv_disk_path": str(tmp_path / "b.csv")},
    ]
    monkeypatch.setattr(repo, "listar_miembros_de_grupo", lambda client, **kw: miembros)
    # No se monkeypatchea _leer_filas_csv_con_columnas -- se usa la función
    # real, que levanta ExtraccionNoDisponibleError sobre un path inexistente
    # (mismo comportamiento que protege GET .../filas hoy, §8.2).

    extraction = {
        "id": "ext-1",
        "grupo_id": "grupo-1",
        "csv_disk_path": ruta_inexistente,
        "source_filename": "a.pdf",
    }

    with pytest.raises(ExtraccionNoDisponibleError):
        service._leer_filas_grupo(MagicMock(), extraction=extraction)


# =============================================================================
# 4.2 -- _conciliar_cabecera (D13.1 § Cabecera inconsistente entre archivos).
# =============================================================================


def _fila_cabecera(
    *,
    numero_oc: str = "OC-1",
    razon_social_cliente: str = "Hospital A",
    fecha_emision: str = "01/01/2026",
    direccion_entrega: str = "Calle 1",
    cantidad_entregas: str = "1",
    cuit_cliente: str = "30712345679",
) -> dict[str, str]:
    return {
        "numero_oc": numero_oc,
        "razon_social_cliente": razon_social_cliente,
        "fecha_emision": fecha_emision,
        "direccion_entrega": direccion_entrega,
        "cantidad_entregas": cantidad_entregas,
        "cuit_cliente": cuit_cliente,
    }


def test_conciliar_cabecera_numero_oc_distinto_bloquea():
    filas_por_miembro = [
        _fila_cabecera(numero_oc="OC-1"),
        _fila_cabecera(numero_oc="OC-2"),
    ]
    with pytest.raises(ValidationError):
        service._conciliar_cabecera(filas_por_miembro)


def test_conciliar_cabecera_otros_campos_distintos_advierten_sin_bloquear():
    filas_por_miembro = [
        _fila_cabecera(fecha_emision="01/01/2026", direccion_entrega="Calle 1", cantidad_entregas="1"),
        _fila_cabecera(fecha_emision="02/01/2026", direccion_entrega="Calle 2", cantidad_entregas="2"),
    ]
    cabecera, advertencias = service._conciliar_cabecera(filas_por_miembro)

    assert cabecera["numero_oc"] == "OC-1"  # no bloqueó
    assert len(advertencias) == 3  # fecha_emision, direccion_entrega, cantidad_entregas


def test_conciliar_cabecera_valor_mas_frecuente_gana():
    filas_por_miembro = [
        _fila_cabecera(fecha_emision="01/01/2026"),
        _fila_cabecera(fecha_emision="01/01/2026"),
        _fila_cabecera(fecha_emision="02/01/2026"),
    ]
    cabecera, _ = service._conciliar_cabecera(filas_por_miembro)

    assert cabecera["fecha_emision"] == "01/01/2026"  # 2 de 3 miembros


def test_conciliar_cabecera_empate_gana_el_primer_miembro():
    filas_por_miembro = [
        _fila_cabecera(fecha_emision="01/01/2026"),
        _fila_cabecera(fecha_emision="02/01/2026"),
    ]
    cabecera, _ = service._conciliar_cabecera(filas_por_miembro)

    assert cabecera["fecha_emision"] == "01/01/2026"  # empate 1-1 -> gana el primero


# =============================================================================
# 4.3 -- 5 precondiciones de agrupar_extracciones + desagrupar_extracciones.
# =============================================================================


def test_agrupar_requiere_al_menos_2_ids_sin_repetidos():
    with pytest.raises(ValidationError):
        service.agrupar_extracciones(MagicMock(), extraction_ids=["a"], drogueria_id="d1")
    with pytest.raises(ValidationError):
        service.agrupar_extracciones(MagicMock(), extraction_ids=["a", "a"], drogueria_id="d1")


def test_agrupar_extraccion_inexistente_da_404(monkeypatch):
    monkeypatch.setattr(repo, "buscar_extraction_result", lambda client, **kw: None)

    with pytest.raises(NotFoundError):
        service.agrupar_extracciones(MagicMock(), extraction_ids=["a", "b"], drogueria_id="d1")


def test_agrupar_extraccion_de_otra_drogueria_da_403(monkeypatch):
    filas = {"a": _extraccion(id="a"), "b": _extraccion(id="b", drogueria_id="d2")}
    monkeypatch.setattr(
        repo, "buscar_extraction_result", lambda client, *, extraction_id: filas[extraction_id]
    )

    with pytest.raises(ForbiddenError):
        service.agrupar_extracciones(MagicMock(), extraction_ids=["a", "b"], drogueria_id="d1")


def test_agrupar_document_type_distinto_da_422(monkeypatch):
    filas = {"a": _extraccion(id="a"), "b": _extraccion(id="b", document_type="licitacion")}
    monkeypatch.setattr(
        repo, "buscar_extraction_result", lambda client, *, extraction_id: filas[extraction_id]
    )

    with pytest.raises(ValidationError):
        service.agrupar_extracciones(MagicMock(), extraction_ids=["a", "b"], drogueria_id="d1")


def test_agrupar_validada_rechazado(monkeypatch):
    # 4.3 (precondición) + 4.4 (threat-matrix): ConflictError ANTES del UPDATE.
    filas = {"a": _extraccion(id="a"), "b": _extraccion(id="b", validado=True)}
    monkeypatch.setattr(
        repo, "buscar_extraction_result", lambda client, *, extraction_id: filas[extraction_id]
    )
    mock_actualizar = MagicMock()
    monkeypatch.setattr(repo, "actualizar_grupo_id", mock_actualizar)

    with pytest.raises(ConflictError):
        service.agrupar_extracciones(MagicMock(), extraction_ids=["a", "b"], drogueria_id="d1")

    mock_actualizar.assert_not_called()


def test_agrupar_mas_de_un_grupo_id_distinto_da_409(monkeypatch):
    filas = {
        "a": _extraccion(id="a", grupo_id="g1"),
        "b": _extraccion(id="b", grupo_id="g2"),
    }
    monkeypatch.setattr(
        repo, "buscar_extraction_result", lambda client, *, extraction_id: filas[extraction_id]
    )

    with pytest.raises(ConflictError):
        service.agrupar_extracciones(MagicMock(), extraction_ids=["a", "b"], drogueria_id="d1")


def test_agrupar_exitoso_genera_grupo_id_nuevo_y_actualiza_ambas(monkeypatch):
    filas = {"a": _extraccion(id="a"), "b": _extraccion(id="b")}
    monkeypatch.setattr(
        repo, "buscar_extraction_result", lambda client, *, extraction_id: filas[extraction_id]
    )
    mock_actualizar = MagicMock()
    monkeypatch.setattr(repo, "actualizar_grupo_id", mock_actualizar)

    grupo_id = service.agrupar_extracciones(MagicMock(), extraction_ids=["a", "b"], drogueria_id="d1")

    assert grupo_id
    llamadas = [call.kwargs for call in mock_actualizar.call_args_list]
    assert {"extraction_id": "a", "grupo_id": grupo_id} in llamadas
    assert {"extraction_id": "b", "grupo_id": grupo_id} in llamadas


def test_desagrupar_deja_grupo_id_null_y_disuelve_el_de_un_solo_miembro_restante(monkeypatch):
    filas = {"a": _extraccion(id="a", grupo_id="g1")}
    monkeypatch.setattr(
        repo, "buscar_extraction_result", lambda client, *, extraction_id: filas[extraction_id]
    )
    mock_actualizar = MagicMock()
    monkeypatch.setattr(repo, "actualizar_grupo_id", mock_actualizar)
    # Tras desagrupar "a", queda un solo miembro restante en el grupo ("c").
    monkeypatch.setattr(
        repo, "listar_miembros_de_grupo", lambda client, **kw: [_extraccion(id="c", grupo_id="g1")]
    )

    service.desagrupar_extracciones(MagicMock(), extraction_ids=["a"], drogueria_id="d1")

    llamadas = [call.kwargs for call in mock_actualizar.call_args_list]
    assert {"extraction_id": "a", "grupo_id": None} in llamadas
    assert {"extraction_id": "c", "grupo_id": None} in llamadas  # se disuelve el resto


def test_desagrupar_extraccion_validada_rechazado(monkeypatch):
    filas = {"a": _extraccion(id="a", grupo_id="g1", validado=True)}
    monkeypatch.setattr(
        repo, "buscar_extraction_result", lambda client, *, extraction_id: filas[extraction_id]
    )
    mock_actualizar = MagicMock()
    monkeypatch.setattr(repo, "actualizar_grupo_id", mock_actualizar)

    with pytest.raises(ConflictError):
        service.desagrupar_extracciones(MagicMock(), extraction_ids=["a"], drogueria_id="d1")

    mock_actualizar.assert_not_called()


# =============================================================================
# 4.9 -- contra el proyecto Supabase de test (grnamollopxdlstcpxhc).
# =============================================================================

_COLUMNAS_OC = [
    "numero_oc",
    "fecha_emision",
    "cuit_cliente",
    "razon_social_cliente",
    "direccion_entrega",
    "cantidad_entregas",
    "numero_renglon",
    "descripcion",
    "cantidad",
    "precio_unitario",
    "entregas",
]


def _fila_oc(numero_renglon: str, descripcion: str, cantidad: str) -> dict[str, str]:
    return {
        "numero_oc": "OC-4471",
        "fecha_emision": "12/09/2026",
        "cuit_cliente": "30712345679",
        "razon_social_cliente": "HOSPITAL SAN ROQUE",
        "direccion_entrega": "Av. Siempreviva 742",
        "cantidad_entregas": "2",
        "numero_renglon": numero_renglon,
        "descripcion": descripcion,
        "cantidad": cantidad,
        "precio_unitario": "1250,00",
        "entregas": "",
    }


@pytest.mark.integration
def test_leer_filas_grupo_en_vivo_concatena_los_miembros_del_grupo(
    service_client, seed_drogueria, seed_proceso_comercial, seed_extraction_result_factory,
    seed_usuario_sistema,
):
    grupo_id = str(uuid_module.uuid4())

    miembro_1 = seed_extraction_result_factory(
        "orden_compra",
        filas=[_fila_oc("1", "Ibuprofeno 400mg", "100")],
        columnas=_COLUMNAS_OC,
        grupo_id=grupo_id,
        source_filename="archivo1.pdf",
    )
    miembro_2 = seed_extraction_result_factory(
        "orden_compra",
        filas=[_fila_oc("2", "Amoxicilina 500mg", "80"), _fila_oc("3", "Gasa esteril", "40")],
        columnas=_COLUMNAS_OC,
        grupo_id=grupo_id,
        source_filename="archivo2.pdf",
    )

    extraction = (
        service_client.table("extraction_results")
        .select("*")
        .eq("id", miembro_1["id"])
        .limit(1)
        .execute()
        .data[0]
    )

    _, filas, miembros = service._leer_filas_grupo(service_client, extraction=extraction)

    assert len(filas) == 3  # 1 + 2, suma exacta -- no fusiona
    assert [f["_extraction_id"] for f in filas] == [
        miembro_1["id"],
        miembro_2["id"],
        miembro_2["id"],
    ]
    assert [f["_archivo"] for f in filas] == ["archivo1.pdf", "archivo2.pdf", "archivo2.pdf"]
    assert {m["id"] for m in miembros} == {miembro_1["id"], miembro_2["id"]}


@pytest.mark.integration
def test_agrupar_y_desagrupar_extracciones_en_vivo(
    service_client, seed_drogueria, seed_proceso_comercial, seed_extraction_result_factory,
    seed_usuario_sistema,
):
    miembro_1 = seed_extraction_result_factory(
        "orden_compra", filas=[_fila_oc("1", "Ibuprofeno 400mg", "100")], columnas=_COLUMNAS_OC
    )
    miembro_2 = seed_extraction_result_factory(
        "orden_compra", filas=[_fila_oc("1", "Amoxicilina 500mg", "80")], columnas=_COLUMNAS_OC
    )

    grupo_id = service.agrupar_extracciones(
        service_client,
        extraction_ids=[miembro_1["id"], miembro_2["id"]],
        drogueria_id=seed_drogueria["id"],
    )

    filas_agrupadas = (
        service_client.table("extraction_results")
        .select("id, grupo_id")
        .in_("id", [miembro_1["id"], miembro_2["id"]])
        .execute()
        .data
    )
    assert {f["grupo_id"] for f in filas_agrupadas} == {grupo_id}

    service.desagrupar_extracciones(
        service_client,
        extraction_ids=[miembro_1["id"], miembro_2["id"]],
        drogueria_id=seed_drogueria["id"],
    )

    filas_finales = (
        service_client.table("extraction_results")
        .select("id, grupo_id")
        .in_("id", [miembro_1["id"], miembro_2["id"]])
        .execute()
        .data
    )
    assert all(fila["grupo_id"] is None for fila in filas_finales)
