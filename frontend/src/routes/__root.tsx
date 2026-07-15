import { createRootRouteWithContext, Outlet } from '@tanstack/react-router'
import type { useAuth } from '@/features/auth/AuthContext'

interface RouterContext {
  auth: ReturnType<typeof useAuth>
}

export const Route = createRootRouteWithContext<RouterContext>()({
  component: () => <Outlet />,
})
