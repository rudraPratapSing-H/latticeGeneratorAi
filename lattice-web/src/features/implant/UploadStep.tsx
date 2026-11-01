import { useState, useRef } from 'react'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Select, SelectItem } from '@/components/ui/select'
import { useMaterials } from '@/hooks/useMaterials'
import { generateSampleStemStl } from '@/mocks/stemProfile'
import { USE_MOCK } from '@/config/env'
import { UploadCloud, FileCode, Beaker } from 'lucide-react'

interface UploadStepProps {
  onUploaded: (file: File | Blob, material: string, description: string) => void
  isLoading: boolean
}

export function UploadStep({ onUploaded, isLoading }: UploadStepProps) {
  const { data: materials } = useMaterials()
  const [file, setFile] = useState<File | Blob | null>(null)
  const [fileName, setFileName] = useState<string>('')
  const [material, setMaterial] = useState<string>('ti64')
  const [description, setDescription] = useState<string>(
    'Right femoral hip stem for 75 kg active patient. Keep the proximal neck region solid for fatigue strength.',
  )
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const selected = e.target.files[0]
      setFile(selected)
      setFileName(selected.name)
    }
  }

  const handleUseSampleStem = () => {
    const ascii = generateSampleStemStl()
    const blob = new Blob([ascii], { type: 'model/stl' })
    setFile(blob)
    setFileName('sample_femoral_stem.stl')
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!file) return
    onUploaded(file, material, description)
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold text-text">
              1. Upload Implant Geometry &amp; Describe Case
            </h2>
            {USE_MOCK && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleUseSampleStem}
                className="text-xs"
              >
                <Beaker className="mr-1.5 h-3.5 w-3.5" />
                Use sample stem
              </Button>
            )}
          </div>
        </CardHeader>

        <CardContent className="space-y-5">
          {/* File drop zone */}
          <div
            onClick={() => fileInputRef.current?.click()}
            className="border-2 border-dashed border-line hover:border-accent cursor-pointer rounded-xl p-8 text-center transition-colors bg-surface-2/40 hover:bg-surface-2/70"
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".stl"
              onChange={handleFileChange}
              className="hidden"
            />
            <div className="flex flex-col items-center gap-2">
              <UploadCloud className="h-8 w-8 text-accent" />
              <p className="text-sm font-medium text-text">
                {fileName ? fileName : 'Click or drag your implant STL file here'}
              </p>
              <p className="text-xs text-muted">
                Accepts binary or ASCII .stl files (maximum 50 MB)
              </p>
            </div>
          </div>

          {/* Material selection */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-text">Implant Material</label>
            <Select value={material} onChange={setMaterial}>
              {materials?.map((m) => (
                <SelectItem key={m.id} value={m.id}>
                  {m.name} (E {m.E_gpa} GPa &middot; &sigma;y {m.yield_mpa} MPa)
                </SelectItem>
              ))}
            </Select>
          </div>

          {/* Clinical description */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label className="text-xs font-medium text-text">Description &amp; constraints</label>
              <span className="text-[11px] text-muted">Body weight, activity and rules are read from this text</span>
            </div>
            <textarea
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="e.g. Hip stem for a 75 kg moderately active patient, keep the neck solid"
              className="w-full rounded-lg border border-line bg-surface px-3 py-2 text-xs text-text focus:border-accent focus:outline-none"
            />
          </div>

          <div className="flex justify-end pt-2">
            <Button type="submit" size="lg" disabled={!file || isLoading} loading={isLoading}>
              <FileCode className="mr-1.5 h-4 w-4" />
              Upload &amp; Analyze Mesh
            </Button>
          </div>
        </CardContent>
      </Card>
    </form>
  )
}

