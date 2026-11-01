import { useEffect, useMemo, useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { toast } from 'sonner'
import { useMaterials } from '@/hooks/useMaterials'
import { useCreateDesign } from '@/hooks/useCreateDesign'
import { useReach } from '@/hooks/useReach'
import { useLimits } from '@/hooks/useLimits'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Select, SelectItem } from '@/components/ui/select'
import { NumberField } from '@/components/ui/number-field'
import { Switch } from '@/components/ui/switch'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import { InfoTip } from '@/components/ui/info-tip'
import { InlineAlert } from '@/components/feedback/InlineAlert'
import { ErrorState } from '@/components/feedback/ErrorState'
import { Dialog, DialogContent, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { AxisFields } from '@/features/design-form/AxisFields'
import { ModeSelector } from '@/features/design-form/ModeSelector'
import { ReachBadge } from '@/features/design-form/ReachBadge'
import { ClosestAchievable } from '@/features/design-form/ClosestAchievable'
import { SummaryPanel } from '@/features/design-form/SummaryPanel'
import { createFormSchema } from '@/features/design-form/formSchema'
import { buildRequest } from '@/features/design-form/buildRequest'
import { DEFAULT_VALUES, EXAMPLE_VALUES } from '@/features/design-form/defaults'
import type { DesignFormValues } from '@/features/design-form/defaults'
import type { DesignRequest, ReachResponse, TargetMode } from '@/api/types'
import type { ApiError } from '@/api/client'
import { tilesPerAxis, isIntegerMultiple, partVolumeCm3, solidMassG } from '@/lib/units'
import { DATASET_DENSITIES } from '@/config/constants'
import { FORM_BOUNDS } from '@/config/limits'
import { Beaker, ChevronDown, RotateCcw, Settings, AlertTriangle } from 'lucide-react'

export function DesignForm() {
  const {
    data: materials,
    isLoading: materialsLoading,
    error: materialsError,
    refetch: refetchMaterials,
  } = useMaterials()
  const createDesign = useCreateDesign()
  const [showSearch, setShowSearch] = useState(false)
  const [showAdvStrength, setShowAdvStrength] = useState(false)
  const [showAdvWeight, setShowAdvWeight] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [forceConfirmOpen, setForceConfirmOpen] = useState(false)

  // Track user-adjusted fields (from accepting reach suggestions)
  const [adjustedFields, setAdjustedFields] = useState<Set<string>>(new Set())
  const [storedOriginalValues, setStoredOriginalValues] = useState<Partial<DesignFormValues>>({})

  const schema = useMemo(() => createFormSchema(materials), [materials])

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    reset,
    formState: { errors },
  } = useForm<DesignFormValues>({
    defaultValues: DEFAULT_VALUES,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    resolver: zodResolver(schema) as any,
    mode: 'onTouched',
    reValidateMode: 'onChange',
  })

  const formValues = watch()

  // The backend has one material today: select the first one so the dataset hints work without an extra click.
  const firstMaterialId = materials?.[0]?.id
  useEffect(() => {
    if (firstMaterialId && !formValues.material) setValue('material', firstMaterialId)
  }, [firstMaterialId, formValues.material, setValue])

  // Debounced request calculation for reach query (400ms)
  const [debouncedRequest, setDebouncedRequest] = useState<DesignRequest | null>(null)
  const [debouncedHash, setDebouncedHash] = useState('')

  useEffect(() => {
    const timer = setTimeout(() => {
      try {
        const req = buildRequest(formValues)
        // Check if there is at least one target before triggering reach
        const hasTarget =
          Object.values(req.target.stiffness_gpa).some((v) => v !== null) ||
          ('strength_mpa' in req.target &&
            Object.values(req.target.strength_mpa).some((v) => v !== null)) ||
          ('yield_strength_mpa' in req.target &&
            Object.values(req.target.yield_strength_mpa).some((v) => v !== null))

        if (hasTarget && req.material) {
          setDebouncedRequest(req)
          setDebouncedHash(JSON.stringify(req))
        } else {
          setDebouncedRequest(null)
          setDebouncedHash('')
        }
      } catch {
        setDebouncedRequest(null)
        setDebouncedHash('')
      }
    }, 400)

    return () => clearTimeout(timer)
  }, [formValues])

  const { data: reachData } = useReach(debouncedRequest, debouncedHash)

  const handleAcceptNearest = (nearest: ReachResponse['nearest']) => {
    // Save current values to restore later on Undo
    setStoredOriginalValues({
      stiffnessX: formValues.stiffnessX,
      stiffnessY: formValues.stiffnessY,
      stiffnessZ: formValues.stiffnessZ,
      strengthX: formValues.strengthX,
      strengthY: formValues.strengthY,
      strengthZ: formValues.strengthZ,
    })

    const newAdjusted = new Set(adjustedFields)

    const reqStiffness = reachData?.requested?.stiffness_gpa
    const reqStrength = reachData?.requested?.strength_mpa

    if (reqStiffness) {
      if (reqStiffness[0] != null && nearest.stiffness_gpa?.[0] != null) {
        setValue('stiffnessX', nearest.stiffness_gpa[0].toFixed(2), { shouldValidate: true })
        newAdjusted.add('stiffnessX')
      }
      if (reqStiffness[1] != null && nearest.stiffness_gpa?.[1] != null && !formValues.stiffnessSameAll) {
        setValue('stiffnessY', nearest.stiffness_gpa[1].toFixed(2), { shouldValidate: true })
        newAdjusted.add('stiffnessY')
      }
      if (reqStiffness[2] != null && nearest.stiffness_gpa?.[2] != null && !formValues.stiffnessSameAll) {
        setValue('stiffnessZ', nearest.stiffness_gpa[2].toFixed(2), { shouldValidate: true })
        newAdjusted.add('stiffnessZ')
      }
    }

    if (reqStrength) {
      if (reqStrength[0] != null && nearest.strength_mpa?.[0] != null) {
        setValue('strengthX', nearest.strength_mpa[0].toFixed(1), { shouldValidate: true })
        newAdjusted.add('strengthX')
      }
      if (reqStrength[1] != null && nearest.strength_mpa?.[1] != null && !formValues.strengthSameAll) {
        setValue('strengthY', nearest.strength_mpa[1].toFixed(1), { shouldValidate: true })
        newAdjusted.add('strengthY')
      }
      if (reqStrength[2] != null && nearest.strength_mpa?.[2] != null && !formValues.strengthSameAll) {
        setValue('strengthZ', nearest.strength_mpa[2].toFixed(1), { shouldValidate: true })
        newAdjusted.add('strengthZ')
      }
    }

    setAdjustedFields(newAdjusted)
    toast.success('Applied nearest achievable values to targets.')
  }

  const handleUndoAdjustments = () => {
    if (storedOriginalValues.stiffnessX !== undefined) setValue('stiffnessX', storedOriginalValues.stiffnessX)
    if (storedOriginalValues.stiffnessY !== undefined) setValue('stiffnessY', storedOriginalValues.stiffnessY)
    if (storedOriginalValues.stiffnessZ !== undefined) setValue('stiffnessZ', storedOriginalValues.stiffnessZ)
    if (storedOriginalValues.strengthX !== undefined) setValue('strengthX', storedOriginalValues.strengthX)
    if (storedOriginalValues.strengthY !== undefined) setValue('strengthY', storedOriginalValues.strengthY)
    if (storedOriginalValues.strengthZ !== undefined) setValue('strengthZ', storedOriginalValues.strengthZ)

    setAdjustedFields(new Set())
    setStoredOriginalValues({})
    toast.info('Restored requested targets.')
  }

  const submitWithForce = (force: boolean) => {
    setSubmitError(null)
    const request = buildRequest(formValues, { force })
    createDesign.mutate(
      { request, metadata: { adjustedFields: Array.from(adjustedFields) } },
      {
        onError: (err: Error) => {
          const apiErr = err as ApiError
          const msg = apiErr.message ?? 'An error occurred'
          setSubmitError(msg)
          toast.error(msg)
        },
      },
    )
  }

  const onError = () => {
    const firstError = document.querySelector('[aria-invalid="true"]')
    if (firstError) {
      firstError.scrollIntoView({ behavior: 'smooth', block: 'center' })
      ;(firstError as HTMLElement).focus?.()
    }
  }

  const onSubmit = handleSubmit((_data: DesignFormValues) => {
    if (reachData?.level === 'infeasible') {
      setForceConfirmOpen(true)
      return
    }
    submitWithForce(false)
  }, onError)

  const { data: limits } = useLimits(formValues.material || undefined)

  const fillExample = () => {
    const matId = materials?.find((m) => m.id === 'ti64')?.id ?? materials?.[0]?.id ?? ''
    // The example comes from what the dataset actually holds (median stiffness and strength at density 0.15, from
    // /api/limits), so it is a target a stored lattice can meet. Without limits the built-in example is used.
    const row = limits?.densities?.['0.15']
    const mat = materials?.find((m) => m.id === matId)
    let example = EXAMPLE_VALUES
    if (row && mat) {
      const sig = (v: number) => String(Number(v.toPrecision(3)))
      const vol = partVolumeCm3([40, 40, 40])
      example = {
        ...EXAMPLE_VALUES,
        stiffnessX: sig(row.stiffness_gpa.median),
        stiffnessY: sig(row.stiffness_gpa.median),
        stiffnessZ: sig(row.stiffness_gpa.median),
        strengthX: sig(row.strength_mpa.median),
        strengthY: sig(row.strength_mpa.median),
        strengthZ: sig(row.strength_mpa.median),
        strengthDontCareZ: false,
        maxMassG: sig(0.15 * solidMassG(vol, mat.density_g_cm3)),
      }
    }
    reset({ ...example, material: matId })
    setAdjustedFields(new Set())
  }

  // Computed hints
  const cellMm = parseFloat(formValues.cellMm) || 0
  const sizeX = parseFloat(formValues.partSizeX) || 0
  const sizeY = parseFloat(formValues.partSizeY) || 0
  const sizeZ = parseFloat(formValues.partSizeZ) || 0
  const cellWarning =
    cellMm > 0 &&
    sizeX > 0 &&
    (!isIntegerMultiple(sizeX, cellMm) ||
      !isIntegerMultiple(sizeY, cellMm) ||
      !isIntegerMultiple(sizeZ, cellMm))
      ? 'Part size is not an integer multiple of cell size'
      : undefined

  // Density & Mass warnings
  const selectedMaterial = materials?.find((m) => m.id === formValues.material)
  const partVol = partVolumeCm3([sizeX, sizeY, sizeZ])
  const solidMass = selectedMaterial ? solidMassG(partVol, selectedMaterial.density_g_cm3) : 0

  let massWarning: string | undefined
  if (selectedMaterial && solidMass > 0 && !formValues.useRelDensity) {
    const massNum = parseFloat(formValues.maxMassG)
    if (isFinite(massNum) && massNum > 0) {
      const impliedRd = massNum / solidMass
      if (impliedRd < 0.05) {
        const minMass = (0.05 * solidMass).toFixed(1)
        massWarning = `Lightest possible mass ≈ ${minMass} g (estimate for ρ = 0.05)`
      } else if (impliedRd > 0.25) {
        massWarning = 'The search will use ρ = 0.25 (maximum dataset density)'
      }
    }
  }

  let relDensityWarning: string | undefined
  if (formValues.useRelDensity) {
    const rdNum = parseFloat(formValues.relDensity)
    if (
      isFinite(rdNum) &&
      rdNum > 0 &&
      rdNum < 1 &&
      !DATASET_DENSITIES.some((d) => Math.abs(d - rdNum) < 0.001)
    ) {
      relDensityWarning = 'The predictor was not trained or tested between the dataset densities (0.05, 0.15, 0.25).'
    }
  }

  const isInfeasible = reachData?.level === 'infeasible'

  return (
    <form onSubmit={onSubmit} noValidate>
      <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[1fr_320px]">
        {/* Left: form sections */}
        <div className="space-y-5">
          {submitError && (
            <InlineAlert variant="error">
              <div className="flex flex-col gap-2">
                <span>{submitError}</span>
                {isInfeasible && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="self-start text-xs"
                    onClick={() => setForceConfirmOpen(true)}
                  >
                    Run anyway (override bound checks)
                  </Button>
                )}
              </div>
            </InlineAlert>
          )}

          {/* Material */}
          <Card className="animate-card-in">
            <CardHeader>
              <h2 className="text-text text-base font-semibold"><span className="text-accent/80 mr-2 font-mono text-[11px] font-medium tracking-wider">01</span>Material</h2>
            </CardHeader>
            <CardContent>
              {materialsLoading ? (
                <Skeleton className="h-10 w-full" />
              ) : materialsError ? (
                <ErrorState
                  error={materialsError as Error}
                  onRetry={() => {
                    refetchMaterials()
                  }}
                  className="py-4"
                />
              ) : (
                <div className="space-y-3">
                  <Select
                    value={formValues.material}
                    onChange={(v) => setValue('material', v, { shouldValidate: true })}
                    placeholder="Choose a material"
                    error={errors.material?.message}
                  >
                    {materials?.map((m) => (
                      <SelectItem key={m.id} value={m.id}>
                        <div>
                          <span className="font-medium">{m.name}</span>
                          <span className="text-muted ml-2 text-xs">
                            E {m.E_gpa} GPa · σy {m.yield_mpa} MPa · {m.density_g_cm3} g/cm³
                          </span>
                        </div>
                      </SelectItem>
                    ))}
                  </Select>
                  {formValues.material && materials && (
                    <div className="flex flex-wrap gap-2">
                      {(() => {
                        const m = materials.find((mat) => mat.id === formValues.material)
                        if (!m) return null
                        return (
                          <>
                            <Badge variant="neutral">E {m.E_gpa} GPa</Badge>
                            <Badge variant="neutral">σy {m.yield_mpa} MPa</Badge>
                            <Badge variant="neutral">{m.density_g_cm3} g/cm³</Badge>
                          </>
                        )
                      })()}
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Stiffness */}
          <Card className="animate-card-in" style={{ animationDelay: '60ms' }}>
            <CardHeader>
              <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
                <h2 className="text-text text-base font-semibold">
                  <span className="text-accent/80 mr-2 font-mono text-[11px] font-medium tracking-wider">02</span>Stiffness targets
                  <span className="text-muted ml-1.5 text-xs font-normal">(GPa)</span>
                </h2>
                <ModeSelector
                  value={formValues.stiffnessMode}
                  onChange={(v: TargetMode) => setValue('stiffnessMode', v)}
                  tolerancePct={formValues.tolerancePct}
                />
              </div>
            </CardHeader>
            <CardContent>
              <AxisFields
                prefix="stiffness"
                unit="GPa"
                register={register}
                errors={errors}
                watch={watch}
                setValue={setValue as (name: keyof DesignFormValues, value: unknown) => void}
                adjustedFields={adjustedFields}
              />
            </CardContent>
          </Card>

          {/* Strength */}
          <Card className="animate-card-in" style={{ animationDelay: '120ms' }}>
            <CardHeader>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <h2 className="text-text text-base font-semibold">
                    <span className="text-accent/80 mr-2 font-mono text-[11px] font-medium tracking-wider">03</span>Strength targets
                    <span className="text-muted ml-1.5 text-xs font-normal">(MPa)</span>
                  </h2>
                  <InfoTip content="Load the design takes before failing: the lower of yield and buckling." />
                </div>
                <ModeSelector
                  value={formValues.strengthMode}
                  onChange={(v: TargetMode) => setValue('strengthMode', v)}
                  tolerancePct={formValues.tolerancePct}
                />
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <AxisFields
                prefix="strength"
                unit="MPa"
                register={register}
                errors={errors}
                watch={watch}
                setValue={setValue as (name: keyof DesignFormValues, value: unknown) => void}
                adjustedFields={adjustedFields}
              />

              <button
                type="button"
                onClick={() => setShowAdvStrength(!showAdvStrength)}
                className="text-muted hover:text-text flex cursor-pointer items-center gap-1 text-xs"
              >
                <ChevronDown
                  className={`h-3.5 w-3.5 transition-transform ${showAdvStrength ? 'rotate-180' : ''}`}
                />
                Advanced strength definition
              </button>

              {showAdvStrength && (
                <div className="border-line animate-fade-in space-y-2 border-l-2 pl-3">
                  <p className="text-muted text-xs">Strength failure criterion</p>
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => setValue('strengthType', 'effective')}
                      className={`cursor-pointer rounded-md border px-3 py-1.5 text-xs font-medium transition-colors ${
                        formValues.strengthType === 'effective'
                          ? 'border-accent bg-accent-soft text-accent'
                          : 'border-line text-muted hover:text-text'
                      }`}
                    >
                      Effective strength (yield & buckling) [Default]
                    </button>
                    <button
                      type="button"
                      onClick={() => setValue('strengthType', 'yield_only')}
                      className={`cursor-pointer rounded-md border px-3 py-1.5 text-xs font-medium transition-colors ${
                        formValues.strengthType === 'yield_only'
                          ? 'border-accent bg-accent-soft text-accent'
                          : 'border-line text-muted hover:text-text'
                      }`}
                    >
                      Yield only (tension)
                    </button>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Reachability & Dataset Coverage */}
          {reachData && (
            <div className="space-y-3">
              <ReachBadge
                level={reachData.level}
                distancePct={reachData.distance_pct}
                message={reachData.message}
              />
              <ClosestAchievable
                reach={reachData}
                isAdjusted={adjustedFields.size > 0}
                onAccept={handleAcceptNearest}
                onUndo={handleUndoAdjustments}
              />
            </div>
          )}

          {/* Weight & Part */}
          <Card className="animate-card-in" style={{ animationDelay: '180ms' }}>
            <CardHeader>
              <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
                <h2 className="text-text text-base font-semibold"><span className="text-accent/80 mr-2 font-mono text-[11px] font-medium tracking-wider">04</span>Weight & part</h2>
                <ModeSelector
                  value={formValues.weightMode}
                  onChange={(v: TargetMode) => setValue('weightMode', v)}
                />
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {!formValues.useRelDensity ? (
                <NumberField
                  {...register('maxMassG')}
                  label="Max mass"
                  unit="g"
                  error={errors.maxMassG?.message}
                  warning={massWarning}
                  placeholder="60"
                />
              ) : (
                <NumberField
                  {...register('relDensity')}
                  label="Relative density"
                  unit="—"
                  hint="Dataset densities: 0.05, 0.15, 0.25"
                  error={errors.relDensity?.message}
                  warning={relDensityWarning}
                  placeholder="0.15"
                />
              )}

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <NumberField
                  {...register('partSizeX')}
                  label="Size X"
                  unit="mm"
                  error={errors.partSizeX?.message}
                />
                <NumberField
                  {...register('partSizeY')}
                  label="Size Y"
                  unit="mm"
                  error={errors.partSizeY?.message}
                />
                <NumberField
                  {...register('partSizeZ')}
                  label="Size Z"
                  unit="mm"
                  error={errors.partSizeZ?.message}
                />
              </div>

              <div className="space-y-2">
                <NumberField
                  {...register('cellMm')}
                  label="Unit-cell size"
                  unit="mm"
                  error={errors.cellMm?.message}
                  warning={cellWarning}
                />
                {cellMm > 0 && sizeX > 0 && (
                  <p className="text-muted text-xs">
                    Tiles: {tilesPerAxis(sizeX, cellMm)} × {tilesPerAxis(sizeY, cellMm)} ×{' '}
                    {tilesPerAxis(sizeZ, cellMm)}
                  </p>
                )}
              </div>

              <button
                type="button"
                onClick={() => setShowAdvWeight(!showAdvWeight)}
                className="text-muted hover:text-text flex cursor-pointer items-center gap-1 text-xs"
              >
                <ChevronDown
                  className={`h-3.5 w-3.5 transition-transform ${showAdvWeight ? 'rotate-180' : ''}`}
                />
                Advanced density settings
              </button>

              {showAdvWeight && (
                <div className="border-line animate-fade-in space-y-2 border-l-2 pl-3">
                  <Switch
                    checked={formValues.useRelDensity}
                    onChange={(v) => setValue('useRelDensity', v)}
                    label="Specify relative density instead of mass"
                  />
                  <p className="text-muted text-xs">
                    Default dataset densities are 0.05, 0.15, 0.25. Non-dataset densities trigger extra solver iterations.
                  </p>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Search settings (collapsed) */}
          <button
            type="button"
            onClick={() => setShowSearch(!showSearch)}
            className="text-muted hover:text-text flex cursor-pointer items-center gap-2 text-sm"
          >
            <Settings className="h-4 w-4" />
            Search settings
            <ChevronDown
              className={`h-3.5 w-3.5 transition-transform ${showSearch ? 'rotate-180' : ''}`}
            />
          </button>

          {showSearch && (
            <Card className="animate-fade-in">
              <CardContent className="space-y-4 pt-5">
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <NumberField
                    {...register('tolerancePct')}
                    label="Tolerance"
                    unit="%"
                    hint={`${FORM_BOUNDS.tolerance_pct.min}–${FORM_BOUNDS.tolerance_pct.max}%`}
                    error={errors.tolerancePct?.message}
                  />
                  <NumberField
                    {...register('nResults')}
                    label="Number of results"
                    unit="designs"
                    hint={`${FORM_BOUNDS.n_results.min}–${FORM_BOUNDS.n_results.max}`}
                    error={errors.nResults?.message}
                  />
                </div>
              </CardContent>
            </Card>
          )}

          {/* Actions — mobile: sticky bottom bar */}
          <div className="flex items-center justify-between gap-3 py-3 lg:pb-0">
            <div className="flex gap-2">
              <Button type="button" variant="ghost" size="sm" onClick={fillExample}>
                <Beaker className="h-3.5 w-3.5" />
                Fill example
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => {
                  reset(DEFAULT_VALUES)
                  setAdjustedFields(new Set())
                }}
              >
                <RotateCcw className="h-3.5 w-3.5" />
                Reset
              </Button>
            </div>
            <Button
              type="submit"
              size="lg"
              variant={isInfeasible ? 'danger' : 'primary'}
              loading={createDesign.isPending}
              className="min-w-[140px]"
            >
              {isInfeasible ? 'Run anyway' : 'Design'}
            </Button>
          </div>
        </div>

        {/* Right: summary panel */}
        <div className="hidden lg:sticky lg:top-20 lg:block">
          <SummaryPanel values={formValues} />
        </div>

        {/* Mobile: summary stacks below */}
        <div className="lg:hidden">
          <SummaryPanel values={formValues} />
        </div>
      </div>

      {/* Confirmation Dialog for Infeasible Target */}
      <Dialog open={forceConfirmOpen} onOpenChange={setForceConfirmOpen}>
        <DialogContent className="max-w-md">
          <DialogTitle className="flex items-center gap-2 text-danger">
            <AlertTriangle className="h-5 w-5" />
            Target Marked Infeasible
          </DialogTitle>
          <DialogDescription className="text-sm">
            The target exceeds the physical bounds of beam lattices at this density (stiffness sum &gt; 1.05 &times; &rho; &times; E<sub>s</sub> or strength exceeding maximum).
            The backend physics search is very likely to return shortfalls.
          </DialogDescription>
          <div className="mt-4 flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setForceConfirmOpen(false)}
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="danger"
              size="sm"
              onClick={() => {
                setForceConfirmOpen(false)
                submitWithForce(true)
              }}
            >
              Force Run
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </form>
  )
}
