import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { OcResumenOut } from '@/lib/api/ocResumen'
import { ApiError } from '@/lib/api/presupuestacion'

const rolActual = vi.hoisted(() => ({ valor: 'comercial' as string }))

vi.mock('@tanstack/react-router', () => ({
  Link: ({
    children,
    to,
    params,
    className,
  }: {
    children?: React.ReactNode
    to: string
    params?: Record<string, string>
    className?: string
  }) => (
    <a href={to.replace('$ordenCompraId', params?.ordenCompraId ?? '')} className={className}>
      {children}
    </a>
  ),
}))
vi.mock('@/features/auth/AuthContext', () => ({
  useAuth: () => ({ perfil: { rol: rolActual.valor, nombre: 'Test' } }),
}))
vi.mock('@/lib/api/ocResumen', () => ({ obtenerOcResumen: vi.fn() }))

import { obtenerOcResumen } from '@/lib/api/ocResumen'
import { OcResumen } from './OcResumen'

function renderVista() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <OcResumen ordenCompraId="oc-1" />
    </QueryClientProvider>,
  )
}

function resumen(o: Partial<OcResumenOut> = {}): OcResumenOut {
  return {
    orden_compra_id: 'oc-1',
    numero_oc: 'OC-100',
    cliente: { razon_social: 'Hospital Norte', cuit: '30123456789' },
    fecha_emision: '2026-10-01',
    fecha_entrega_estimada: '2026-11-20',
    direccion_entrega: 'Av. Siempreviva 742',
    notas: 'Entregar por la mañana',
    estado: 'confirmada',
    version_numero: 2,
    monto_total: 5000,
    exportacion: null,
    renglones: [
      {
        oc_item_id: 'item-1',
        numero_renglon: 1,
        numero_renglon_documento: '10',
        descripcion: 'Ibuprofeno 400mg',
        producto: { codigo_interno: 'P-1', nombre: 'Ibuprofeno' },
        cantidad: 100,
        precio_unitario: 12.5,
        monto_total: 1250,
        estado_vinculo: 'confirmado',
      },
      {
        oc_item_id: 'item-2',
        numero_renglon: 2,
        numero_renglon_documento: null,
        descripcion: 'Gasas estériles',
        producto: null,
        cantidad: 5,
        precio_unitario: 100,
        monto_total: 500,
        estado_vinculo: 'pendiente',
      },
    ],
    entregas: [],
    ...o,
  }
}

describe('OcResumen', () => {
  beforeEach(() => {
    vi.mocked(obtenerOcResumen).mockReset()
    rolActual.valor = 'comercial'
  })

  it('muestra estado de carga', () => {
    vi.mocked(obtenerOcResumen).mockReturnValue(new Promise(() => {}))
    renderVista()
    expect(screen.getByText(/Cargando/)).toBeTruthy()
  })

  it('muestra el mensaje del backend ante un error', async () => {
    vi.mocked(obtenerOcResumen).mockRejectedValue(new ApiError('Orden de compra no encontrada', 404))
    renderVista()
    expect(await screen.findByText(/Orden de compra no encontrada/)).toBeTruthy()
  })

  it('renderiza encabezado y cliente con CUIT', async () => {
    vi.mocked(obtenerOcResumen).mockResolvedValue(resumen())
    renderVista()

    expect(await screen.findByRole('heading', { name: /OC-100/ })).toBeTruthy()
    expect(screen.getByText(/v2/)).toBeTruthy()
    expect(screen.getByText('Hospital Norte — CUIT 30123456789')).toBeTruthy()
    expect(screen.getByText('Av. Siempreviva 742')).toBeTruthy()
    expect(screen.getByText('Entregar por la mañana')).toBeTruthy()
    expect(screen.getByText('01/10/2026')).toBeTruthy()
    expect(screen.getByText('20/11/2026')).toBeTruthy()
    expect(screen.getByText('confirmada')).toBeTruthy()
  })

  it('muestra el banner de exportación solo si la OC fue exportada', async () => {
    vi.mocked(obtenerOcResumen).mockResolvedValue(resumen())
    const { unmount } = renderVista()
    await screen.findByRole('heading', { name: /OC-100/ })
    expect(screen.queryByText(/Exportada a Progress/)).toBeNull()
    unmount()

    vi.mocked(obtenerOcResumen).mockResolvedValue(
      resumen({
        exportacion: {
          exportado_at: '2026-10-02T10:00:00Z',
          exportado_por: 'u1',
          exportado_por_nombre: 'Ana Pérez',
          archivo_exportado: 'oc-100.txt',
        },
      }),
    )
    renderVista()
    expect(await screen.findByText(/Exportada a Progress/)).toBeTruthy()
    expect(screen.getByText(/por Ana Pérez/)).toBeTruthy()
    expect(screen.getByText(/oc-100\.txt/)).toBeTruthy()
  })

  it('lista renglones con producto, o "—" cuando no hay', async () => {
    vi.mocked(obtenerOcResumen).mockResolvedValue(resumen())
    renderVista()

    const tabla = await screen.findByRole('table', { name: 'Renglones' })
    expect(within(tabla).getByText('Ibuprofeno 400mg')).toBeTruthy()
    expect(within(tabla).getByText('P-1 · Ibuprofeno')).toBeTruthy()
    expect(within(tabla).getByText('Confirmado')).toBeTruthy()
    expect(within(tabla).getByText('Pendiente')).toBeTruthy()
    const filaGasas = within(tabla).getByText('Gasas estériles').closest('tr')!
    expect(within(filaGasas).getByText('—')).toBeTruthy()
  })

  it('usa el monto_total del encabezado con formato argentino', async () => {
    vi.mocked(obtenerOcResumen).mockResolvedValue(resumen({ monto_total: 1234567.89 }))
    renderVista()
    expect((await screen.findByTestId('total-oc')).textContent).toBe('$ 1.234.567,89')
    expect(screen.queryByText(/está incompleto/)).toBeNull()
  })

  it('formatea precio unitario y total de cada renglón', async () => {
    vi.mocked(obtenerOcResumen).mockResolvedValue(resumen())
    renderVista()
    const tabla = await screen.findByRole('table', { name: 'Renglones' })
    expect(within(tabla).getByText('$ 12,50')).toBeTruthy()
    expect(within(tabla).getByText('$ 1.250,00')).toBeTruthy()
  })

  it('sin monto_total en el encabezado suma los renglones', async () => {
    vi.mocked(obtenerOcResumen).mockResolvedValue(resumen({ monto_total: null }))
    renderVista()
    expect((await screen.findByTestId('total-oc')).textContent).toBe('$ 1.750,00')
    expect(screen.queryByText(/está incompleto/)).toBeNull()
  })

  it('avisa que el total está incompleto si algún renglón no tiene precio', async () => {
    const base = resumen({ monto_total: null })
    base.renglones[1] = { ...base.renglones[1], precio_unitario: null, monto_total: null }
    vi.mocked(obtenerOcResumen).mockResolvedValue(base)
    renderVista()
    expect((await screen.findByTestId('total-oc')).textContent).toBe('$ 1.250,00')
    expect(screen.getByText('Sin precio en 1 renglón: el total está incompleto.')).toBeTruthy()
  })

  it('si ningún renglón tiene precio muestra "—" y el aviso en plural', async () => {
    const base = resumen({ monto_total: null })
    base.renglones = base.renglones.map((r) => ({ ...r, precio_unitario: null, monto_total: null }))
    vi.mocked(obtenerOcResumen).mockResolvedValue(base)
    renderVista()
    expect((await screen.findByTestId('total-oc')).textContent).toBe('—')
    expect(screen.getByText('Sin precio en 2 renglones: el total está incompleto.')).toBeTruthy()
  })

  it('muestra "Sin entregas planificadas" sin entregas', async () => {
    vi.mocked(obtenerOcResumen).mockResolvedValue(resumen())
    renderVista()
    expect(await screen.findByText('Sin entregas planificadas')).toBeTruthy()
  })

  it('mapea los items de cada entrega a la descripción del renglón', async () => {
    vi.mocked(obtenerOcResumen).mockResolvedValue(
      resumen({
        entregas: [
          {
            numero_entrega: 1,
            fecha_entrega_planificada: '2026-11-05',
            estado: 'pendiente',
            items: [
              { oc_item_id: 'item-1', cantidad_planificada: 60 },
              { oc_item_id: 'item-2', cantidad_planificada: 5 },
            ],
          },
          { numero_entrega: 2, fecha_entrega_planificada: null, estado: 'pendiente', items: [{ oc_item_id: 'item-1', cantidad_planificada: 40 }] },
        ],
      }),
    )
    renderVista()

    const bloque1 = (await screen.findByText('Entrega 1')).closest('li')!
    expect(within(bloque1).getByText('05/11/2026')).toBeTruthy()
    expect(within(bloque1).getByText('Ibuprofeno 400mg')).toBeTruthy()
    expect(within(bloque1).getByText('60')).toBeTruthy()
    expect(within(bloque1).getByText('Gasas estériles')).toBeTruthy()
    const bloque2 = screen.getByText('Entrega 2').closest('li')!
    expect(within(bloque2).getByText('Sin fecha')).toBeTruthy()
    expect(within(bloque2).getByText('40')).toBeTruthy()
    expect(screen.queryByText('Sin entregas planificadas')).toBeNull()
  })

  it('muestra los links a matching y planificación para comercial', async () => {
    vi.mocked(obtenerOcResumen).mockResolvedValue(resumen())
    renderVista()

    const matching = await screen.findByRole('link', { name: 'Ver matching' })
    expect(matching.getAttribute('href')).toBe('/ordenes-compra/oc-1/matching')
    const planificar = screen.getByRole('link', { name: 'Planificar entregas' })
    expect(planificar.getAttribute('href')).toBe('/ordenes-compra/oc-1/entregas')
  })

  it('muestra el link para volver a compromisos', async () => {
    vi.mocked(obtenerOcResumen).mockResolvedValue(resumen())
    renderVista()
    const volver = await screen.findByRole('link', { name: '← Volver a compromisos' })
    expect(volver.getAttribute('href')).toBe('/compromisos')
    expect(volver.className).toContain('mb-4 inline-block text-sm text-accent hover:underline')
  })

  it('oculta "Planificar entregas" si la OC ya fue exportada, pero deja "Ver matching"', async () => {
    vi.mocked(obtenerOcResumen).mockResolvedValue(
      resumen({
        exportacion: {
          exportado_at: '2026-10-02T10:00:00Z',
          exportado_por: 'u1',
          exportado_por_nombre: null,
          archivo_exportado: 'oc-100.txt',
        },
      }),
    )
    renderVista()
    expect(await screen.findByRole('link', { name: 'Ver matching' })).toBeTruthy()
    expect(screen.queryByRole('link', { name: 'Planificar entregas' })).toBeNull()
  })

  it('oculta los links para compras', async () => {
    rolActual.valor = 'compras'
    vi.mocked(obtenerOcResumen).mockResolvedValue(resumen())
    renderVista()

    await screen.findByRole('heading', { name: /OC-100/ })
    expect(screen.queryByRole('link', { name: 'Ver matching' })).toBeNull()
    expect(screen.queryByRole('link', { name: 'Planificar entregas' })).toBeNull()
  })
})
