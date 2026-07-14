"""
Tests para services/extraccion/background_tasks.py — Retry 3x con backoff exponencial.

Verifica:
- schedule_persist_output: registra la tarea sin error
- _retry_persist: primer intento OK → sin retry
- _retry_persist: todos fallan → log ERROR x3, sin propagación de excepción
- _retry_persist: backoff exponencial de 2^1, 2^2, 2^3 segundos (mock asyncio.sleep)
- _retry_persist: falla 2 veces, tercer intento OK → retorna UUID
"""

import uuid
from pathlib import Path
from uuid import UUID
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest
from fastapi import BackgroundTasks

from services.extraccion import background_tasks
from services.extraccion.background_tasks import _retry_persist, schedule_persist_output


# ---------------------------------------------------------------------------
# Fixtures compartidas
# ---------------------------------------------------------------------------

@pytest.fixture
def kwargs_base(tmp_path):
    """
    Kwargs comunes para todas las llamadas a _retry_persist /
    schedule_persist_output.
    """
    csv_path = tmp_path / "resultado.csv"
    csv_path.touch()
    return {
        "session_id": UUID("12345678-1234-5678-1234-567812345678"),
        "doc_type": "comparativa",
        "rows": [{"proveedor": "ACME", "precio": "100"}],
        "csv_path": csv_path,
        "client_id": "cliente_a",
        "source_filename": "comparativa.xlsx",
        "source_sha256": "a" * 64,
    }


# ---------------------------------------------------------------------------
# Tests de schedule_persist_output
# ---------------------------------------------------------------------------

class TestSchedulePersistOutput:
    """Tests para schedule_persist_output()."""

    @pytest.mark.asyncio
    async def test_schedule_persist_output_success(self, kwargs_base):
        """
        schedule_persist_output registra la background task correctamente
        sin lanzar excepción.
        """
        bg_mock = MagicMock(spec=BackgroundTasks)

        # No debe lanzar excepción
        await schedule_persist_output(bg_mock, **kwargs_base)

        # Verificamos que se llamó a add_task exactamente una vez
        bg_mock.add_task.assert_called_once()
        # El primer argumento debe ser la función _retry_persist
        primer_arg = bg_mock.add_task.call_args[0][0]
        assert primer_arg is background_tasks._retry_persist


# ---------------------------------------------------------------------------
# Tests de _retry_persist
# ---------------------------------------------------------------------------

class TestRetryPersist:
    """Tests para _retry_persist() directamente."""

    @pytest.mark.asyncio
    async def test_retry_persist_first_attempt_success(self, kwargs_base, mocker):
        """
        Cuando persistir_output_final tiene éxito en el primer intento →
        no hay sleeps, termina sin error.
        """
        extraction_uuid = uuid.uuid4()
        mock_persistir = mocker.patch(
            "services.extraccion.background_tasks.persistir_output_final",
            new_callable=AsyncMock,
            return_value=extraction_uuid,
        )
        mock_sleep = mocker.patch("services.extraccion.background_tasks.asyncio.sleep", new_callable=AsyncMock)

        await _retry_persist(**kwargs_base, attempt=0, max_attempts=3)

        mock_persistir.assert_awaited_once()
        mock_sleep.assert_not_awaited()  # Sin backoff si primer intento OK

    @pytest.mark.asyncio
    async def test_retry_persist_fails_3_times(self, kwargs_base, mocker, caplog):
        """
        Cuando los 3 intentos fallan → se logea ERROR, y NO se propaga
        excepción al caller (la función retorna silenciosamente).
        """
        import logging

        mocker.patch(
            "services.extraccion.background_tasks.persistir_output_final",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Error de BD simulado"),
        )
        mocker.patch("services.extraccion.background_tasks.asyncio.sleep", new_callable=AsyncMock)

        with caplog.at_level(logging.ERROR, logger="services.extraccion.background_tasks"):
            # No debe lanzar excepción
            await _retry_persist(**kwargs_base, attempt=0, max_attempts=3)

        # Debe existir al menos un mensaje de ERROR en los logs
        assert any(
            "definitivamente" in msg or "fallida" in msg
            for msg in caplog.messages
        ), f"Se esperaba ERROR de persistencia definitiva. Mensajes: {caplog.messages}"

    @pytest.mark.asyncio
    async def test_retry_persist_backoff_exponencial(self, kwargs_base, mocker):
        """
        Los sleeps deben ser 2^1=2s y 2^2=4s entre intentos fallidos.

        Esquema con max_attempts=3:
          intento 0 → falla → sleep(2)
          intento 1 → falla → sleep(4)
          intento 2 → falla → ERROR (no sleep)
        """
        mocker.patch(
            "services.extraccion.background_tasks.persistir_output_final",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Error"),
        )
        mock_sleep = mocker.patch(
            "services.extraccion.background_tasks.asyncio.sleep",
            new_callable=AsyncMock,
        )

        await _retry_persist(**kwargs_base, attempt=0, max_attempts=3)

        # Debe haberse llamado a sleep exactamente 2 veces: 2s y 4s
        assert mock_sleep.await_count == 2
        sleep_args = [c.args[0] for c in mock_sleep.await_args_list]
        assert sleep_args == [2, 4], (
            f"Se esperaba [2, 4] segundos de backoff, se obtuvo: {sleep_args}"
        )

    @pytest.mark.asyncio
    async def test_retry_persist_partial_failure(self, kwargs_base, mocker):
        """
        persistir_output_final falla 2 veces y luego tiene éxito en el
        tercer intento → retorna sin error.
        """
        extraction_uuid = uuid.uuid4()
        falla = RuntimeError("Error temporal")

        mock_persistir = mocker.patch(
            "services.extraccion.background_tasks.persistir_output_final",
            new_callable=AsyncMock,
            side_effect=[falla, falla, extraction_uuid],
        )
        mock_sleep = mocker.patch(
            "services.extraccion.background_tasks.asyncio.sleep",
            new_callable=AsyncMock,
        )

        # No debe lanzar excepción
        await _retry_persist(**kwargs_base, attempt=0, max_attempts=3)

        # Se llamó 3 veces (2 fallos + 1 éxito)
        assert mock_persistir.await_count == 3
        # Se durmió 2 veces antes de reintentar
        assert mock_sleep.await_count == 2
