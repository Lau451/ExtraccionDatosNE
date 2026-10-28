import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ConfirmDialog } from './ConfirmDialog'

// Sticky table cells (z-10) and the sticky action bar (z-20) of the
// validation screen painted above an overlay without z-index, so they stayed
// bright instead of dimmed. Every dialog layer must sit above them.
describe('ConfirmDialog — capas', () => {
  it('el overlay y el contenido quedan por encima de los elementos sticky (z-50)', () => {
    render(
      <ConfirmDialog
        open
        onOpenChange={() => {}}
        title="Confirmar validación"
        description="Se van a materializar las filas."
        onConfirm={() => {}}
      />,
    )

    const dialogo = screen.getByRole('dialog')
    expect(dialogo).toHaveClass('z-50')
    expect(document.querySelector('.bg-black\\/40')).toHaveClass('z-50')
  })
})

describe('Todos los diálogos — capas', () => {
  const fuentes = import.meta.glob('/src/**/*.tsx', {
    query: '?raw',
    import: 'default',
    eager: true,
  }) as Record<string, string>

  const capas = Object.entries(fuentes).flatMap(([archivo, codigo]) =>
    [...codigo.matchAll(/<Dialog\.(Overlay|Content)\b[^>]*className="([^"]*)"/g)].map(
      ([, capa, clases]) => ({ archivo, capa, clases }),
    ),
  )

  it('encuentra los diálogos de la app', () => {
    expect(capas.length).toBeGreaterThan(20)
  })

  it('ningún Dialog.Overlay ni Dialog.Content queda sin z-50', () => {
    const sinZ = capas
      .filter(({ clases }) => !clases.split(/\s+/).includes('z-50'))
      .map(({ archivo, capa }) => `${archivo} (${capa})`)
    expect(sinZ).toEqual([])
  })
})
