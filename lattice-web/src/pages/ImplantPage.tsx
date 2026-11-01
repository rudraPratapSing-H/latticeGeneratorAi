import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { PageHeader } from '@/components/layout/PageHeader'
import { ImplantBanner } from '@/features/implant/ImplantBanner'
import { UploadStep } from '@/features/implant/UploadStep'
import { ConfirmStep } from '@/features/implant/ConfirmStep'
import { useCreateImplant, useConfirmImplant } from '@/hooks/useImplant'
import type { CreateImplantResponse, ConfirmImplantRequest } from '@/api/implantTypes'
import { toast } from 'sonner'

export default function ImplantPage() {
  const navigate = useNavigate()
  const createMutation = useCreateImplant()
  const [implantData, setImplantData] = useState<CreateImplantResponse | null>(null)

  const confirmMutation = useConfirmImplant(implantData?.implant_id ?? '')

  const handleUploaded = (file: File | Blob, material: string, description: string) => {
    createMutation.mutate(
      { file, material, description },
      {
        onSuccess: (data) => {
          setImplantData(data)
          toast.success('Mesh uploaded and parsed.')
        },
        onError: (err) => {
          toast.error(err.message || 'Failed to upload mesh')
        },
      },
    )
  }

  const handleConfirm = (req: ConfirmImplantRequest) => {
    if (!implantData) return
    confirmMutation.mutate(req, {
      onSuccess: () => {
        toast.success('Implant configuration confirmed.')
        navigate(`/implant/${implantData.implant_id}/zones`)
      },
      onError: (err) => {
        toast.error(err.message || 'Failed to confirm implant')
      },
    })
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <PageHeader
        title="Implant stem designer (demo)"
        description="Turn a stem model and a short description into zones with lattice or solid sections, using solver-verified lattice cells."
      />

      <ImplantBanner />

      {!implantData ? (
        <UploadStep onUploaded={handleUploaded} isLoading={createMutation.isPending} />
      ) : (
        <ConfirmStep
          implantData={implantData}
          onConfirm={handleConfirm}
          isConfirming={confirmMutation.isPending}
        />
      )}
    </div>
  )
}

