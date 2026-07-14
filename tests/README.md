# Concurrent Load Testing Suite

Validación de concurrencia para `run_in_executor()` implementado en commit e0d6dbc.

## Files

- **test_concurrency.py** — Script principal de carga concurrente
- **create_test_pdf.py** — Genera PDF de prueba mínimo válido
- **run_concurrency_test.sh** — Script helper para ejecutar (Linux/Mac)
- **test_file.pdf** — Documento de prueba (generado automáticamente)

## Quick Start

**Terminal 1: Inicia la app**
```bash
cd ..
python -m uvicorn services.extraccion.main:app --host 0.0.0.0 --port 8000
```

**Terminal 2: Corre los tests**
```bash
cd test
python test_concurrency.py
```

## What It Tests

- 3 usuarios simultáneos (baseline)
- 7 usuarios simultáneos (target del fix)
- 10 usuarios simultáneos (stress test)

Cada test mide:
- Tiempo total de ejecución
- Eficiencia de paralelismo (% de paralelismo real)
- Tasa de éxito/fallo

## Expected Results

✅ Todos los tests deberían pasar con:
- 3 users: ~45s, 295% efficiency
- 7 users: ~28s, 501% efficiency  
- 10 users: ~30s, 759% efficiency

❌ Si hay 503 errors: Gemini API rate limit alcanzado (upgrade a API paga)

## How It Works

El script simula múltiples usuarios HTTP concurrentes que suben archivos. Si `run_in_executor()` está funcionando correctamente, el tiempo total debería ser ~3x menor que si se procesaran secuencialmente.

Eficiencia > 300% = Verdadero paralelismo (no espera bloqueante)

## Manual Test

Para correr manualmente sin script:
```bash
# Terminal 1: App
python -m uvicorn services.extraccion.main:app --host 0.0.0.0 --port 8000

# Terminal 2+: Abre 7 tabs del navegador y sube archivos simultáneamente
# http://localhost:8000/upload?tipo=licitaciones
```

Sin `run_in_executor()`: Se congela
Con `run_in_executor()`: Fluido y responsivo
