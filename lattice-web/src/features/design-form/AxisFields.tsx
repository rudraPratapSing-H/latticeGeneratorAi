import type { UseFormRegister, FieldErrors } from 'react-hook-form'
import type { DesignFormValues } from '@/features/design-form/defaults'
import type { Axis } from '@/api/types'
import { NumberField } from '@/components/ui/number-field'
import { Switch } from '@/components/ui/switch'
import { SourceTag } from '@/components/ui/source-tag'
import { AXES, AXIS_LABELS } from '@/config/constants'
import { TRAINED_RANGES } from '@/config/limits'
import { cn } from '@/lib/cn'

const AXIS_COLOR: Record<Axis, string> = {
  x: 'text-axis-x',
  y: 'text-axis-y',
  z: 'text-axis-z',
}

interface AxisFieldsProps {
  prefix: 'stiffness' | 'strength'
  unit: string
  register: UseFormRegister<DesignFormValues>
  errors: FieldErrors<DesignFormValues>
  watch: (name: keyof DesignFormValues) => unknown
  setValue: (name: keyof DesignFormValues, value: unknown) => void
  adjustedFields?: Set<string>
}

export function AxisFields({
  prefix,
  unit,
  register,
  errors,
  watch,
  setValue,
  adjustedFields,
}: AxisFieldsProps) {
  const sameAll = watch(`${prefix}SameAll` as keyof DesignFormValues) as boolean
  const trainedRange =
    prefix === 'stiffness' ? TRAINED_RANGES.stiffness_gpa : TRAINED_RANGES.strength_mpa

  return (
    <div className="space-y-3">
      <Switch
        checked={sameAll}
        onChange={(v) => setValue(`${prefix}SameAll` as keyof DesignFormValues, v)}
        label="Same in all directions"
      />

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {AXES.map((axis) => {
          const fieldName = `${prefix}${axis.toUpperCase()}` as keyof DesignFormValues
          const dontCareName = `${prefix}DontCare${axis.toUpperCase()}` as keyof DesignFormValues
          const isDontCare = watch(dontCareName) as boolean
          const isReadOnly = sameAll && axis !== 'x'
          const value = watch(fieldName) as string
          const isAdjusted = adjustedFields?.has(fieldName) ?? false

          // Soft warning for out-of-range
          const numVal = parseFloat(value)
          const outOfRange =
            !isDontCare &&
            isFinite(numVal) &&
            (numVal < trainedRange.min || numVal > trainedRange.max)

          const error = errors[fieldName]

          return (
            <div key={axis} className="space-y-1.5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <span className={cn('text-sm font-semibold', AXIS_COLOR[axis])}>
                    {AXIS_LABELS[axis]}
                  </span>
                  {!isDontCare && isFinite(numVal) && numVal > 0 && (
                    <SourceTag source={isAdjusted ? 'adjusted' : 'requested'} />
                  )}
                </div>
                {!isReadOnly && (
                  <label className="text-muted flex cursor-pointer items-center gap-1.5 text-xs">
                    <input
                      type="checkbox"
                      className="border-line accent-accent cursor-pointer rounded"
                      checked={isDontCare}
                      onChange={(e) => setValue(dontCareName, e.target.checked)}
                    />
                    Don&apos;t care
                  </label>
                )}
              </div>
              <NumberField
                {...register(fieldName)}
                unit={unit}
                disabled={isDontCare || isReadOnly}
                placeholder={
                  isDontCare
                    ? '—'
                    : isReadOnly
                      ? (watch(`${prefix}X` as keyof DesignFormValues) as string)
                      : '0'
                }
                value={
                  isReadOnly ? (watch(`${prefix}X` as keyof DesignFormValues) as string) : undefined
                }
                error={error?.message as string | undefined}
                warning={outOfRange ? 'Outside trained range; results may be weaker' : undefined}
              />
            </div>
          )
        })}
      </div>
    </div>
  )
}
