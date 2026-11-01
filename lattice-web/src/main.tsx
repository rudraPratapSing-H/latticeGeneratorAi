import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router-dom'
import { Providers } from '@/app/providers'
import { router } from '@/app/router'
import './index.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Providers>
      <RouterProvider router={router} />
    </Providers>
  </StrictMode>,
)

// Dev-only: mount mock controls
if (import.meta.env.DEV && import.meta.env.VITE_USE_MOCK === 'true') {
  import('@/components/dev/MockControls').then(({ mountMockControls }) => {
    mountMockControls()
  })
}
