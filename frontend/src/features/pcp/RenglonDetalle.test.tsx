import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { RenglonDetalle } from './RenglonDetalle'

const { perfilMock } = vi.hoisted(() => ({ perfilMock: { rol: 'admin' as string } }))

vi.mock('@/features/auth/AuthContext', () => ({ useAuth: () => ({ perfil: perfilMock }) }))
vi.mock('@/lib/api/pcp', () => ({
  obtenerDetalleRenglon: vi.fn(),
  seleccionarProveedores: vi.fn(),
  listarResultadosRenglon: vi.fn(),
  actualizarSeleccion: vi.fn(),
  obtenerSugerenciaAgrupacion: vi.fn(),
  listarSugerenciasPreciosRecientes: vi.fn(),
}))

import {
  obtenerDetalleRenglon, seleccionarProveedores, listarResultadosRenglon, actualizarSeleccion,
  obtenerSugerenciaAgrupacion, listarSugerenciasPreciosRecientes,
} from '@/lib/api/pcp'

const DETALLE_RENGLON = {
  renglon: {
    id: 'reng-1', drogueria_id: 'drog-1', pcp_id: 'pcp-1', item_proceso_id: 'item-1',
    producto_id: 'prod-1', cantidad: 12, precio_referencia: 1850, origen: 'manual',
    regla_pcp_id: null, estado: 'pendiente',
  },
  producto: {
    id: 'prod-1', drogueria_id: 'drog-1', codigo_interno: 'AMOX-500', nombre: 'Amoxicilina 500 mg',
    categoria_id: null, clasificacion: 'medicamento', droga: 'Amoxicilina', presentacion: 'Caja x 20',
    forma_farmaceutica: null, laboratorio: null, codigo_anmat: null, activo: true,
  },
  proveedores_catalogados: [
    { id: 'pp-1', proveedor_id: 'prov-1', codigo_proveedor: 'NORTE-15', activo: true },
    { id: 'pp-2', proveedor_id: 'prov-2', codigo_proveedor: 'SUR-2', activo: true },
  ],
}

function renderDetalle() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return { client, ...render(<QueryClientProvider client={client}><RenglonDetalle pcpId="pcp-1" renglonId="reng-1" /></QueryClientProvider>) }
}

beforeEach(() => {
  perfilMock.rol = 'admin'
  vi.mocked(obtenerDetalleRenglon).mockReset().mockResolvedValue(DETALLE_RENGLON as never)
  vi.mocked(seleccionarProveedores).mockReset().mockResolvedValue([])
  vi.mocked(listarResultadosRenglon).mockReset().mockResolvedValue([])
  vi.mocked(obtenerSugerenciaAgrupacion).mockReset().mockResolvedValue(null)
  vi.mocked(listarSugerenciasPreciosRecientes).mockReset().mockResolvedValue([])
})

describe('RenglonDetalle', () => {
  it('muestra el producto identificado y los proveedores catalogados del renglón', async () => {
    renderDetalle()

    expect(await screen.findByRole('heading', { name: 'Amoxicilina 500 mg' })).toBeInTheDocument()
    expect(screen.getByText('AMOX-500')).toBeInTheDocument()
    const proveedores = within(screen.getByRole('list', { name: 'Proveedores catalogados' }))
    expect(proveedores.getAllByRole('listitem')).toHaveLength(2)
    expect(proveedores.getByText('NORTE-15')).toBeInTheDocument()
    expect(proveedores.getByText('SUR-2')).toBeInTheDocument()
  })

  it('permite seleccionar varios proveedores para negociación', async () => {
    const { client } = renderDetalle()
    const invalidateQueries = vi.spyOn(client, 'invalidateQueries')
    await screen.findByRole('heading', { name: 'Amoxicilina 500 mg' })

    fireEvent.click(screen.getByRole('checkbox', { name: 'NORTE-15' }))
    fireEvent.click(screen.getByRole('checkbox', { name: 'SUR-2' }))
    fireEvent.click(screen.getByRole('button', { name: /confirmar proveedores/i }))

    await waitFor(() => expect(seleccionarProveedores).toHaveBeenCalledWith('pcp-1', 'reng-1', ['prov-1', 'prov-2']))
    await waitFor(() => expect(invalidateQueries).toHaveBeenCalledWith({
      queryKey: ['pcp', 'pcp-1', 'renglones', 'reng-1'],
      exact: true,
    }))
  })

  it('mantiene el detalle visible y omite controles de selección para solo lectura', async () => {
    perfilMock.rol = 'superadmin'
    renderDetalle()

    expect(await screen.findByText('NORTE-15')).toBeInTheDocument()
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /confirmar proveedores/i })).not.toBeInTheDocument()
  })

  it('muestra un estado vacío explícito y ningún control de selección cuando no hay proveedores catalogados', async () => {
    vi.mocked(obtenerDetalleRenglon).mockResolvedValue({
      ...DETALLE_RENGLON,
      proveedores_catalogados: [],
    } as never)
    renderDetalle()

    expect(await screen.findByText('No hay proveedores catalogados para este producto.')).toBeInTheDocument()
    expect(screen.queryByRole('list', { name: 'Proveedores catalogados' })).not.toBeInTheDocument()
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /confirmar proveedores/i })).not.toBeInTheDocument()
  })

  it('envía exactamente el subconjunto elegido al seleccionar solo algunos de varios proveedores disponibles', async () => {
    vi.mocked(obtenerDetalleRenglon).mockResolvedValue({
      ...DETALLE_RENGLON,
      proveedores_catalogados: [
        { id: 'pp-1', proveedor_id: 'prov-1', codigo_proveedor: 'NORTE-15', activo: true },
        { id: 'pp-2', proveedor_id: 'prov-2', codigo_proveedor: 'SUR-2', activo: true },
        { id: 'pp-3', proveedor_id: 'prov-3', codigo_proveedor: 'CENTRO-8', activo: true },
      ],
    } as never)
    renderDetalle()
    await screen.findByRole('heading', { name: 'Amoxicilina 500 mg' })

    fireEvent.click(screen.getByRole('checkbox', { name: 'SUR-2' }))
    fireEvent.click(screen.getByRole('button', { name: /confirmar proveedores/i }))

    await waitFor(() => expect(seleccionarProveedores).toHaveBeenCalledWith('pcp-1', 'reng-1', ['prov-2']))
    expect(seleccionarProveedores).not.toHaveBeenCalledWith('pcp-1', 'reng-1', expect.arrayContaining(['prov-1']))
    expect(seleccionarProveedores).not.toHaveBeenCalledWith('pcp-1', 'reng-1', expect.arrayContaining(['prov-3']))
  })

  it('renderiza en línea un error de validación del servidor al seleccionar proveedores sin perder la selección ya marcada', async () => {
    vi.mocked(seleccionarProveedores).mockRejectedValue(
      Object.assign(new Error('proveedor_ids: Field required'), { status: 422 }),
    )
    renderDetalle()
    await screen.findByRole('heading', { name: 'Amoxicilina 500 mg' })

    fireEvent.click(screen.getByRole('checkbox', { name: 'NORTE-15' }))
    fireEvent.click(screen.getByRole('checkbox', { name: 'SUR-2' }))
    fireEvent.click(screen.getByRole('button', { name: /confirmar proveedores/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('proveedor_ids: Field required')
    expect(screen.getByRole('checkbox', { name: 'NORTE-15' })).toBeChecked()
    expect(screen.getByRole('checkbox', { name: 'SUR-2' })).toBeChecked()
  })

  it('no vuelve a ofrecer como checkbox seleccionable un proveedor que ya tiene un resultado de negociación registrado', async () => {
    vi.mocked(listarResultadosRenglon).mockResolvedValue([
      {
        id: 'res-1', drogueria_id: 'drog-1', pcp_renglon_id: 'reng-1', proveedor_id: 'prov-1',
        resultado: 'no_cotiza', seleccionado: false, precio_proveedor_id: null, precio_unitario: null,
        cantidad_minima: null, cantidad_maxima: null, mantenimiento_hasta: null,
        condicion_pago_id: null, forma_pago_id: null, motivo: null, registrado_por: null,
      },
    ] as never)
    renderDetalle()
    await screen.findByRole('heading', { name: 'Amoxicilina 500 mg' })
    // Espera a que resuelva la query batched de resultados (misma clave que
    // usa ComparacionProveedoresTable) antes de afirmar la ausencia del
    // checkbox -- ambos checkboxes existen mientras esa query sigue pendiente.
    await screen.findByRole('checkbox', { name: 'SUR-2' })

    expect(screen.queryByRole('checkbox', { name: 'NORTE-15' })).not.toBeInTheDocument()
    expect(screen.getByText('NORTE-15 (ya confirmado)')).toBeInTheDocument()
  })

  it('mantiene deshabilitado el botón de un proveedor cuya actualización sigue en curso, sin verse afectado por otra selección concurrente ya resuelta', async () => {
    const base = {
      drogueria_id: 'drog-1', pcp_renglon_id: 'reng-1', resultado: 'precio_obtenido', seleccionado: false,
      precio_proveedor_id: 'precio-1', precio_unitario: 100, cantidad_minima: null, cantidad_maxima: null,
      mantenimiento_hasta: null, condicion_pago_id: null, forma_pago_id: null, motivo: null, registrado_por: null,
    }
    const resultadoNorte = { ...base, id: 'res-1', proveedor_id: 'prov-1' }
    const resultadoSur = { ...base, id: 'res-2', proveedor_id: 'prov-2' }
    vi.mocked(listarResultadosRenglon).mockResolvedValue([resultadoNorte, resultadoSur] as never)

    let resolverNorte: (valor: unknown) => void = () => {}
    vi.mocked(actualizarSeleccion).mockImplementation((_pcpId, _renglonId, proveedorId) => {
      if (proveedorId === 'prov-1') {
        return new Promise((resolve) => { resolverNorte = resolve as (valor: unknown) => void }) as never
      }
      return new Promise(() => {}) as never // prov-2 permanece pendiente durante todo el test
    })

    renderDetalle()
    await screen.findByRole('heading', { name: 'Amoxicilina 500 mg' })

    const [botonNorte, botonSur] = await screen.findAllByRole('button', { name: 'Seleccionar proveedor' })
    fireEvent.click(botonNorte)
    fireEvent.click(botonSur)

    expect(botonNorte).toBeDisabled()
    expect(botonSur).toBeDisabled()

    resolverNorte({ ...resultadoNorte, seleccionado: true })
    await waitFor(() => expect(botonNorte).not.toBeDisabled())

    expect(botonSur).toBeDisabled()
  })

  it('muestra la comparación de proveedores y permite alternar la selección persistida con permisos de escritura', async () => {
    const resultadoNorte = {
      id: 'res-1', drogueria_id: 'drog-1', pcp_renglon_id: 'reng-1', proveedor_id: 'prov-1',
      resultado: 'precio_obtenido', seleccionado: false, precio_proveedor_id: 'precio-1',
      precio_unitario: 100, cantidad_minima: null, cantidad_maxima: null, mantenimiento_hasta: null,
      condicion_pago_id: null, forma_pago_id: null, motivo: null, registrado_por: null,
    }
    vi.mocked(listarResultadosRenglon).mockResolvedValue([resultadoNorte] as never)
    vi.mocked(actualizarSeleccion).mockResolvedValue({ ...resultadoNorte, seleccionado: true } as never)

    renderDetalle()
    await screen.findByRole('heading', { name: 'Amoxicilina 500 mg' })

    const boton = await screen.findByRole('button', { name: 'Seleccionar proveedor' })
    fireEvent.click(boton)

    await waitFor(() => expect(actualizarSeleccion).toHaveBeenCalledWith('pcp-1', 'reng-1', 'prov-1', true))
    expect(await screen.findByText('Seleccionado')).toBeInTheDocument()
  })
})
