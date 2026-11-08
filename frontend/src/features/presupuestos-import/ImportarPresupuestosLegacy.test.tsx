import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { capacidadesDeRol } from '@/test/capacidades'
import { ImportarPresupuestosLegacy } from './ImportarPresupuestosLegacy'
import { Route as ImportarRoute } from '@/routes/_authenticated.presupuestos.importar'
import { fechaLegible } from '@/lib/fechas'

const { perfilMock } = vi.hoisted(() => ({ perfilMock: { rol: 'admin' as string } }))

vi.mock('@/features/auth/AuthContext', async () => {
  const { authDeRol } = await import('@/test/capacidades')
  return { useAuth: () => ({ perfil: perfilMock, ...authDeRol(perfilMock.rol) }) }
})
vi.mock('@/lib/api/integracionProgress', () => ({ subirPresupuestosProgress: vi.fn() }))

import { subirPresupuestosProgress } from '@/lib/api/integracionProgress'
import type { RecepcionPresupuestos } from '@/lib/api/integracionProgress'

function archivoCsv(nombre = 'legado.csv') {
  return new File(['codigo_cliente;razon_social_cliente\n'], nombre, { type: 'text/csv' })
}

function recepcion(campos: Partial<RecepcionPresupuestos>): RecepcionPresupuestos {
  return {
    estado: 'procesado',
    registro_id: 'reg-1',
    nombre_archivo: 'legado.csv',
    procesado_at: '2026-11-04T12:00:00Z',
    errores: [],
    resultados: [],
    ...campos,
  }
}

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
    context: { auth: { isAuthenticated: true, perfil: { rol }, capacidades: capacidadesDeRol(rol) } },
    location: { href: '/presupuestos/importar' },
  }
}

function seleccionar(archivo: File) {
  fireEvent.change(screen.getByLabelText(/archivo/i), { target: { files: [archivo] } })
}

describe('ImportarPresupuestosLegacy', () => {
  beforeEach(() => {
    perfilMock.rol = 'admin'
    vi.mocked(subirPresupuestosProgress).mockReset()
  })

  it('S6: solo admin puede navegar directo a la importación legacy', () => {
    expect(() => ImportarRoute.options.beforeLoad?.(navigationArgs('admin') as never)).not.toThrow()
    expect(() => ImportarRoute.options.beforeLoad?.(navigationArgs('gerencia') as never)).toThrow()
    expect(() => ImportarRoute.options.beforeLoad?.(navigationArgs('compras') as never)).toThrow()
  })

  it('sigue bloqueando la navegación directa de superadmin', () => {
    expect(() => ImportarRoute.options.beforeLoad?.(navigationArgs('superadmin') as never)).toThrow()
  })

  it('el botón importar queda deshabilitado hasta elegir un archivo', () => {
    renderPantalla()

    expect(screen.getByRole('button', { name: /importar/i })).toBeDisabled()
    seleccionar(archivoCsv())
    expect(screen.getByRole('button', { name: /importar/i })).toBeEnabled()
    expect(subirPresupuestosProgress).not.toHaveBeenCalled()
  })

  it('sube el archivo seleccionado tal cual y muestra la tabla de resultados', async () => {
    vi.mocked(subirPresupuestosProgress).mockResolvedValue(
      recepcion({
        resultados: [
          { codigo_legacy: 'PRE-100', presupuesto_id: 'p1', accion: 'creado', renglones_procesados: 2, renglones_sin_producto: 0 },
          { codigo_legacy: 'PRE-200', presupuesto_id: 'p2', accion: 'existente', renglones_procesados: 1, renglones_sin_producto: 1 },
        ],
      }),
    )
    renderPantalla()
    const archivo = archivoCsv()

    seleccionar(archivo)
    fireEvent.click(screen.getByRole('button', { name: /importar/i }))

    await waitFor(() => expect(subirPresupuestosProgress).toHaveBeenCalledWith(archivo))
    expect(await screen.findByText('PRE-100')).toBeInTheDocument()
    expect(screen.getByText('creado')).toBeInTheDocument()
    expect(screen.getByText('PRE-200')).toBeInTheDocument()
    expect(screen.getByText('existente')).toBeInTheDocument()
  })

  it('lista los errores por línea que devuelve el backend', async () => {
    vi.mocked(subirPresupuestosProgress).mockResolvedValue(
      recepcion({
        estado: 'error',
        procesado_at: null,
        errores: [
          { linea: 2, mensaje: 'renglón no es un número entero' },
          { linea: 4, mensaje: 'falta codigo_cliente; falta descripcion_producto' },
        ],
      }),
    )
    renderPantalla()

    seleccionar(archivoCsv())
    fireEvent.click(screen.getByRole('button', { name: /importar/i }))

    expect(await screen.findByText('Línea 2: renglón no es un número entero')).toBeInTheDocument()
    expect(screen.getByText('Línea 4: falta codigo_cliente; falta descripcion_producto')).toBeInTheDocument()
    expect(screen.getByText(/2 errores bloquean el import/i)).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('avisa cuando el archivo ya fue procesado, con la fecha original', async () => {
    vi.mocked(subirPresupuestosProgress).mockResolvedValue(recepcion({ estado: 'duplicado' }))
    renderPantalla()

    seleccionar(archivoCsv())
    fireEvent.click(screen.getByRole('button', { name: /importar/i }))

    const aviso = await screen.findByRole('status')
    expect(aviso).toHaveTextContent('Este archivo ya fue procesado')
    expect(aviso).toHaveTextContent(fechaLegible('2026-11-04T12:00:00Z'))
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('si el original sigue en curso, avisa que se está procesando y no que ya se procesó', async () => {
    vi.mocked(subirPresupuestosProgress).mockResolvedValue(recepcion({ estado: 'duplicado', procesado_at: null }))
    renderPantalla()

    seleccionar(archivoCsv())
    fireEvent.click(screen.getByRole('button', { name: /importar/i }))

    const aviso = await screen.findByRole('status')
    expect(aviso).toHaveTextContent(/^Este archivo ya se está procesando\.$/)
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('si el original terminó en error, avisa que falló y que se puede reintentar', async () => {
    vi.mocked(subirPresupuestosProgress).mockResolvedValue(
      recepcion({
        estado: 'duplicado',
        procesado_at: null,
        errores: [{ linea: 0, mensaje: 'No se encontró el cliente CLI-9' }],
      }),
    )
    renderPantalla()

    seleccionar(archivoCsv())
    fireEvent.click(screen.getByRole('button', { name: /importar/i }))

    const aviso = await screen.findByRole('status')
    expect(aviso).toHaveTextContent(
      /^Este archivo ya se intentó importar y terminó con errores\. Se puede volver a cargar para reintentar\.$/,
    )
    expect(screen.queryByText(/se está procesando/i)).not.toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('elegir otro archivo limpia el resultado anterior', async () => {
    vi.mocked(subirPresupuestosProgress).mockResolvedValue(
      recepcion({ estado: 'error', errores: [{ linea: 2, mensaje: 'renglón no es un número entero' }] }),
    )
    renderPantalla()

    seleccionar(archivoCsv('a.csv'))
    fireEvent.click(screen.getByRole('button', { name: /importar/i }))
    expect(await screen.findByText(/línea 2/i)).toBeInTheDocument()

    seleccionar(archivoCsv('b.csv'))

    expect(screen.queryByText(/línea 2/i)).not.toBeInTheDocument()
  })

  it('si la API de import falla, muestra el detalle del backend', async () => {
    vi.mocked(subirPresupuestosProgress).mockRejectedValueOnce(new Error('No se encontró el cliente CLI-9'))
    renderPantalla()

    seleccionar(archivoCsv())
    fireEvent.click(screen.getByRole('button', { name: /importar/i }))

    const alerta = await screen.findByRole('alert')
    expect(alerta).toHaveTextContent('No se encontró el cliente CLI-9')
  })
})
