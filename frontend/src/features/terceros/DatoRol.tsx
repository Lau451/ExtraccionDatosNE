/** Campo de un rol que viene de Progress: se muestra, no se edita. */
export function DatoRol({ etiqueta, valor }: { etiqueta: string; valor: string }) {
  return (
    <div>
      <dt className="text-slate-500">{etiqueta}</dt>
      <dd className="text-slate-800">{valor}</dd>
    </div>
  )
}
