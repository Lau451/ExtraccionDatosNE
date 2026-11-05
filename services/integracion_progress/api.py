"""Fachada de `services/integracion_progress/` (docs/arquitectura/integracion-progress.md;
mismo criterio que `services/terceros/api.py` y `services/pcp/api.py`).

`integracion_progress` es el único dueño del intercambio de archivos con Progress 9.1D:
solo este módulo conoce la carpeta de intercambio, el nombre de los archivos, el
encoding y la escritura atómica. Los demás módulos importan EXCLUSIVAMENTE este
archivo — nunca `salida/` ni otro submódulo interno. Este archivo no define lógica
propia: reexporta lo que los módulos de negocio necesitan.

Salida (nosotros → Progress): `presupuestacion/oc_export` arma las filas de la OC y
le delega a esta fachada la carpeta (`carpeta_oc`), el nombre (`construir_nombre_oc`),
la escritura (`escribir_csv`, que recibe encabezados + filas y no sabe nada de las
columnas de una OC) y la compensación (`borrar_archivo`).

Entrada (Progress → nosotros): `presupuestacion/main.py` corre
`recepcion_automatica_periodica` en su lifespan (S4 automática); se apaga sola si
falta la carpeta o el tenant.

`tests/integracion_progress/test_dependencias.py` verifica con `ast` que este módulo
solo importa `services.shared` (más las fachadas destino que se habiliten) y que
fuera de él nadie importa otra cosa que `services.integracion_progress.api`.
"""

from services.integracion_progress.recepcion.automatica import (
    escanear_si_configurado as escanear_entrada_si_configurado,
)
from services.integracion_progress.recepcion.automatica import (
    recepcion_periodica as recepcion_automatica_periodica,
)
from services.integracion_progress.salida.escritor import (
    borrar_archivo,
    carpeta_oc,
    escribir_csv,
)
from services.integracion_progress.salida.escritor import (
    construir_nombre as construir_nombre_oc,
)

__all__ = [
    # salida — OC
    "carpeta_oc",
    "construir_nombre_oc",
    "escribir_csv",
    "borrar_archivo",
    # entrada — recepción automática desde la carpeta
    "escanear_entrada_si_configurado",
    "recepcion_automatica_periodica",
]
