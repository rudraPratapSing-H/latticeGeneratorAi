import { InlineAlert } from '@/components/feedback/InlineAlert'

export function ImplantBanner() {
  return (
    <InlineAlert variant="warning" className="border-warning/30 bg-warning/10">
      <div className="flex items-start gap-2.5">
        <div className="text-xs text-text space-y-0.5">
          <p className="font-semibold text-warning">
            Design demo, not a medical device.
          </p>
          <p className="text-muted">
            Bone and load numbers are placeholders. Lattice stiffness and strength are solver results for an infinite lattice, strength is static (no fatigue), and the finite-block stiffness is only an estimate. Nothing here is a clinical, safety or regulatory claim.
          </p>
        </div>
      </div>
    </InlineAlert>
  )
}

