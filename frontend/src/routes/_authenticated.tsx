import { createFileRoute, Outlet } from '@tanstack/react-router'
import { requireAuth } from '@/features/auth/routeGuards'
import { Sidebar } from '@/features/shell/Sidebar'

export const Route = createFileRoute('/_authenticated')({
  beforeLoad: requireAuth,
  component: AuthenticatedLayout,
})

function AuthenticatedLayout() {
  return (
    <div className="flex min-h-svh bg-slate-50">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
    </div>
  )
}
