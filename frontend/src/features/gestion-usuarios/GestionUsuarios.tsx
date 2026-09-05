import { useState } from 'react'
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { useAuth, type Rol } from '@/features/auth/AuthContext'
import { listarDroguerias } from '@/lib/api/droguerias'
import {
  cambiarActivoUsuario,
  cambiarRolUsuario,
  eliminarUsuario,
  listarUsuarios,
  type Usuario,
} from '@/lib/api/usuarios'
import { InvitarUsuarioDialog } from './InvitarUsuarioDialog'

const ROLES_BASE: Rol[] = ['gerencia', 'lider_comercial', 'comercial', 'compras']

export function GestionUsuarios() {
  const { perfil } = useAuth()
  const queryClient = useQueryClient()
  const [aEliminar, setAEliminar] = useState<Usuario | null>(null)
  const { data: usuarios, isPending } = useQuery({
    queryKey: ['usuarios'],
    queryFn: listarUsuarios,
  })
  // Para superadmin esta lista mezcla usuarios de TODAS las empresas — sin
  // esto no había forma de saber a cuál pertenece cada uno.
  const { data: droguerias } = useQuery({ queryKey: ['droguerias'], queryFn: listarDroguerias })
  const nombreEmpresa = (drogueriaId: string | null) =>
    droguerias?.find((d) => d.id === drogueriaId)?.nombre ?? drogueriaId ?? '—'

  // Solo superadmin puede promover a admin (RN-USUARIOS-002/cambiar_rol
  // extendida) — no se muestra la opción si quien mira es un admin.
  const rolesAsignables: Rol[] = perfil?.rol === 'superadmin' ? ['admin', ...ROLES_BASE] : ROLES_BASE

  const cambiarRolMutation = useMutation({
    mutationFn: ({ id, rol }: { id: string; rol: string }) => cambiarRolUsuario(id, rol),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['usuarios'] }),
  })

  const cambiarActivoMutation = useMutation({
    mutationFn: ({ id, activo }: { id: string; activo: boolean }) => cambiarActivoUsuario(id, activo),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['usuarios'] }),
  })

  const eliminarMutation = useMutation({
    mutationFn: (id: string) => eliminarUsuario(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['usuarios'] })
      setAEliminar(null)
    },
  })

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-semibold text-navy">Usuarios</h1>
        <InvitarUsuarioDialog rolesAsignables={rolesAsignables} />
      </div>

      {(cambiarRolMutation.isError || cambiarActivoMutation.isError || eliminarMutation.isError) && (
        <p className="mb-4 text-sm text-red-600">No se pudo aplicar el cambio.</p>
      )}

      {isPending ? (
        <p className="text-sm text-slate-500">Cargando…</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-slate-500">
              <th className="py-2 font-medium">Nombre</th>
              <th className="py-2 font-medium">Empresa</th>
              <th className="py-2 font-medium">Rol</th>
              <th className="py-2 font-medium">Estado</th>
              <th className="py-2 font-medium" />
            </tr>
          </thead>
          <tbody>
            {usuarios?.map((usuario) => (
              <FilaUsuario
                key={usuario.id}
                usuario={usuario}
                nombreEmpresa={nombreEmpresa(usuario.drogueria_id)}
                usuarioActualId={perfil?.id}
                rolesAsignables={rolesAsignables}
                onCambiarRol={(rol) => cambiarRolMutation.mutate({ id: usuario.id, rol })}
                onCambiarActivo={(activo) => cambiarActivoMutation.mutate({ id: usuario.id, activo })}
                onEliminar={() => setAEliminar(usuario)}
              />
            ))}
          </tbody>
        </table>
      )}

      <ConfirmDialog
        open={aEliminar !== null}
        onOpenChange={(open) => !open && setAEliminar(null)}
        title="Eliminar usuario"
        description={`¿Eliminar a ${aEliminar?.nombre ?? ''} ${aEliminar?.apellido ?? ''}? Esta acción no se puede deshacer.`}
        isPending={eliminarMutation.isPending}
        onConfirm={() => aEliminar && eliminarMutation.mutate(aEliminar.id)}
      />
    </div>
  )
}

function FilaUsuario({
  usuario,
  nombreEmpresa,
  usuarioActualId,
  rolesAsignables,
  onCambiarRol,
  onCambiarActivo,
  onEliminar,
}: {
  usuario: Usuario
  nombreEmpresa: string
  usuarioActualId: string | undefined
  rolesAsignables: Rol[]
  onCambiarRol: (rol: string) => void
  onCambiarActivo: (activo: boolean) => void
  onEliminar: () => void
}) {
  // superadmin y sistema no son editables desde acá — mismo criterio que el
  // backend (cambiar_rol/cambiar_activo los rechaza explícitamente). Tampoco
  // podés cambiarte el rol/estado a vos mismo (mismo criterio que eliminar).
  const esProtegido = usuario.rol === 'superadmin' || usuario.rol === 'sistema'
  const esUnoMismo = usuario.id === usuarioActualId
  const noEditable = esProtegido || esUnoMismo
  // El rol actual siempre tiene que estar en las opciones, aunque quien mira
  // no pueda asignarlo (ej. un admin viendo la fila de otro admin).
  const opciones: string[] = rolesAsignables.some((rol) => rol === usuario.rol)
    ? rolesAsignables
    : [usuario.rol, ...rolesAsignables]

  return (
    <tr className="border-b border-slate-100">
      <td className="py-2">
        {usuario.nombre} {usuario.apellido ?? ''}
      </td>
      <td className="py-2 text-slate-500">{usuario.drogueria_id ? nombreEmpresa : '—'}</td>
      <td className="py-2">
        {noEditable ? (
          <span className="text-slate-500">{usuario.rol}</span>
        ) : (
          <select
            value={usuario.rol}
            onChange={(event) => onCambiarRol(event.target.value)}
            className="rounded-md border border-slate-300 px-2 py-1 text-sm"
          >
            {opciones.map((rol) => (
              <option key={rol} value={rol}>
                {rol}
              </option>
            ))}
          </select>
        )}
      </td>
      <td className="py-2">
        <span className={usuario.activo ? 'text-emerald-600' : 'text-slate-400'}>
          {usuario.activo ? 'Activo' : 'Desactivado'}
        </span>
      </td>
      <td className="py-2 text-right space-x-3">
        {!noEditable && (
          <button
            type="button"
            onClick={() => onCambiarActivo(!usuario.activo)}
            className="text-sm font-medium text-accent hover:underline"
          >
            {usuario.activo ? 'Desactivar' : 'Reactivar'}
          </button>
        )}
        {!noEditable && (
          <button
            type="button"
            onClick={onEliminar}
            className="text-sm font-medium text-red-600 hover:underline"
          >
            Eliminar
          </button>
        )}
      </td>
    </tr>
  )
}
