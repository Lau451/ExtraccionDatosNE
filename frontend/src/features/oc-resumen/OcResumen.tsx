import { useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { useAuth } from '@/features/auth/AuthContext'
import { formatearPrecio } from '@/features/oc-matching/formatearPrecio'
import { obtenerOcResumen, type EstadoVinculo, type OcResumenOut, type RenglonResumen } from '@/lib/api/ocResumen'
import { ApiError } from '@/lib/api/presupuestacion'
import { fechaLegible } from '@/lib/fechas'
import { OC_RESUMEN_ACCIONES_ROLES, puedeRol } from './roles'

const ETIQUETA_VINCULO: Record<EstadoVinculo, { texto: string; clase: string }> = {
  confirmado: { texto: 'Confirmado', clase: 'bg-emerald-50 text-emerald-700' },
  pendiente: { texto: 'Pendiente', clase: 'bg-amber-50 text-amber-700' },
  sin_presupuesto: { texto: 'Sin presupuesto', clase: 'bg-slate-100 text-slate-600' },
}

// 'YYYY-MM-DD' se parte a mano: new Date('YYYY-MM-DD') parsea como UTC y en
// Argentina (UTC-3) mostraría el día anterior.
function formatearFecha(iso: string | null): string {
  if (!iso) return 'Sin fecha'
  const [anio, mes, dia] = iso.split('-')
  return `${dia}/${mes}/${anio}`
}

function formatearCantidad(cantidad: number): string {
  return cantidad.toLocaleString('es-AR')
}

function formatearMonto(monto: number | null): string {
  return monto === null ? '—' : `$${formatearPrecio(monto)}`
}

// El monto del encabezado puede venir null: se cae a la suma de los renglones.
function totalOc(resumen: OcResumenOut): number {
  if (resumen.monto_total !== null) return resumen.monto_total
  return resumen.renglones.reduce((suma, renglon) => suma + (renglon.monto_total ?? 0), 0)
}

function Dato({ etiqueta, children }: { etiqueta: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-slate-500">{etiqueta}</dt>
      <dd className="mt-0.5 text-sm text-slate-900">{children}</dd>
    </div>
  )
}

function BannerExportada({ exportacion }: { exportacion: NonNullable<OcResumenOut['exportacion']> }) {
  return (
    <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
      <p>
        Exportada a Progress el {fechaLegible(exportacion.exportado_at)}
        {exportacion.exportado_por_nombre ? ` por ${exportacion.exportado_por_nombre}` : ''}.
      </p>
      <p>Archivo: {exportacion.archivo_exportado}</p>
    </div>
  )
}

function TablaRenglones({ renglones, total }: { renglones: RenglonResumen[]; total: number }) {
  return (
    <section>
      <h2 className="mb-3 text-lg font-semibold text-slate-900">Renglones</h2>
      <div className="overflow-x-auto rounded-md border border-slate-200 bg-white">
        <table aria-label="Renglones" className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-3 py-2">Renglón</th>
              <th className="px-3 py-2">Descripción</th>
              <th className="px-3 py-2">Producto</th>
              <th className="px-3 py-2 text-right">Cantidad</th>
              <th className="px-3 py-2 text-right">Precio unitario</th>
              <th className="px-3 py-2 text-right">Total</th>
              <th className="px-3 py-2">Vínculo</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {renglones.map((renglon) => {
              const vinculo = ETIQUETA_VINCULO[renglon.estado_vinculo]
              return (
                <tr key={renglon.oc_item_id}>
                  <td className="px-3 py-2 tabular-nums">
                    {renglon.numero_renglon_documento ?? renglon.numero_renglon}
                  </td>
                  <td className="px-3 py-2 text-slate-900">{renglon.descripcion}</td>
                  <td className="px-3 py-2 text-slate-700">
                    {renglon.producto
                      ? `${renglon.producto.codigo_interno ? `${renglon.producto.codigo_interno} · ` : ''}${renglon.producto.nombre}`
                      : '—'}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">{formatearCantidad(renglon.cantidad)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {renglon.precio_unitario === null ? '—' : `$${formatearPrecio(renglon.precio_unitario)}`}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">{formatearMonto(renglon.monto_total)}</td>
                  <td className="px-3 py-2">
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${vinculo.clase}`}>
                      {vinculo.texto}
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-right text-sm font-semibold text-slate-900">
        Total: <span data-testid="total-oc" className="tabular-nums">{formatearMonto(total)}</span>
      </p>
    </section>
  )
}

function SeccionEntregas({ resumen }: { resumen: OcResumenOut }) {
  const descripcionPorItem = new Map(resumen.renglones.map((renglon) => [renglon.oc_item_id, renglon.descripcion]))
  return (
    <section>
      <h2 className="mb-3 text-lg font-semibold text-slate-900">Entregas planificadas</h2>
      {resumen.entregas.length === 0 ? (
        <p className="text-sm text-slate-500">Sin entregas planificadas</p>
      ) : (
        <ul className="space-y-2">
          {resumen.entregas.map((entrega) => (
            <li key={entrega.numero_entrega} className="rounded-md border border-slate-200 bg-white p-3">
              <div className="flex flex-wrap items-baseline gap-x-3 text-sm">
                <span className="font-medium text-slate-900">Entrega {entrega.numero_entrega}</span>
                <span className="text-slate-600">{formatearFecha(entrega.fecha_entrega_planificada)}</span>
                <span className="text-slate-500">{entrega.estado}</span>
              </div>
              <ul className="mt-2 space-y-1 text-sm text-slate-700">
                {entrega.items.map((item) => (
                  <li key={item.oc_item_id} className="flex justify-between gap-4">
                    <span>{descripcionPorItem.get(item.oc_item_id) ?? 'Renglón desconocido'}</span>
                    <span className="tabular-nums">{formatearCantidad(item.cantidad_planificada)}</span>
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

interface Props {
  ordenCompraId: string
}

export function OcResumen({ ordenCompraId }: Props) {
  const { perfil } = useAuth()
  const query = useQuery({
    queryKey: ['oc-resumen', ordenCompraId],
    queryFn: () => obtenerOcResumen(ordenCompraId),
  })

  if (query.isPending) {
    return <p className="p-6 text-sm text-slate-500">Cargando orden de compra…</p>
  }

  if (query.isError) {
    const mensaje =
      query.error instanceof ApiError ? query.error.message : 'No se pudo cargar la orden de compra.'
    return (
      <p role="alert" className="p-6 text-sm text-red-700">
        {mensaje}
      </p>
    )
  }

  const resumen = query.data
  const mostrarAcciones = puedeRol(perfil?.rol, OC_RESUMEN_ACCIONES_ROLES)

  return (
    <div className="mx-auto max-w-5xl space-y-6 px-6 py-10">
      <div className="rounded-md border border-slate-200 bg-white p-4">
        <div className="flex flex-wrap items-baseline justify-between gap-3">
          <h1 className="text-xl font-semibold text-slate-900">
            {resumen.numero_oc}
            {resumen.version_numero !== null ? (
              <span className="ml-2 text-sm font-normal text-slate-500">v{resumen.version_numero}</span>
            ) : null}
          </h1>
          {mostrarAcciones ? (
            <div className="flex gap-3 text-sm">
              <Link
                to="/ordenes-compra/$ordenCompraId/matching"
                params={{ ordenCompraId }}
                className="text-accent hover:underline"
              >
                Ver matching
              </Link>
              <Link
                to="/ordenes-compra/$ordenCompraId/entregas"
                params={{ ordenCompraId }}
                className="text-accent hover:underline"
              >
                Planificar entregas
              </Link>
            </div>
          ) : null}
        </div>
        <dl className="mt-4 grid gap-4 sm:grid-cols-2">
          <Dato etiqueta="Cliente">
            {resumen.cliente
              ? resumen.cliente.cuit
                ? `${resumen.cliente.razon_social} — CUIT ${resumen.cliente.cuit}`
                : resumen.cliente.razon_social
              : 'Sin cliente'}
          </Dato>
          <Dato etiqueta="Estado">{resumen.estado}</Dato>
          <Dato etiqueta="Fecha de emisión">{formatearFecha(resumen.fecha_emision)}</Dato>
          <Dato etiqueta="Entrega estimada">{formatearFecha(resumen.fecha_entrega_estimada)}</Dato>
          <Dato etiqueta="Dirección de entrega">{resumen.direccion_entrega ?? '—'}</Dato>
          <Dato etiqueta="Notas">{resumen.notas ?? '—'}</Dato>
        </dl>
      </div>

      {resumen.exportacion ? <BannerExportada exportacion={resumen.exportacion} /> : null}

      <TablaRenglones renglones={resumen.renglones} total={totalOc(resumen)} />
      <SeccionEntregas resumen={resumen} />
    </div>
  )
}
