import { lazy, Suspense } from 'react'
import { createBrowserRouter } from 'react-router-dom'
import { AppShell } from '@/components/layout/AppShell'
import { ErrorBoundary } from '@/app/ErrorBoundary'
import { Skeleton } from '@/components/ui/skeleton'
import { ENABLE_IMPLANT } from '@/config/env'

const DesignPage = lazy(() => import('@/pages/DesignPage'))
const JobPage = lazy(() => import('@/pages/JobPage'))
const DetailPage = lazy(() => import('@/pages/DetailPage'))
const NotFoundPage = lazy(() => import('@/pages/NotFoundPage'))

// Implant pages
const ImplantPage = lazy(() => import('@/pages/ImplantPage'))
const ImplantZonesPage = lazy(() => import('@/pages/ImplantZonesPage'))
const ImplantResultsPage = lazy(() => import('@/pages/ImplantResultsPage'))
const ImplantFinalPage = lazy(() => import('@/pages/ImplantFinalPage'))

function PageSkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-8 w-48" />
      <Skeleton className="h-4 w-64" />
      <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Skeleton className="h-40" />
        <Skeleton className="h-40" />
      </div>
    </div>
  )
}

const implantRoutes = ENABLE_IMPLANT
  ? [
      {
        path: '/implant',
        element: (
          <ErrorBoundary>
            <Suspense fallback={<PageSkeleton />}>
              <ImplantPage />
            </Suspense>
          </ErrorBoundary>
        ),
      },
      {
        path: '/implant/:implantId/zones',
        element: (
          <ErrorBoundary>
            <Suspense fallback={<PageSkeleton />}>
              <ImplantZonesPage />
            </Suspense>
          </ErrorBoundary>
        ),
      },
      {
        path: '/implant/:implantId/results',
        element: (
          <ErrorBoundary>
            <Suspense fallback={<PageSkeleton />}>
              <ImplantResultsPage />
            </Suspense>
          </ErrorBoundary>
        ),
      },
      {
        path: '/implant/:implantId/result',
        element: (
          <ErrorBoundary>
            <Suspense fallback={<PageSkeleton />}>
              <ImplantFinalPage />
            </Suspense>
          </ErrorBoundary>
        ),
      },
    ]
  : []

export const router = createBrowserRouter([
  {
    element: <AppShell />,
    children: [
      {
        path: '/',
        element: (
          <ErrorBoundary>
            <Suspense fallback={<PageSkeleton />}>
              <DesignPage />
            </Suspense>
          </ErrorBoundary>
        ),
      },
      {
        path: '/job/:jobId',
        element: (
          <ErrorBoundary>
            <Suspense fallback={<PageSkeleton />}>
              <JobPage />
            </Suspense>
          </ErrorBoundary>
        ),
      },
      {
        path: '/job/:jobId/design/:designId',
        element: (
          <ErrorBoundary>
            <Suspense fallback={<PageSkeleton />}>
              <DetailPage />
            </Suspense>
          </ErrorBoundary>
        ),
      },
      ...implantRoutes,
      {
        path: '*',
        element: (
          <ErrorBoundary>
            <Suspense fallback={<PageSkeleton />}>
              <NotFoundPage />
            </Suspense>
          </ErrorBoundary>
        ),
      },
    ],
  },
])
