import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { RenglonPresupuesto } from '@/lib/api/ocMatching'
import { AvisoReutilizacion } from './AvisoReutilizacion'

function renglon(overrides: Partial<RenglonPresupuesto> = {}): RenglonPresupuesto {
  return {
    presupuesto_item_id: 'pi-1',
    item_proceso_id: 'ip-1',
    numero_renglon: 1,
    descripcion: 'Ibuprofeno 400mg x 20',
    cantidad_ofertada: 100,
    precio_unitario: 1250,
    producto_id: 'prod-1',
    renglones_oc_vinculados: 0,
    renglones_oc_vinculados_otras_oc: 0,
    cantidad_vinculada: 0,
    ...overrides,
  }
}

describe('AvisoReutilizacion (design.md D5, spec § "Relación N:1 permitida, con aviso no bloqueante")', () => {
  it('no muestra nada con un solo vínculo y sin exceso de cantidad', () => {
    render(<AvisoReutilizacion renglon={renglon({ renglones_oc_vinculados: 1, cantidad_vinculada: 50 })} />)
    expect(screen.queryByText(/vinculad/i)).not.toBeInTheDocument()
  })

  it('aparece cuando renglones_oc_vinculados >= 2', () => {
    render(<AvisoReutilizacion renglon={renglon({ renglones_oc_vinculados: 2, cantidad_vinculada: 200 })} />)
    expect(screen.getByText(/ya está vinculado/i)).toBeInTheDocument()
  })

  it('aparece cuando cantidad_vinculada supera cantidad_ofertada, aunque tenga un solo vínculo', () => {
    render(
      <AvisoReutilizacion
        renglon={renglon({ renglones_oc_vinculados: 1, cantidad_vinculada: 150, cantidad_ofertada: 100 })}
      />,
    )
    expect(screen.getByText(/supera/i)).toBeInTheDocument()
  })

  it('nunca deshabilita ningún control externo -- un botón vecino sigue habilitado', () => {
    render(
      <div>
        <AvisoReutilizacion renglon={renglon({ renglones_oc_vinculados: 3, cantidad_vinculada: 300 })} />
        <button type="button">Confirmar</button>
      </div>,
    )
    expect(screen.getByRole('button', { name: /confirmar/i })).not.toBeDisabled()
  })
})
