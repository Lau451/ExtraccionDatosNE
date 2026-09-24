import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ImportarPresupuestosLegacy } from './ImportarPresupuestosLegacy'
import { Route as ImportarRoute } from '@/routes/_authenticated.presupuestos.importar'

const { perfilMock } = vi.hoisted(() => ({ perfilMock: { rol: 'admin' as string } }))

vi.mock('@/features/auth/AuthContext', () => ({ useAuth: () => ({ perfil: perfilMock }) }))
vi.mock('@/lib/api/pcp', () => ({ importarPresupuestosLegacy: vi.fn() }))

import { importarPresupuestosLegacy } from '@/lib/api/pcp'
import type { ImportPresupuestoLegacyResultado } from '@/lib/api/pcp'

const ENCABEZADO =
  'codigo_cliente,razon_social_cliente,numero_presupuesto,renglon,descripcion_producto,cantidad_producto'

function archivoCsv(contenido: string, textoDeferido?: Promise<void>) {
  const archivo = new File([contenido], 'legado.csv', { type: 'text/csv' })
  if (textoDeferido) {
    archivo.text = async () => {
      await textoDeferido
      return contenido
    }
  }
  return archivo
}

const CSV_DOS_PRESUPUESTOS = [
  ENCABEZADO,
  'CLI-1,Farmacia Central,PRE-100,1,Amoxicilina 500mg,10',
  'CLI-1,Farmacia Central,PRE-100,2,Ibuprofeno 400mg,5',
  'CLI-2,Farmacia Sur,PRE-200,1,Paracetamol 500mg,20',
].join('\n')

const CSV_CON_ERROR = [ENCABEZADO, 'CLI-1,Farmacia Central,PRE-100,abc,Amoxicilina 500mg,10'].join('\n')

function renderPantalla() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ImportarPresupuestosLegacy />
    </QueryClientProvider>,
  )
}

function navigationArgs(rol: 'superadmin' | 'admin' | 'gerencia' | 'compras') {
  return {
    context: { auth: { isAuthenticated: true, perfil: { rol } } },
    location: { href: '/presupuestos/importar' },
  }
}

describe('ImportarPresupuestosLegacy', () => {
  beforeEach(() => {
    perfilMock.rol = 'admin'
    vi.mocked(importarPresupuestosLegacy).mockReset()
  })

  it('bloquea la navegación directa de un rol de solo lectura y permite a un rol de escritura', () => {
    expect(() => ImportarRoute.options.beforeLoad?.(navigationArgs('superadmin') as never)).toThrow()
    expect(() => ImportarRoute.options.beforeLoad?.(navigationArgs('compras') as never)).not.toThrow()
  })

  it('muestra la vista previa con la cantidad de presupuestos y filas detectadas', async () => {
    renderPantalla()

    fireEvent.change(screen.getByLabelText(/archivo/i), { target: { files: [archivoCsv(CSV_DOS_PRESUPUESTOS)] } })

    expect(await screen.findByText(/2 presupuestos/i)).toBeInTheDocument()
    expect(screen.getByText(/3 filas/i)).toBeInTheDocument()
  })

  it('lista errores de validación con número de línea y bloquea el botón importar', async () => {
    renderPantalla()

    fireEvent.change(screen.getByLabelText(/archivo/i), { target: { files: [archivoCsv(CSV_CON_ERROR)] } })

    expect(await screen.findByText(/línea 2/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /importar/i })).toBeDisabled()
    expect(importarPresupuestosLegacy).not.toHaveBeenCalled()
  })

  it('envía las filas parseadas y muestra la tabla de resultados', async () => {
    const resultado: ImportPresupuestoLegacyResultado[] = [
      { codigo_legacy: 'PRE-100', presupuesto_id: 'p1', accion: 'creado', renglones_procesados: 2, renglones_sin_producto: 0 },
      { codigo_legacy: 'PRE-200', presupuesto_id: 'p2', accion: 'existente', renglones_procesados: 1, renglones_sin_producto: 1 },
    ]
    vi.mocked(importarPresupuestosLegacy).mockResolvedValue(resultado)
    renderPantalla()

    fireEvent.change(screen.getByLabelText(/archivo/i), { target: { files: [archivoCsv(CSV_DOS_PRESUPUESTOS)] } })
    await screen.findByText(/2 presupuestos/i)
    fireEvent.click(screen.getByRole('button', { name: /importar/i }))

    await waitFor(() =>
      expect(importarPresupuestosLegacy).toHaveBeenCalledWith([
        { codigo_cliente: 'CLI-1', razon_social_cliente: 'Farmacia Central', numero_presupuesto: 'PRE-100', proceso_comercial: undefined, fecha_generacion: undefined, renglon: 1, codigo_producto: undefined, descripcion_producto: 'Amoxicilina 500mg', cantidad_producto: 10, precio_producto: undefined, importe_total: undefined },
        { codigo_cliente: 'CLI-1', razon_social_cliente: 'Farmacia Central', numero_presupuesto: 'PRE-100', proceso_comercial: undefined, fecha_generacion: undefined, renglon: 2, codigo_producto: undefined, descripcion_producto: 'Ibuprofeno 400mg', cantidad_producto: 5, precio_producto: undefined, importe_total: undefined },
        { codigo_cliente: 'CLI-2', razon_social_cliente: 'Farmacia Sur', numero_presupuesto: 'PRE-200', proceso_comercial: undefined, fecha_generacion: undefined, renglon: 1, codigo_producto: undefined, descripcion_producto: 'Paracetamol 500mg', cantidad_producto: 20, precio_producto: undefined, importe_total: undefined },
      ]),
    )

    expect(await screen.findByText('PRE-100')).toBeInTheDocument()
    expect(screen.getByText('creado')).toBeInTheDocument()
    expect(screen.getByText('PRE-200')).toBeInTheDocument()
    expect(screen.getByText('existente')).toBeInTheDocument()
  })

  it('ignora una lectura de archivo obsoleta cuando dos selecciones resuelven fuera de orden', async () => {
    renderPantalla()

    let resolverLecturaA: () => void = () => {}
    const lecturaA = new Promise<void>((resolve) => {
      resolverLecturaA = resolve
    })
    const archivoA = archivoCsv(CSV_CON_ERROR, lecturaA)
    const archivoB = archivoCsv(CSV_DOS_PRESUPUESTOS)

    const input = screen.getByLabelText(/archivo/i)
    fireEvent.change(input, { target: { files: [archivoA] } })
    fireEvent.change(input, { target: { files: [archivoB] } })

    expect(await screen.findByText(/2 presupuestos/i)).toBeInTheDocument()

    resolverLecturaA()
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(screen.getByText(/2 presupuestos/i)).toBeInTheDocument()
    expect(screen.queryByText(/línea 2/i)).not.toBeInTheDocument()
  })

  it('si la API de import falla, muestra el detalle del backend', async () => {
    vi.mocked(importarPresupuestosLegacy).mockRejectedValueOnce(new Error('No se encontró el cliente CLI-9'))
    renderPantalla()

    fireEvent.change(screen.getByLabelText(/archivo/i), { target: { files: [archivoCsv(CSV_DOS_PRESUPUESTOS)] } })
    await screen.findByText(/2 presupuestos/i)
    fireEvent.click(screen.getByRole('button', { name: /importar/i }))

    const alerta = await screen.findByRole('alert')
    expect(alerta).toHaveTextContent('No se encontró el cliente CLI-9')
  })
})
