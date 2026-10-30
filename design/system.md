# Design system — Droguería Nueva Era (frontend)

Captured read-only from the project sources. Tailwind v4 is used with its default palette; only `navy`, `accent` and the fonts are custom. Hex values of Tailwind defaults are the sRGB equivalents of Tailwind v4's oklch palette.

Sources:
- `frontend/src/index.css` (`@theme`)
- Tailwind default palette, as used across `frontend/src/features/**/*.tsx` (usage counts from a grep of class names)
- `frontend/src/features/shell/Sidebar.tsx` (app shell)
- `frontend/src/features/proceso-matching/components/RenglonMatchingFila.tsx` (estado badges)

## Colors

| Token | Value | Usage | Source |
| --- | --- | --- | --- |
| `navy` | `#0f172a` | Sidebar background, primary button background, strong text | `frontend/src/index.css` |
| `accent` | `#0369a1` | Links, active nav (`accent/20`), focus rings | `frontend/src/index.css` |
| `slate-50` | `#f8fafc` | Subtle panels, hover rows | Tailwind default |
| `slate-100` | `#f1f5f9` | Row dividers, neutral badge background | Tailwind default |
| `slate-200` | `#e2e8f0` | Borders of cards and tables | Tailwind default |
| `slate-300` | `#cbd5e1` | Input and secondary button borders | Tailwind default |
| `slate-400` | `#94a3b8` | Placeholder, sidebar meta text | Tailwind default |
| `slate-500` | `#64748b` | Secondary text, table headers | Tailwind default |
| `slate-600` | `#475569` | Body secondary text | Tailwind default |
| `slate-700` | `#334155` | Secondary button text | Tailwind default |
| `slate-900` | `#0f172a` | Primary text | Tailwind default |
| `amber-50` / `amber-200` / `amber-800` | `#fffbeb` / `#fde68a` / `#92400e` | Estado "pendiente" badge | `RenglonMatchingFila.tsx` |
| `sky-50` / `sky-200` / `sky-800` | `#f0f9ff` / `#bae6fd` / `#075985` | Estado "sugerido" badge | `RenglonMatchingFila.tsx` |
| `emerald-50` / `emerald-200` / `emerald-700` / `emerald-800` | `#ecfdf5` / `#a7f3d0` / `#047857` / `#065f46` | Estado "automático" / "confirmado", success | `RenglonMatchingFila.tsx` |
| `red-50` / `red-200` / `red-600` / `red-700` | `#fef2f2` / `#fecaca` / `#dc2626` / `#b91c1c` | Errors and alerts | Tailwind default |
| `white` | `#ffffff` | Page and card background | Tailwind default |

## Typography

| Token | Value | Source |
| --- | --- | --- |
| `font-sans` | `"Fira Sans", ui-sans-serif, system-ui, sans-serif` (weights 400, 500, 600, 700) | `frontend/src/index.css` |
| `font-mono` | `"Fira Code", ui-monospace, monospace` (weights 400, 500) | `frontend/src/index.css` |

Scale in use (Tailwind defaults): `text-xs` 12/16, `text-sm` 14/20 (body of every table and form), `text-lg` 18/28 (sidebar brand), `text-xl` 20/28 (page title, `font-semibold`). Numbers in tables use `tabular-nums`. Table headers: `text-xs font-medium uppercase tracking-wide text-slate-500`.

Artboards cannot load the Google Fonts import, so they use the same stack: Fira Sans when installed locally, else the system UI font.

## Spacing

Tailwind 4 px scale. Common: page `px-6 py-10`, `max-w-6xl` content, section gap `space-y-6`, cells `py-3 pr-4`, buttons `px-2.5 py-1` (xs) and `px-3 py-2` (sm), sidebar `w-64` (256 px).

## Radius

| Token | Value | Usage |
| --- | --- | --- |
| `rounded-md` | 6 px | Default: buttons, inputs, panels, alerts (most used) |
| `rounded-lg` | 8 px | Cards |
| `rounded-xl` | 12 px | Dialogs |
| `rounded-full` | 9999 px | Estado badges |

## Shadows

| Token | Value | Usage |
| --- | --- | --- |
| `shadow-sm` | `0 1px 3px 0 rgb(0 0 0 / .1), 0 1px 2px -1px rgb(0 0 0 / .1)` | Cards |
| `shadow-xl` | `0 20px 25px -5px rgb(0 0 0 / .1), 0 8px 10px -6px rgb(0 0 0 / .1)` | Dialogs |

## Components

- **App shell**: left sidebar `w-64 bg-navy text-slate-100`, brand "Droguería Nueva Era" `text-lg font-semibold`; nav items `rounded-md px-3 py-2 text-sm text-slate-200`, hover `bg-white/5`, active `bg-accent/20 text-white`. Content on white.
- **Primary button**: `rounded-md bg-navy text-white font-medium`, disabled `opacity-40`.
- **Secondary button**: `rounded-md border border-slate-300 text-slate-700 font-medium`, hover `bg-slate-50`.
- **Input**: `rounded-md border border-slate-300 px-3 py-2 text-sm`.
- **Estado badge**: `rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset`, colors per estado above; sin match uses `slate-100 / slate-200 / slate-700`.
- **Table**: header row `border-b border-slate-200`, body `divide-y divide-slate-100`.
- **Alert**: `rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700`.
