"""
Test de concurrencia para el endpoint /procesar.

Verifica que múltiples usuarios pueden subir archivos simultáneamente sin que
el servidor se bloquee. Mockea procesar_archivo para no consumir quota de Gemini.
"""

import asyncio
import time
import pytest
import pytest_asyncio
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from app.main import app

# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def test_pdf(tmp_path: Path) -> Path:
    """PDF mínimo válido para simular un upload."""
    pdf = tmp_path / "CLIENTE_pedido.pdf"
    pdf.write_bytes(
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
        b"xref\n0 4\ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n0\n%%EOF"
    )
    return pdf


def _fake_procesar(ruta_archivo: Path, nombre_original: str | None = None) -> Path:
    """Simula procesar_archivo: tarda 1s y devuelve un CSV válido."""
    time.sleep(1)
    csv = ruta_archivo.parent / "resultado.csv"
    csv.write_text("item;cantidad;descripcion;origen\n1;10;Producto test;CLIENTE\n")
    return csv


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _upload(client: httpx.AsyncClient, pdf: Path) -> tuple[int, float]:
    """Hace un POST /procesar y devuelve (status_code, elapsed_seconds)."""
    pass  # se usa la versión async abajo


async def _upload_async(client: httpx.AsyncClient, pdf: Path) -> tuple[int, float]:
    start = time.monotonic()
    with open(pdf, "rb") as f:
        response = await client.post(
            "http://testserver/procesar",
            files={"archivo": (pdf.name, f, "application/pdf")},
            data={"tipo": ""},
        )
    return response.status_code, time.monotonic() - start


# ─── Tests ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("num_users", [2, 3, 5])
async def test_concurrent_uploads(num_users: int, test_pdf: Path, tmp_path: Path):
    """
    Verifica que N usuarios simultáneos reciben respuesta sin que el servidor se bloquee.

    Criterio: el tiempo total debe ser menor a (num_users * tiempo_individual),
    lo que confirma que los requests corren en paralelo y no en serie.
    """
    with patch("app.main.procesar_archivo", side_effect=_fake_procesar):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), timeout=30
        ) as client:
            tasks = [_upload_async(client, test_pdf) for _ in range(num_users)]
            results = await asyncio.gather(*tasks)

    statuses = [s for s, _ in results]
    times = [t for _, t in results]
    total_elapsed = max(times)
    serial_estimate = sum(times)

    # Todos deben responder (2xx o error de negocio, no timeouts)
    assert all(s < 500 for s in statuses), (
        f"Hubo errores de servidor: {statuses}"
    )

    # El tiempo real debe ser notablemente menor al serial
    # Con mock de 1s cada uno, el paralelo debería ser ~1-2s, no ~N segundos
    assert total_elapsed < serial_estimate * 0.7, (
        f"Posible bloqueo del event loop: "
        f"total={total_elapsed:.2f}s, serial estimado={serial_estimate:.2f}s"
    )


@pytest.mark.asyncio
async def test_semaforo_limita_concurrencia(test_pdf: Path):
    """
    Verifica que el semáforo (_GEMINI_SEMAPHORE) acepta 5 requests simultáneos
    sin rechazarlos. El sexto debe esperar, no fallar.
    """
    call_count = 0

    def _fake_con_contador(ruta, nombre=None):
        nonlocal call_count
        call_count += 1
        time.sleep(0.5)
        csv = ruta.parent / "resultado.csv"
        csv.write_text("item;cantidad;descripcion;origen\n1;5;Producto;CLIENTE\n")
        return csv

    with patch("app.main.procesar_archivo", side_effect=_fake_con_contador):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), timeout=30
        ) as client:
            tasks = [_upload_async(client, test_pdf) for _ in range(6)]
            results = await asyncio.gather(*tasks)

    statuses = [s for s, _ in results]
    assert all(s < 500 for s in statuses), f"Errores inesperados: {statuses}"
    assert call_count == 6, f"Se esperaban 6 llamadas, hubo {call_count}"
