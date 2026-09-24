import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { PresupuestosCandidatosOut } from '@/lib/api/ocMatching'
import { SelectorPresupuesto } from './SelectorPresupuesto'

function candidatosOut(overrides: Partial<PresupuestosCandidatosOut> = {}): PresupuestosCandidatosOut {
  return {
    orden_compra_id: 'oc-1',
    cliente_id: 'cli-1',
    razon_social_cliente: 'Hospital Central',
    presupuestos_del_cliente: 0,
    candidatos: [],
    presupuesto_sugerido_id: null,
    advertencias: [],
    ...overrides,
  }
}

describe('SelectorPresupuesto (design.md D2, spec oc-presupuesto-candidato)', () => {
  it('con un único candidato lo muestra como sugerido pero no viene elegido', () => {
    const onSeleccionar = vi.fn()
    render(
      <SelectorPresupuesto
        data={candidatosOut({
          presupuestos_del_cliente: 1,
          presupuesto_sugerido_id: 'pre-1',
          candidatos: [
            {
              presupuesto_id: 'pre-1',
              proceso_comercial_id: 'proc-1',
              nombre_proceso: 'Compra hospital',
              numero_presupuesto: '00246033',
              estado: 'generado',
              generado_at: '2026-01-01T00:00:00Z',
              cantidad_items: 2,
              renglones_oc_con_coincidencia: 2,
              renglones_oc_totales: 2,
            },
          ],
        })}
        presupuestoIdSeleccionado={null}
        onSeleccionar={onSeleccionar}
      />,
    )

    expect(screen.getByText(/00246033/)).toBeInTheDocument()
    expect(screen.getByText(/sugerido/i)).toBeInTheDocument()
    expect(screen.getByRole('radio')).not.toBeChecked()
  })

  it('un click en un candidato lo reporta al padre, no lo marca elegido por sí mismo', () => {
    const onSeleccionar = vi.fn()
    render(
      <SelectorPresupuesto
        data={candidatosOut({
          presupuestos_del_cliente: 1,
          presupuesto_sugerido_id: 'pre-1',
          candidatos: [
            {
              presupuesto_id: 'pre-1',
              proceso_comercial_id: 'proc-1',
              nombre_proceso: 'Compra hospital',
              numero_presupuesto: null,
              estado: 'generado',
              generado_at: '2026-01-01T00:00:00Z',
              cantidad_items: 2,
              renglones_oc_con_coincidencia: 2,
              renglones_oc_totales: 2,
            },
          ],
        })}
        presupuestoIdSeleccionado={null}
        onSeleccionar={onSeleccionar}
      />,
    )

    screen.getByRole('radio').dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(onSeleccionar).toHaveBeenCalledWith('pre-1')
    // el padre no volvió a renderizar con la elección -- sigue sin marcarse.
    expect(screen.getByRole('radio')).not.toBeChecked()
  })

  it('distingue "sin presupuestos para este cliente" de "tiene N, ninguno coincide"', () => {
    const { rerender } = render(
      <SelectorPresupuesto
        data={candidatosOut({ presupuestos_del_cliente: 0, candidatos: [] })}
        presupuestoIdSeleccionado={null}
        onSeleccionar={vi.fn()}
      />,
    )
    expect(screen.getByText(/no tiene presupuestos/i)).toBeInTheDocument()

    rerender(
      <SelectorPresupuesto
        data={candidatosOut({ presupuestos_del_cliente: 3, candidatos: [] })}
        presupuestoIdSeleccionado={null}
        onSeleccionar={vi.fn()}
      />,
    )
    expect(screen.getByText(/3 presupuestos/i)).toBeInTheDocument()
    expect(screen.getByText(/ninguno coincide/i)).toBeInTheDocument()
  })
})
