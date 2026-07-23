import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider, createRouter } from '@tanstack/react-router'
import { AuthProvider, useAuth } from '@/features/auth/AuthContext'
import './index.css'
import { routeTree } from './routeTree.gen'

const router = createRouter({
  routeTree,
  context: { auth: undefined! },
})

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}

const queryClient = new QueryClient()

function InnerApp() {
  const auth = useAuth()
  // Esperar los dos pasos asíncronos (sesión + perfil) antes de montar el
  // router — requireRole() en routeGuards.ts decide en base a auth.perfil,
  // y si el router se monta antes de que llegue, rebota a "/" por las dudas.
  if (auth.loading || auth.perfilLoading) return null
  return <RouterProvider router={router} context={{ auth }} />
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <InnerApp />
      </AuthProvider>
    </QueryClientProvider>
  </StrictMode>,
)
