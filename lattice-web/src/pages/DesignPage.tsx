import { useEffect } from 'react'
import { DesignForm } from '@/features/design-form/DesignForm'
import { PageHeader } from '@/components/layout/PageHeader'

export default function DesignPage() {
  useEffect(() => {
    document.title = 'Lattice Designer'
  }, [])

  return (
    <div className="space-y-6">
      <div>
        <p className="text-accent mb-2 font-mono text-[11px] font-medium tracking-[0.18em] uppercase">
          Inverse design · solver-verified
        </p>
        <PageHeader
          title="Design a lattice"
          description="Describe the part you need. We'll find lattices that hit it, and prove it with a physics solver."
        />
      </div>
      <DesignForm />
    </div>
  )
}
