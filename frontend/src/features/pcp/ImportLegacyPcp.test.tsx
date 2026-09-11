import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ImportLegacyPcp } from './ImportLegacyPcp'
import { Route as ImportsRoute } from '@/routes/_authenticated.pcp.imports'

const { perfilMock } = vi.hoisted(() => ({ perfilMock: { rol: 'admin' as string } }))

vi.mock('@/features/auth/AuthContext', () => ({ useAuth: () => ({ perfil: perfilMock }) }))
vi.mock('@/lib/api/pcp', () => ({ importarPcpLegacy: vi.fn() }))

import { importarPcpLegacy } from '@/lib/api/pcp'
import type { FilaImportPcpLegacy, ImportPcpLegacyResultado } from '@/lib/api/pcp'

const FILAS: FilaImportPcpLegacy[] = [
  {
    codigo_cliente: 'CLI-1',
    razon_social_cliente: 'Farmacia Central',
    numero_pcp: 'PCP-100',
    renglon: 1,
    descripcion_producto: 'Amoxicilina 500mg',
    cantidad_producto: 10,
  },
  {
    codigo_cliente: 'CLI-1',
    razon_social_cliente: 'Farmacia Central',
    numero_pcp: 'PCP-100',
    renglon: 2,
    descripcion_producto: 'Ibuprofeno 400mg',
    cantidad_producto: 5,
  },
]

/** El formato exacto de parseo (CSV vs JSON) no está definido por spec/design;
 * usamos JSON porque su "parseo" es un `JSON.parse` trivial, así el RED se
 * enfoca en el contrato del componente (leer archivo -> llamar
 * `importarPcpLegacy` con las filas) y no en lógica de parseo de columnas,
 * que queda fuera de este subunit RED-only. */
function archivoLegado(filas: FilaImportPcpLegacy[]) {
  return new File([JSON.stringify(filas)], 'legado.json', { type: 'application/json' })
}

function renderImport() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}><ImportLegacyPcp /></QueryClientProvider>)
}

function navigationArgs(rol: 'superadmin' | 'admin' | 'gerencia' | 'compras') {
  return {
    context: { auth: { isAuthenticated: true, perfil: { rol } } },
    location: { href: '/pcp/imports' },
  }
}

describe('ImportLegacyPcp', () => {
  beforeEach(() => {
    perfilMock.rol = 'admin'
    vi.mocked(importarPcpLegacy).mockReset()
  })

  it('un rol de escritura envía el import con las filas parseadas del archivo', async () => {
    vi.mocked(importarPcpLegacy).mockResolvedValue([])
    renderImport()

    fireEvent.change(screen.getByLabelText(/archivo/i), { target: { files: [archivoLegado(FILAS)] } })
    fireEvent.click(screen.getByRole('button', { name: /importar/i }))

    await waitFor(() => expect(importarPcpLegacy).toHaveBeenCalledWith(FILAS))
  })

  it('bloquea la navegación directa de un rol de solo lectura y permite a un rol de escritura', () => {
    expect(() => ImportsRoute.options.beforeLoad?.(navigationArgs('superadmin') as never)).toThrow()
    expect(() => ImportsRoute.options.beforeLoad?.(navigationArgs('compras') as never)).not.toThrow()
  })

  it('muestra un resumen legible en vez de la respuesta cruda de la API', async () => {
    const resultado: ImportPcpLegacyResultado[] = [
      { codigo_legacy: 'PCP-100', pcp_id: 'pcp-1', accion: 'creado', renglones_procesados: 2 },
      { codigo_legacy: 'PCP-101', pcp_id: 'pcp-2', accion: 'creado', renglones_procesados: 1 },
      { codigo_legacy: 'PCP-102', pcp_id: 'pcp-3', accion: 'actualizado', renglones_procesados: 3 },
    ]
    vi.mocked(importarPcpLegacy).mockResolvedValue(resultado)
    renderImport()

    fireEvent.change(screen.getByLabelText(/archivo/i), { target: { files: [archivoLegado(FILAS)] } })
    fireEvent.click(screen.getByRole('button', { name: /importar/i }))

    expect(await screen.findByText(/2 pcp creados/i)).toBeInTheDocument()
    expect(screen.getByText(/1 pcp actualizado/i)).toBeInTheDocument()
    expect(screen.queryByText(/"codigo_legacy"/)).not.toBeInTheDocument()
  })

  it('un import repetido se distingue como actualizado y no vuelve a contarse como creado', async () => {
    vi.mocked(importarPcpLegacy).mockResolvedValueOnce([
      { codigo_legacy: 'PCP-100', pcp_id: 'pcp-1', accion: 'creado', renglones_procesados: 2 },
    ])
    renderImport()
    fireEvent.change(screen.getByLabelText(/archivo/i), { target: { files: [archivoLegado(FILAS)] } })
    fireEvent.click(screen.getByRole('button', { name: /importar/i }))
    expect(await screen.findByText(/1 pcp creado/i)).toBeInTheDocument()
    expect(screen.queryByText(/actualizado/i)).not.toBeInTheDocument()

    vi.mocked(importarPcpLegacy).mockResolvedValueOnce([
      { codigo_legacy: 'PCP-100', pcp_id: 'pcp-1', accion: 'actualizado', renglones_procesados: 2 },
    ])
    fireEvent.change(screen.getByLabelText(/archivo/i), { target: { files: [archivoLegado(FILAS)] } })
    fireEvent.click(screen.getByRole('button', { name: /importar/i }))

    expect(await screen.findByText(/1 pcp actualizado/i)).toBeInTheDocument()
    expect(screen.queryByText(/1 pcp creado/i)).not.toBeInTheDocument()
  })

  it('una misma respuesta con conteo desparejo de creados y actualizados se resume con números exactos', async () => {
    const resultado: ImportPcpLegacyResultado[] = [
      { codigo_legacy: 'PCP-200', pcp_id: 'pcp-10', accion: 'creado', renglones_procesados: 1 },
      { codigo_legacy: 'PCP-201', pcp_id: 'pcp-11', accion: 'actualizado', renglones_procesados: 2 },
      { codigo_legacy: 'PCP-202', pcp_id: 'pcp-12', accion: 'creado', renglones_procesados: 1 },
      { codigo_legacy: 'PCP-203', pcp_id: 'pcp-13', accion: 'creado', renglones_procesados: 3 },
    ]
    vi.mocked(importarPcpLegacy).mockResolvedValue(resultado)
    renderImport()

    fireEvent.change(screen.getByLabelText(/archivo/i), { target: { files: [archivoLegado(FILAS)] } })
    fireEvent.click(screen.getByRole('button', { name: /importar/i }))

    expect(await screen.findByText(/^3 pcp creados$/i)).toBeInTheDocument()
    expect(screen.getByText(/^1 pcp actualizado$/i)).toBeInTheDocument()
    expect(screen.queryByText(/^4 pcp/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/^2 pcp actualizado/i)).not.toBeInTheDocument()
  })

  it('si la API de import falla, muestra un error genérico y el control sigue habilitado para reintentar', async () => {
    vi.mocked(importarPcpLegacy).mockRejectedValueOnce(new Error('Internal Server Error: stack trace leak at line 42'))
    renderImport()

    fireEvent.change(screen.getByLabelText(/archivo/i), { target: { files: [archivoLegado(FILAS)] } })
    const boton = screen.getByRole('button', { name: /importar/i })
    fireEvent.click(boton)

    const alerta = await screen.findByRole('alert')
    expect(alerta).toHaveTextContent(/no se pudo importar/i)
    expect(alerta.textContent).not.toMatch(/internal server error|stack trace/i)
    await waitFor(() => expect(boton).not.toBeDisabled())

    vi.mocked(importarPcpLegacy).mockResolvedValueOnce([
      { codigo_legacy: 'PCP-100', pcp_id: 'pcp-1', accion: 'creado', renglones_procesados: 2 },
    ])
    fireEvent.click(boton)

    expect(await screen.findByText(/1 pcp creado/i)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(importarPcpLegacy).toHaveBeenCalledTimes(2)
  })
})
