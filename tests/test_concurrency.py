#!/usr/bin/env python3
"""
Script de simulación de carga concurrente para validar run_in_executor.
Hace requests simultáneos para probar que la app no se congela.
"""

import asyncio
import httpx
import time
import sys
from pathlib import Path
from typing import Tuple

# Config
BASE_URL = "http://localhost:8000"
NUM_CONCURRENT_USERS = 10
TEST_FILE = Path(__file__).parent / "test_file.pdf"

# Crear archivo de prueba si no existe
if not TEST_FILE.exists():
    print(f"Creando PDF de prueba...")
    import subprocess
    result = subprocess.run([sys.executable, str(Path(__file__).parent / "create_test_pdf.py")], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error creando PDF: {result.stderr}")
        sys.exit(1)
    print(f"OK - Archivo de prueba listo: {TEST_FILE}")


async def upload_file(
    client: httpx.AsyncClient,
    user_id: int,
    file_path: Path,
    tipo: str = "licitaciones"
) -> Tuple[int, float, bool]:
    """
    Hace un upload a /procesar y retorna (user_id, tiempo, éxito).
    """
    start = time.time()
    try:
        with open(file_path, "rb") as f:
            files = {"archivo": (file_path.name, f, "application/octet-stream")}
            data = {"tipo": tipo}

            resp = await client.post(f"{BASE_URL}/procesar", files=files, data=data)
            elapsed = time.time() - start
            success = resp.status_code < 400

            if not success:
                try:
                    error_text = resp.text[:200]
                    if user_id == 1:  # Solo mostrar el error una vez
                        print(f"  (Usuario {user_id} error: {resp.status_code} - {error_text})")
                except:
                    pass

            return (user_id, elapsed, success)

    except Exception as e:
        elapsed = time.time() - start
        if user_id == 1:  # Solo mostrar una vez
            print(f"  (Usuario {user_id} error: {e})")
        return (user_id, elapsed, False)


async def simulate_concurrent_load(
    num_users: int = 5,
    tipo: str = "licitaciones"
) -> bool:
    """
    Simula múltiples usuarios haciendo uploads simultáneamente.
    """
    print(f"\n{'='*60}")
    print(f"SIMULACIÓN DE CARGA CONCURRENTE")
    print(f"{'='*60}")
    print(f"Users simultáneos: {num_users}")
    print(f"Tipo: {tipo}")
    print(f"URL: {BASE_URL}/procesar")
    print(f"Archivo: {TEST_FILE.name} ({TEST_FILE.stat().st_size} bytes)")
    print(f"{'='*60}\n")

    # Verificar que la app esté corriendo
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(f"{BASE_URL}/")
            if resp.status_code != 200:
                print("✗ No se puede conectar a la app. ¿Está corriendo en http://localhost:8000?")
                sys.exit(1)
    except Exception as e:
        print(f"✗ Error de conexión: {e}")
        print("Asegúrate de que la app está corriendo: uvicorn app.main:app --host 0.0.0.0 --port 8000")
        sys.exit(1)

    # Hacer los requests concurrentes
    start_total = time.time()

    async with httpx.AsyncClient(timeout=120) as client:
        tasks = [
            upload_file(client, user_id, TEST_FILE, tipo)
            for user_id in range(1, num_users + 1)
        ]

        print("🚀 Enviando requests...\n")
        results = await asyncio.gather(*tasks)

    elapsed_total = time.time() - start_total

    # Analizar resultados
    print(f"\n{'='*60}")
    print(f"RESULTADOS")
    print(f"{'='*60}\n")

    successes = sum(1 for _, _, ok in results if ok)
    failures = num_users - successes

    print(f"Total usuarios:     {num_users}")
    print(f"Exitosos:           {successes} ✓")
    print(f"Fallidos:           {failures} ✗")
    print(f"Tiempo total:       {elapsed_total:.2f}s")

    if results:
        times = [t for _, t, _ in results]
        avg_time = sum(times) / len(times)
        min_time = min(times)
        max_time = max(times)
        print(f"\nTiempos individuales:")
        print(f"  Promedio:         {avg_time:.2f}s")
        print(f"  Mínimo:           {min_time:.2f}s")
        print(f"  Máximo:           {max_time:.2f}s")

        print(f"\nDetalles por usuario:")
        for user_id, elapsed, success in sorted(results):
            status = "✓" if success else "✗"
            print(f"  Usuario {user_id:2d}: {elapsed:6.2f}s {status}")

    # Validación de concurrencia
    print(f"\n{'='*60}")
    print(f"ANÁLISIS DE CONCURRENCIA")
    print(f"{'='*60}\n")

    # Si todos completaron sin congelación, es buen signo
    # La app se congela cuando el tiempo total es muy cercano a (max_time * num_users)
    serial_time = sum(times)
    concurrent_efficiency = (serial_time / elapsed_total) * 100

    print(f"Tiempo si fuera serial: ~{serial_time:.2f}s")
    print(f"Tiempo real (concurrente): {elapsed_total:.2f}s")
    print(f"Eficiencia de concurrencia: {concurrent_efficiency:.0f}%")

    if concurrent_efficiency > 70:
        print(f"✓ EXCELENTE: La app maneja bien la concurrencia")
    elif concurrent_efficiency > 50:
        print(f"✓ BUENO: Hay algo de paralelismo")
    else:
        print(f"✗ POBRE: Posible congelación o serialización")

    print()

    return successes == num_users


async def main():
    """Ejecuta simulaciones con diferentes cargas."""

    # Test 1: 3 usuarios
    ok1 = await simulate_concurrent_load(num_users=3, tipo="licitaciones")
    await asyncio.sleep(2)

    # Test 2: 7 usuarios (el objetivo del fix)
    ok2 = await simulate_concurrent_load(num_users=7, tipo="licitaciones")
    await asyncio.sleep(2)

    # Test 3: 10 usuarios (stress test)
    ok3 = await simulate_concurrent_load(num_users=10, tipo="licitaciones")

    # Resumen final
    print(f"\n{'='*60}")
    print(f"RESUMEN FINAL")
    print(f"{'='*60}")
    print(f"Test 1 (3 usuarios):  {'✓ PASS' if ok1 else '✗ FAIL'}")
    print(f"Test 2 (7 usuarios):  {'✓ PASS' if ok2 else '✗ FAIL'}")
    print(f"Test 3 (10 usuarios): {'✓ PASS' if ok3 else '✗ FAIL'}")
    print(f"{'='*60}\n")

    if ok1 and ok2:
        print("✓ Todos los tests pasaron. run_in_executor está funcionando.")
        return True
    else:
        print("✗ Algunos tests fallaron. Revisar logs.")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
