import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ProductoProveedor } from '@/lib/api/pcp'

vi.mock('@/lib/api/pcp', () => ({ listarResultadosRenglon: vi.fn(), actualizarSeleccion: vi.fn() }))

import { ComparacionProveedoresTable } from './ComparacionProveedoresTable'
import { listarResultadosRenglon, actualizarSeleccion } from '@/lib/api/pcp'
import { pcpQueryKeys } from './queryKeys'

const PROVEEDORES: ProductoProveedor[] = [
  { id: 'pp-1', drogueria_id: 'drog-1', producto_id: 'prod-1', proveedor_id: 'prov-1', codigo_proveedor: 'NORTE-15', preferido: false, activo: true, notas: null },
  { id: 'pp-2', drogueria_id: 'drog-1', producto_id: 'prod-1', proveedor_id: 'prov-2', codigo_proveedor: 'SUR-2', preferido: false, activo: true, notas: null },
]

function resultadoDe(proveedorId: string, overrides: Record<string, unknown> = {}) {
  return {
    id: `res-${proveedorId}`,
    drogueria_id: 'drog-1',
    pcp_renglon_id: 'reng-1',
    proveedor_id: proveedorId,
    resultado: 'precio_obtenido',
    seleccionado: false,
    precio_proveedor_id: 'precio-1',
    motivo: null,
    registrado_por: null,
    ...overrides,
  }
}

function renderTabla(overrides: { proveedores?: ProductoProveedor[], puedeEscribir?: boolean } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return {
    client,
    ...render(
      <QueryClientProvider client={client}>
        <ComparacionProveedoresTable
          pcpId="pcp-1"
          renglonId="reng-1"
          proveedores={overrides.proveedores ?? PROVEEDORES}
          puedeEscribir={overrides.puedeEscribir ?? false}
        />
      </QueryClientProvider>,
    ),
  }
}

beforeEach(() => {
  vi.mocked(listarResultadosRenglon).mockReset()
  vi.mocked(actualizarSeleccion).mockReset()
})

describe('ComparacionProveedoresTable', () => {
  it('muestra un estado de carga mientras se obtiene la comparación', () => {
    vi.mocked(listarResultadosRenglon).mockReturnValue(new Promise(() => {}))

    renderTabla()

    expect(screen.getByText('Cargando comparación…')).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('muestra un estado vacío cuando el renglón no tiene proveedores catalogados', () => {
    renderTabla({ proveedores: [] })

    expect(screen.getByText('No hay proveedores catalogados para este renglón.')).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(listarResultadosRenglon).not.toHaveBeenCalled()
  })

  it('llama a la lectura batched una sola vez por su ruta exacta, en vez de un fan-out por proveedor', async () => {
    vi.mocked(listarResultadosRenglon).mockResolvedValue([resultadoDe('prov-1'), resultadoDe('prov-2')] as never)

    renderTabla()

    await screen.findAllByText('Precio obtenido')
    expect(listarResultadosRenglon).toHaveBeenCalledTimes(1)
    expect(listarResultadosRenglon).toHaveBeenCalledWith('pcp-1', 'reng-1')
  })

  it('trata a un proveedor ausente de la lista batched como "sin resultado aún", no como un error', async () => {
    vi.mocked(listarResultadosRenglon).mockResolvedValue([resultadoDe('prov-2')] as never)

    renderTabla()

    expect(await screen.findByText('Sin resultado aún')).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('distingue un fallo real de carga de "sin resultado aún" con un mensaje a nivel de tabla', async () => {
    vi.mocked(listarResultadosRenglon).mockRejectedValue(new Error('Error del servidor'))

    renderTabla()

    expect(await screen.findByText('Error al cargar la comparación de proveedores.')).toBeInTheDocument()
    expect(screen.queryByText('Sin resultado aún')).not.toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('muestra el resultado precio_obtenido de un proveedor', async () => {
    vi.mocked(listarResultadosRenglon).mockResolvedValue([resultadoDe('prov-1')] as never)

    renderTabla({ proveedores: [PROVEEDORES[0]] })

    expect(await screen.findByText('Precio obtenido')).toBeInTheDocument()
    expect(screen.queryByText('No cotiza')).not.toBeInTheDocument()
  })

  it('muestra el resultado no_cotiza junto al motivo, sin ningún precio', async () => {
    vi.mocked(listarResultadosRenglon).mockResolvedValue([resultadoDe('prov-1', {
      resultado: 'no_cotiza', precio_proveedor_id: null, motivo: 'Sin stock disponible',
    })] as never)

    renderTabla({ proveedores: [PROVEEDORES[0]] })

    expect(await screen.findByText('No cotiza')).toBeInTheDocument()
    expect(screen.getByText('Sin stock disponible')).toBeInTheDocument()
    expect(screen.queryByText('Precio obtenido')).not.toBeInTheDocument()
  })

  it('renderiza columnas de escritorio, una por proveedor catalogado', async () => {
    vi.mocked(listarResultadosRenglon).mockResolvedValue([resultadoDe('prov-1'), resultadoDe('prov-2')] as never)

    renderTabla()

    const tabla = await screen.findByRole('table', { name: 'Comparación de proveedores' })
    expect(within(tabla).getByRole('columnheader', { name: 'NORTE-15' })).toBeInTheDocument()
    expect(within(tabla).getByRole('columnheader', { name: 'SUR-2' })).toBeInTheDocument()
    expect(within(tabla).getByRole('rowheader', { name: 'Resultado' })).toBeInTheDocument()
  })

  it('renderiza tarjetas móviles con los mismos datos que la tabla de escritorio', async () => {
    vi.mocked(listarResultadosRenglon).mockResolvedValue([resultadoDe('prov-1'), resultadoDe('prov-2')] as never)

    renderTabla()

    const lista = await screen.findByRole('list', { name: 'Comparación de proveedores en tarjetas' })
    const tarjetas = within(lista).getAllByRole('listitem')
    expect(tarjetas).toHaveLength(2)
    expect(within(tarjetas[0]).getByText('NORTE-15')).toBeInTheDocument()
    expect(within(tarjetas[0]).getByText('Precio obtenido')).toBeInTheDocument()
    expect(within(tarjetas[1]).getByText('SUR-2')).toBeInTheDocument()
  })

  it('no muestra ningún control de mutación para un rol de solo lectura', async () => {
    vi.mocked(listarResultadosRenglon).mockResolvedValue([resultadoDe('prov-1'), resultadoDe('prov-2')] as never)

    renderTabla({ puedeEscribir: false })

    await screen.findAllByText('Precio obtenido')
    expect(screen.queryByRole('button', { name: /resultado/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /selecci/i })).not.toBeInTheDocument()
  })

  it('nunca renderiza un control para cerrar el PCP, ni siquiera con permisos de escritura', async () => {
    vi.mocked(listarResultadosRenglon).mockResolvedValue([resultadoDe('prov-1'), resultadoDe('prov-2')] as never)

    renderTabla({ puedeEscribir: true })

    await screen.findAllByText('Precio obtenido')
    expect(screen.queryByRole('button', { name: /cerrar pcp/i })).not.toBeInTheDocument()
    expect(screen.queryByText(/cerrar pcp/i)).not.toBeInTheDocument()
  })

  it('permite dos proveedores marcados como seleccionado de forma simultánea y no exclusiva', async () => {
    vi.mocked(listarResultadosRenglon).mockResolvedValue([
      resultadoDe('prov-1', { seleccionado: true }),
      resultadoDe('prov-2', { seleccionado: true }),
    ] as never)

    renderTabla({ puedeEscribir: true })

    await screen.findAllByText('Precio obtenido')
    expect(screen.getAllByText('Seleccionado')).toHaveLength(2)
    expect(screen.getAllByRole('button', { name: 'Quitar selección' })).toHaveLength(2)
  })

  it('escribe la fila devuelta en la clave batched existente y solo invalida selección/agrupables al marcar', async () => {
    const resultadoInicial = resultadoDe('prov-1', { precio_unitario: 100, cantidad_minima: 5 })
    vi.mocked(listarResultadosRenglon).mockResolvedValue([resultadoInicial] as never)
    vi.mocked(actualizarSeleccion).mockResolvedValue({ ...resultadoInicial, seleccionado: true } as never)

    const { client } = renderTabla({ proveedores: [PROVEEDORES[0]], puedeEscribir: true })
    const setQueryData = vi.spyOn(client, 'setQueryData')
    const invalidateQueries = vi.spyOn(client, 'invalidateQueries')

    fireEvent.click(await screen.findByRole('button', { name: 'Seleccionar proveedor' }))

    await waitFor(() => expect(actualizarSeleccion).toHaveBeenCalledWith('pcp-1', 'reng-1', 'prov-1', true))

    const claveResultados = pcpQueryKeys.resultadosRenglon('pcp-1', 'reng-1')
    await waitFor(() => expect(setQueryData).toHaveBeenCalledWith(claveResultados, expect.any(Function)))
    const actual = client.getQueryData<typeof resultadoInicial[]>(claveResultados)
    expect(actual).toMatchObject([{ seleccionado: true, precio_unitario: 100, cantidad_minima: 5 }])

    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: pcpQueryKeys.seleccion('pcp-1') })
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: pcpQueryKeys.seleccionesAgrupables('pcp-1') })
    expect(invalidateQueries).not.toHaveBeenCalledWith({ queryKey: pcpQueryKeys.detalle('pcp-1') })
    expect(invalidateQueries).not.toHaveBeenCalledWith({ queryKey: pcpQueryKeys.renglones('pcp-1') })
    expect(invalidateQueries).not.toHaveBeenCalledWith({ queryKey: pcpQueryKeys.renglon('pcp-1', 'reng-1') })
    expect(invalidateQueries).not.toHaveBeenCalledWith({ queryKey: claveResultados })
  })

  it('muestra un mensaje de error si falla la actualización de selección, sin dejar al usuario sin feedback', async () => {
    const resultadoInicial = resultadoDe('prov-1', { precio_unitario: 100 })
    vi.mocked(listarResultadosRenglon).mockResolvedValue([resultadoInicial] as never)
    vi.mocked(actualizarSeleccion).mockRejectedValue(new Error('network error'))

    renderTabla({ proveedores: [PROVEEDORES[0]], puedeEscribir: true })

    fireEvent.click(await screen.findByRole('button', { name: 'Seleccionar proveedor' }))

    expect(await screen.findAllByText('No se pudo actualizar la selección.')).not.toHaveLength(0)
  })

  it('repite el mismo contrato de caché al desmarcar una selección ya persistida', async () => {
    const resultadoSeleccionado = resultadoDe('prov-1', { seleccionado: true, precio_unitario: 250 })
    vi.mocked(listarResultadosRenglon).mockResolvedValue([resultadoSeleccionado] as never)
    vi.mocked(actualizarSeleccion).mockResolvedValue({ ...resultadoSeleccionado, seleccionado: false } as never)

    const { client } = renderTabla({ proveedores: [PROVEEDORES[0]], puedeEscribir: true })
    const invalidateQueries = vi.spyOn(client, 'invalidateQueries')

    fireEvent.click(await screen.findByRole('button', { name: 'Quitar selección' }))

    await waitFor(() => expect(actualizarSeleccion).toHaveBeenCalledWith('pcp-1', 'reng-1', 'prov-1', false))

    const claveResultados = pcpQueryKeys.resultadosRenglon('pcp-1', 'reng-1')
    await waitFor(() => {
      const actual = client.getQueryData<typeof resultadoSeleccionado[]>(claveResultados)
      expect(actual).toMatchObject([{ seleccionado: false, precio_unitario: 250 }])
    })

    expect(invalidateQueries).toHaveBeenCalledTimes(2)
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: pcpQueryKeys.seleccion('pcp-1') })
    expect(invalidateQueries).toHaveBeenCalledWith({ queryKey: pcpQueryKeys.seleccionesAgrupables('pcp-1') })
  })
})
