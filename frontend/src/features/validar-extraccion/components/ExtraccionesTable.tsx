import { useState } from 'react'
import { Link } from '@tanstack/react-router'
import clsx from 'clsx'
import type { DocumentType, ExtraccionResumen } from '@/lib/api/extracciones'
import { ESTADO_META, esEstadoValidable, estadoDerivadoDe, estadoGrupoDe } from '../estadoExtraccion'
import { grupoIdDe } from '../ValidarExtraccionListado'

interface ExtraccionesTableProps {
  extracciones: ExtraccionResumen[]
  // T3 -- lista COMPLETA de extracciones de la tab activa, sin el filtro de
  // chip de estado aplicado (`ValidarExtraccionListado.filasPorTipo`). Un
  // grupo se muestra si CUALQUIER miembro matchea el chip activo (está en
  // `extracciones`), pero al expandirlo hay que poder mostrar TODOS sus
  // miembros -- incluidos los que el chip dejó afuera. Por defecto usa
  // `extracciones` (comportamiento sin grupos, sin cambios).
  extraccionesDelTipo?: ExtraccionResumen[]
  // T2 -- Agrupar/Desagrupar y los checkboxes de selección solo tienen
  // sentido en la tab Orden de compra (decisión de usuario, 2026-09-26); el
  // resto de las tabs renderiza la misma tabla sin esas columnas activas.
  tipoActivo: DocumentType
  seleccionados?: Set<string>
  onAlternarSeleccion?: (id: string) => void
  // D13/7.13 -- override OPTIMISTA post-agrupar/desagrupar de esta sesión (ver
  // grupoIdDe); cuando no hay override se usa extraccion.grupo_id, el dato
  // real que ya devuelve GET /extracciones.
  gruposLocales?: Record<string, string | null>
}

/** T3 -- una entrada de la tabla es o bien una fila suelta (sin grupo), o
 * bien UN encabezado que representa a todo un grupo (2+ filas que comparten
 * `grupoIdDe`). Reemplaza el viejo tag "Grupo" por fila (D13/7.13): con 2+
 * grupos en pantalla ese tag no distinguía a qué grupo pertenecía cada fila
 * (pedido de usuario, 2026-09-27, antes del push). */
type EntradaTabla =
  | { tipo: 'individual'; extraccion: ExtraccionResumen }
  | { tipo: 'grupo'; grupoId: string; miembros: ExtraccionResumen[] }

/** Arma las entradas a renderizar a partir de las filas visibles (ya con el
 * chip de estado aplicado). Cada grupo aparece UNA sola vez, en la posición
 * de su primer miembro visible (que ya viene ordenado por `created_at DESC`
 * desde el listado, ver `ValidarExtraccionListado`), pero con la lista
 * COMPLETA de miembros (resuelta contra `extraccionesDelTipo`) para que
 * expandirlo muestre el grupo entero, no solo lo que matchea el filtro. */
function construirEntradas(
  extracciones: ExtraccionResumen[],
  extraccionesDelTipo: ExtraccionResumen[],
  gruposLocales: Record<string, string | null>,
): EntradaTabla[] {
  const entradas: EntradaTabla[] = []
  const gruposYaAgregados = new Set<string>()

  for (const extraccion of extracciones) {
    const grupoId = grupoIdDe(extraccion, gruposLocales)

    if (grupoId === null) {
      entradas.push({ tipo: 'individual', extraccion })
      continue
    }

    if (gruposYaAgregados.has(grupoId)) continue
    gruposYaAgregados.add(grupoId)

    const miembros = extraccionesDelTipo.filter(
      (candidata) => grupoIdDe(candidata, gruposLocales) === grupoId,
    )
    entradas.push({ tipo: 'grupo', grupoId, miembros })
  }

  return entradas
}

/** T2 -- celda de acción por fila: "Revisar" para procesado/procesado con
 * advertencias (cualquier tipo); "Matching" solo para una OC ya validada con
 * `orden_compra_id` resuelto (D11); sin acción para procesando/error, y para
 * una fila validada sin OC resuelta o que no es orden_compra (informativa). */
function AccionCelda({ extraccion }: { extraccion: ExtraccionResumen }) {
  const estado = estadoDerivadoDe(extraccion)

  if (esEstadoValidable(estado)) {
    return (
      <Link
        to="/validar-extraccion/$extractionId"
        params={{ extractionId: extraccion.id }}
        search={{ rowCount: extraccion.row_count }}
        className="text-sm font-medium text-accent hover:underline"
      >
        Revisar
      </Link>
    )
  }

  if (estado === 'validada' && extraccion.document_type === 'orden_compra' && extraccion.orden_compra_id) {
    return (
      <Link
        to="/ordenes-compra/$ordenCompraId/matching"
        params={{ ordenCompraId: extraccion.orden_compra_id }}
        className="text-sm font-medium text-accent hover:underline"
      >
        Matching
      </Link>
    )
  }

  return <span className="text-xs text-slate-400">—</span>
}

interface FilaExtraccionProps {
  extraccion: ExtraccionResumen
  tipoActivo: DocumentType
  seleccionados?: Set<string>
  onAlternarSeleccion?: (id: string) => void
  // T3 -- true para una fila renderizada como miembro (anidada) dentro de un
  // grupo expandido: agrega sangría y ya no lleva el tag "Grupo" (ningún
  // otro camino lo lleva tampoco, T3 lo elimina por completo).
  indentada?: boolean
}

/** Fila de una única extracción -- reutilizada tanto para filas sueltas
 * (sin grupo) como para cada miembro de un grupo expandido (T3). */
function FilaExtraccion({ extraccion, tipoActivo, seleccionados, onAlternarSeleccion, indentada }: FilaExtraccionProps) {
  const estado = estadoDerivadoDe(extraccion)
  const meta = ESTADO_META[estado]
  // D13 -- solo orden_compra en estado validable (no procesando, no
  // error, no ya validada) se puede tildar para agrupar/desagrupar.
  const esSeleccionable =
    tipoActivo === 'orden_compra' && extraccion.document_type === 'orden_compra' && esEstadoValidable(estado)

  return (
    <tr className="border-b border-slate-100">
      <td className="py-2">
        {esSeleccionable && onAlternarSeleccion && (
          <input
            type="checkbox"
            aria-label={`Seleccionar ${extraccion.source_filename}`}
            checked={seleccionados?.has(extraccion.id) ?? false}
            onChange={() => onAlternarSeleccion(extraccion.id)}
          />
        )}
      </td>
      <td className={clsx('max-w-xs truncate py-2 text-slate-900', indentada && 'pl-6 text-slate-600')}>
        {extraccion.source_filename}
      </td>
      <td className="py-2">
        <span
          className={clsx(
            'flex w-fit items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium',
            meta.badgeClass,
          )}
        >
          {meta.pulso && (
            <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-amber-500 motion-safe:animate-pulse" />
          )}
          {meta.label}
        </span>
        {estado === 'error' && (
          <p className="mt-1 text-xs text-red-600">{extraccion.error_msg ?? 'No se pudo procesar el documento.'}</p>
        )}
      </td>
      <td className="py-2 text-slate-600">{extraccion.row_count}</td>
      <td className="py-2 text-slate-600">{extraccion.proceso_comercial_nombre ?? '—'}</td>
      <td className="py-2 text-slate-600">{extraccion.subido_por_nombre ?? '—'}</td>
      <td className="py-2 text-slate-500">{new Date(extraccion.created_at).toLocaleDateString('es-AR')}</td>
      <td className="py-2 text-right">
        <AccionCelda extraccion={extraccion} />
      </td>
    </tr>
  )
}

interface FilaGrupoProps {
  miembros: ExtraccionResumen[]
  seleccionados?: Set<string>
  onAlternarSeleccion?: (id: string) => void
  tipoActivo: DocumentType
  expandido: boolean
  onAlternarExpandido: () => void
}

/** T3 -- encabezado colapsable de un grupo (colapsado por defecto). El
 * checkbox del encabezado selecciona/deselecciona TODOS los miembros
 * seleccionables (mismo criterio que una fila individual: orden_compra +
 * estado validable); los checkboxes de cada miembro siguen existiendo al
 * expandir, para permitir desagrupar solo una parte (pedido de usuario,
 * 2026-09-27). */
function FilaGrupo({
  miembros,
  seleccionados,
  onAlternarSeleccion,
  tipoActivo,
  expandido,
  onAlternarExpandido,
}: FilaGrupoProps) {
  const estadoGrupo = estadoGrupoDe(miembros.map((miembro) => estadoDerivadoDe(miembro)))
  const meta = estadoGrupo ? ESTADO_META[estadoGrupo] : null

  const miembrosSeleccionables = miembros.filter(
    (miembro) =>
      tipoActivo === 'orden_compra' &&
      miembro.document_type === 'orden_compra' &&
      esEstadoValidable(estadoDerivadoDe(miembro)),
  )
  const todosSeleccionados =
    miembrosSeleccionables.length > 0 &&
    miembrosSeleccionables.every((miembro) => seleccionados?.has(miembro.id) ?? false)
  const algunoSeleccionado = miembrosSeleccionables.some((miembro) => seleccionados?.has(miembro.id) ?? false)

  function alternarTodos() {
    if (!onAlternarSeleccion) return
    // `onAlternarSeleccion` solo TOGGLEA un id -- para simular "tildar/
    // destildar todos" se invoca solo sobre los miembros que van a cambiar
    // de estado (los ya tildados si se está destildando, los no tildados si
    // se está tildando), nunca sobre los dos.
    const objetivo = todosSeleccionados
      ? miembrosSeleccionables.filter((miembro) => seleccionados?.has(miembro.id))
      : miembrosSeleccionables.filter((miembro) => !(seleccionados?.has(miembro.id) ?? false))
    for (const miembro of objetivo) onAlternarSeleccion(miembro.id)
  }

  const nombresArchivos = miembros.map((miembro) => miembro.source_filename).join(', ')
  // T3 -- acción del encabezado: mismo criterio que `AccionCelda`, pero
  // resuelto sobre el PRIMER miembro que corresponda (la pantalla de
  // detalle ya carga el grupo entero a partir de cualquier miembro).
  const miembroValidable = miembros.find((miembro) => esEstadoValidable(estadoDerivadoDe(miembro)))
  const miembroConMatching = miembros.find(
    (miembro) =>
      estadoDerivadoDe(miembro) === 'validada' &&
      miembro.document_type === 'orden_compra' &&
      miembro.orden_compra_id,
  )

  return (
    <>
      <tr className="border-b border-slate-100 bg-slate-50">
        <td className="py-2">
          {miembrosSeleccionables.length > 0 && onAlternarSeleccion && (
            <input
              type="checkbox"
              aria-label={`Seleccionar grupo (${miembros.length} archivos)`}
              checked={todosSeleccionados}
              ref={(elemento) => {
                if (elemento) elemento.indeterminate = algunoSeleccionado && !todosSeleccionados
              }}
              onChange={alternarTodos}
            />
          )}
        </td>
        <td className="max-w-xs py-2 text-slate-900">
          <div className="flex items-start gap-2">
            <button
              type="button"
              aria-expanded={expandido}
              aria-label={expandido ? 'Contraer grupo' : 'Expandir grupo'}
              onClick={onAlternarExpandido}
              className="mt-0.5 shrink-0 text-slate-400 hover:text-slate-600"
            >
              {expandido ? '▾' : '▸'}
            </button>
            <div className="min-w-0">
              <p className="text-sm font-medium">Grupo · {miembros.length} archivos</p>
              <p className="truncate text-xs text-slate-500" title={nombresArchivos}>
                {nombresArchivos}
              </p>
            </div>
          </div>
        </td>
        <td className="py-2">
          {meta ? (
            <span
              className={clsx(
                'flex w-fit items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium',
                meta.badgeClass,
              )}
            >
              {meta.pulso && (
                <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-amber-500 motion-safe:animate-pulse" />
              )}
              {meta.label}
            </span>
          ) : (
            <span className="text-slate-400">—</span>
          )}
        </td>
        <td className="py-2 text-slate-400">—</td>
        <td className="py-2 text-slate-400">—</td>
        <td className="py-2 text-slate-400">—</td>
        <td className="py-2 text-slate-400">—</td>
        <td className="py-2 text-right">
          {miembroValidable ? (
            <Link
              to="/validar-extraccion/$extractionId"
              params={{ extractionId: miembroValidable.id }}
              search={{ rowCount: miembroValidable.row_count }}
              className="text-sm font-medium text-accent hover:underline"
            >
              Revisar
            </Link>
          ) : miembroConMatching ? (
            <Link
              to="/ordenes-compra/$ordenCompraId/matching"
              params={{ ordenCompraId: miembroConMatching.orden_compra_id as string }}
              className="text-sm font-medium text-accent hover:underline"
            >
              Matching
            </Link>
          ) : (
            <span className="text-xs text-slate-400">—</span>
          )}
        </td>
      </tr>
      {expandido &&
        miembros.map((miembro) => (
          <FilaExtraccion
            key={miembro.id}
            extraccion={miembro}
            tipoActivo={tipoActivo}
            seleccionados={seleccionados}
            onAlternarSeleccion={onAlternarSeleccion}
            indentada
          />
        ))}
    </>
  )
}

export function ExtraccionesTable({
  extracciones,
  extraccionesDelTipo,
  tipoActivo,
  seleccionados,
  onAlternarSeleccion,
  gruposLocales = {},
}: ExtraccionesTableProps) {
  // T3 -- estado de expansión por grupo, local al componente y no
  // persistido (decisión de usuario, 2026-09-27): sobrevive a un refetch de
  // la misma sesión (el componente no se desmonta), pero no a un reload.
  const [gruposExpandidos, setGruposExpandidos] = useState<Record<string, boolean>>({})

  if (extracciones.length === 0) {
    return <p className="text-sm text-slate-500">No hay extracciones para mostrar.</p>
  }

  function alternarExpandido(grupoId: string) {
    setGruposExpandidos((previo) => ({ ...previo, [grupoId]: !previo[grupoId] }))
  }

  const entradas = construirEntradas(extracciones, extraccionesDelTipo ?? extracciones, gruposLocales)

  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-slate-200 text-left text-slate-500">
          <th className="py-2 font-medium" />
          <th className="py-2 font-medium">Documento</th>
          <th className="py-2 font-medium">Estado</th>
          <th className="py-2 font-medium">Filas</th>
          <th className="py-2 font-medium">Proceso comercial</th>
          <th className="py-2 font-medium">Cargado por</th>
          <th className="py-2 font-medium">Cargado</th>
          <th className="py-2 font-medium" />
        </tr>
      </thead>
      <tbody>
        {entradas.map((entrada) =>
          entrada.tipo === 'individual' ? (
            <FilaExtraccion
              key={entrada.extraccion.id}
              extraccion={entrada.extraccion}
              tipoActivo={tipoActivo}
              seleccionados={seleccionados}
              onAlternarSeleccion={onAlternarSeleccion}
            />
          ) : (
            <FilaGrupo
              key={entrada.grupoId}
              miembros={entrada.miembros}
              tipoActivo={tipoActivo}
              seleccionados={seleccionados}
              onAlternarSeleccion={onAlternarSeleccion}
              expandido={gruposExpandidos[entrada.grupoId] ?? false}
              onAlternarExpandido={() => alternarExpandido(entrada.grupoId)}
            />
          ),
        )}
      </tbody>
    </table>
  )
}
