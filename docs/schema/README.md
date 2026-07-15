# Schema de referencia — `services/presupuestacion`

`extractor_final.sql` y `rls_final.sql` son el DDL v15 y las políticas RLS
tal como quedaron aplicadas en el proyecto Supabase de test
(`grnamollopxdlstcpxhc`). Se agregan acá como **documentación de
referencia**, no como migraciones ejecutables: ya están corridas contra la
base.

Objetivo: que constraints, defaults y políticas de RLS que no son evidentes
desde el código de `services/presupuestacion/` (por ejemplo checks como
`ck_proc_cotizacion_sin_seguimiento` en `procesos_comerciales`) se puedan
consultar leyendo estos archivos en vez de descubrirlos por prueba y error
contra un 500 en runtime.

Si el schema real cambia, actualizar estos archivos con la versión nueva —
no hay generación automática todavía.
