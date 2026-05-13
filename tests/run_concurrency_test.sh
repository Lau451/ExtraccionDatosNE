#!/bin/bash

# Script para ejecutar el test de concurrencia

echo "=================================================="
echo "TEST DE CONCURRENCIA - run_in_executor"
echo "=================================================="
echo ""

# Verificar que Python esté disponible
if ! command -v python &> /dev/null; then
    echo "✗ Python no encontrado. Instálalo primero."
    exit 1
fi

# Verificar que httpx esté instalado
if ! python -c "import httpx" 2>/dev/null; then
    echo "✗ httpx no está instalado."
    echo "Instalando: pip install httpx"
    pip install httpx
fi

# Verificar que la app esté corriendo
echo "Verificando que la app esté corriendo en http://localhost:8000..."
if ! curl -s http://localhost:8000/ > /dev/null 2>&1; then
    echo ""
    echo "✗ La app NO está corriendo en http://localhost:8000"
    echo ""
    echo "Para iniciar la app, abre otra terminal y corre:"
    echo "  cd $(pwd)"
    echo "  python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
    echo ""
    echo "O usa el script run.bat:"
    echo "  .\scripts\run.bat"
    echo ""
    exit 1
fi

echo "✓ App está corriendo"
echo ""

# Ejecutar el test
echo "Iniciando test de concurrencia..."
python test_concurrency.py

exit_code=$?

echo ""
if [ $exit_code -eq 0 ]; then
    echo "✓ Test completado exitosamente"
else
    echo "✗ Test falló"
fi

exit $exit_code
