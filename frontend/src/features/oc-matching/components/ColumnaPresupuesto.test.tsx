import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { RenglonOrdenCompra, RenglonPresupuesto } from '@/lib/api/ocMatching'
import { ColumnaPresupuesto } from './ColumnaPresupuesto'

function presupuesto(overrides: Partial<RenglonPresupuesto> = {}): RenglonPresupuesto {
  return {
    presupuesto_item_id: 'pi-1',
    item_proceso_id: 'ip-1',
    numero_renglon: 1,
    descripcion: 'Ibuprofeno 400mg x 20',
    cantidad_ofertada: 10,
    precio_unitario: 1250,
    producto_id: null,
    renglones_oc_vinculados: 0,
    renglones_oc_vinculados_otras_oc: 0,
    cantidad_vinculada: 0,
    ...overrides,
  }
}

function ordenCompra(overrides: Partial<RenglonOrdenCompra> = {}): RenglonOrdenCompra {
  return {
    oc_item_id: 'item-1',
    numero_renglon: 1,
    descripcion: 'Ibuprofeno 400mg x 20',
    cantidad: 10,
    precio_unitario: 1250,
    producto_id: null,
    estado: 'pendiente',
    presupuesto_item_id: null,
    vinculo_origen: null,
    candidatos: [],
    ...overrides,
  }
}

function renderColumna(props: Partial<Parameters<typeof ColumnaPresupuesto>[0]> = {}) {
  render(<ColumnaPresupuesto renglones={[]} renglonOcSeleccionado={null} {...props} />)
}

describe('ColumnaPresupuesto — búsqueda y filtro (spec oc-presupuesto-vinculacion, T2)', () => {
  it('filtra por texto de la descripción, ignorando acentos y mayúsculas', () => {
    renderColumna({
      renglones: [
        presupuesto({ presupuesto_item_id: 'pi-1', descripcion: 'Ibuprofeno 400mg x 20' }),
        presupuesto({ presupuesto_item_id: 'pi-2', descripcion: 'Paracetamol 500mg x 10' }),
      ],
    })

    fireEvent.change(screen.getByLabelText(/buscar en el presupuesto/i), {
      target: { value: 'IBUPROFENO' },
    })

    expect(screen.getByText('Ibuprofeno 400mg x 20')).toBeInTheDocument()
    expect(screen.queryByText('Paracetamol 500mg x 10')).not.toBeInTheDocument()
  })

  it('filtra por número de renglón exacto', () => {
    renderColumna({
      renglones: [
        presupuesto({ presupuesto_item_id: 'pi-1', numero_renglon: 3, descripcion: 'Ibuprofeno' }),
        presupuesto({ presupuesto_item_id: 'pi-2', numero_renglon: 12, descripcion: 'Paracetamol' }),
      ],
    })

    fireEvent.change(screen.getByLabelText(/buscar en el presupuesto/i), { target: { value: '12' } })

    expect(screen.getByText('Paracetamol')).toBeInTheDocument()
    expect(screen.queryByText('Ibuprofeno')).not.toBeInTheDocument()
  })

  it('"Solo candidatos" está deshabilitado sin selección de renglón de OC', () => {
    renderColumna({
      renglones: [presupuesto({ presupuesto_item_id: 'pi-1', descripcion: 'Ibuprofeno' })],
      renglonOcSeleccionado: null,
    })

    expect(screen.getByRole('checkbox', { name: /solo candidatos/i })).toBeDisabled()
  })

  it('con un renglón de OC seleccionado, "Solo candidatos" filtra a los que son candidatos de ese renglón', () => {
    const seleccionado = ordenCompra({
      candidatos: [{ presupuesto_item_id: 'pi-1', similitud: null }],
    })

    renderColumna({
      renglones: [
        presupuesto({ presupuesto_item_id: 'pi-1', descripcion: 'Ibuprofeno' }),
        presupuesto({ presupuesto_item_id: 'pi-2', descripcion: 'Paracetamol' }),
      ],
      renglonOcSeleccionado: seleccionado,
    })

    const toggle = screen.getByRole('checkbox', { name: /solo candidatos/i })
    expect(toggle).not.toBeDisabled()

    fireEvent.click(toggle)

    expect(screen.getByText('Ibuprofeno')).toBeInTheDocument()
    expect(screen.queryByText('Paracetamol')).not.toBeInTheDocument()
  })
})
