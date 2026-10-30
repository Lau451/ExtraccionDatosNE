/** A keyboard key hint, as in the matching screen's shortcut legend. */
export function Tecla({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="rounded border border-b-2 border-slate-300 bg-white px-1.5 font-mono text-xs text-slate-700">
      {children}
    </kbd>
  )
}
