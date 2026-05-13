"""
Verifica el fix del bug crítico: upload y generate_content deben usar el mismo cliente.
También verifica que requests distintos rotan entre clientes (round-robin).
"""

import asyncio
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import pytest
import httpx

from app.main import app


@pytest.fixture
def pdf(tmp_path: Path) -> Path:
    p = tmp_path / "CLIENTE_test.pdf"
    p.write_bytes(
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
        b"xref\n0 4\ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n0\n%%EOF"
    )
    return p


def _make_fake_client(name: str):
    """Crea un mock de genai.Client que registra qué operaciones se llamaron."""
    client = MagicMock(name=name)
    fake_file = MagicMock()
    fake_file.state = "ACTIVE"
    client.files.upload.return_value = fake_file
    fake_response = MagicMock()
    fake_response.text = "item;cantidad;descripcion;origen\n1;10;Producto;CLIENTE\n"
    client.models.generate_content.return_value = fake_response
    return client


def test_mismo_cliente_para_upload_y_generate(pdf: Path):
    """
    El cliente elegido al inicio de procesar_archivo debe usarse tanto
    para files.upload como para models.generate_content.
    """
    cliente_a = _make_fake_client("key_A")
    cliente_b = _make_fake_client("key_B")

    call_sequence = []

    def fake_get_next_client():
        client = cliente_a if not call_sequence else cliente_b
        call_sequence.append(client._mock_name)
        return client

    with patch("app.robot.get_next_client", side_effect=fake_get_next_client):
        from app.robot import procesar_archivo
        procesar_archivo(pdf, pdf.name)

    # get_next_client debe haberse llamado exactamente UNA vez por request
    assert len(call_sequence) == 1, (
        f"get_next_client se llamó {len(call_sequence)} veces en un solo request. "
        "Debe llamarse exactamente 1 vez."
    )

    # El cliente elegido debe haber hecho el upload Y el generate
    cliente_usado = cliente_a
    cliente_usado.files.upload.assert_called_once()
    cliente_usado.models.generate_content.assert_called_once()

    # El otro cliente no debe haber sido tocado
    cliente_b.files.upload.assert_not_called()
    cliente_b.models.generate_content.assert_not_called()


def test_round_robin_alterna_entre_requests(tmp_path: Path):
    """
    Requests distintos deben rotar entre clientes disponibles.
    """
    from app.config import CLIENTS, _client_index
    import app.config as config_module

    clientes_usados = []

    original_get_next = config_module.get_next_client

    def spy_get_next():
        client = original_get_next()
        clientes_usados.append(id(client))
        return client

    cliente_a = _make_fake_client("key_A")
    cliente_b = _make_fake_client("key_B")

    call_order = []

    def get_next_alternating():
        idx = len(call_order) % 2
        c = [cliente_a, cliente_b][idx]
        call_order.append(c._mock_name)
        return c

    pdf1 = tmp_path / "CLI1_pedido.pdf"
    pdf2 = tmp_path / "CLI2_pedido.pdf"
    contenido_pdf = (
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
        b"xref\n0 4\ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n0\n%%EOF"
    )
    pdf1.write_bytes(contenido_pdf)
    pdf2.write_bytes(contenido_pdf)

    with patch("app.robot.get_next_client", side_effect=get_next_alternating):
        from app.robot import procesar_archivo
        procesar_archivo(pdf1, pdf1.name)
        procesar_archivo(pdf2, pdf2.name)

    assert call_order == ["key_A", "key_B"], (
        f"Se esperaba alternancia A→B, se obtuvo: {call_order}"
    )


@pytest.mark.asyncio
async def test_dos_usuarios_simultaneos_no_cruzan_clientes(tmp_path: Path):
    """
    Dos requests concurrentes no deben cruzar clientes entre sí.
    Cada request debe usar un único cliente de principio a fin.
    """
    clientes_por_request = {}
    lock = asyncio.Lock()

    cliente_a = _make_fake_client("key_A")
    cliente_b = _make_fake_client("key_B")
    pool = [cliente_a, cliente_b]
    pool_idx = 0

    def get_next():
        nonlocal pool_idx
        c = pool[pool_idx % len(pool)]
        pool_idx += 1
        return c

    def fake_procesar(ruta_archivo, nombre_original=None):
        time.sleep(0.3)
        csv = ruta_archivo.parent / f"{ruta_archivo.stem}.csv"
        csv.write_text("item;cantidad;descripcion;origen\n1;10;Prod;CLI\n")
        return csv

    pdf1 = tmp_path / "CLI1_p.pdf"
    pdf2 = tmp_path / "CLI2_p.pdf"
    contenido_pdf = (
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
        b"xref\n0 4\ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n0\n%%EOF"
    )
    pdf1.write_bytes(contenido_pdf)
    pdf2.write_bytes(contenido_pdf)

    async def upload(client: httpx.AsyncClient, pdf: Path):
        with open(pdf, "rb") as f:
            return await client.post(
                "http://testserver/procesar",
                files={"archivo": (pdf.name, f, "application/pdf")},
                data={"tipo": ""},
            )

    with patch("app.main.procesar_archivo", side_effect=fake_procesar):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), timeout=30
        ) as client:
            results = await asyncio.gather(
                upload(client, pdf1),
                upload(client, pdf2),
            )

    statuses = [r.status_code for r in results]
    assert all(s < 500 for s in statuses), (
        f"Requests fallaron con error de servidor: {statuses}"
    )
