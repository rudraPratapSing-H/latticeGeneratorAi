/** Implant workflow hooks: the /api/implants endpoints. Types come from the backend's OpenAPI document. */

import { useQuery, useQueries, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '@/api/client'
import { queryKeys } from '@/api/queryKeys'
import { getMeshBlob, storeMeshBlob } from '@/lib/meshStore'
import type { Lattice } from '@/api/types'
import type {
  CreateImplantResponse,
  ConfirmImplantRequest,
  Zone,
  ZoneTable,
  ZoneEditRequest,
  ZoneCandidates,
  ImplantResult,
} from '@/api/implantTypes'

export function useCreateImplant() {
  return useMutation({
    mutationFn: async (params: {
      file?: File | Blob
      material: string
      description: string
    }): Promise<CreateImplantResponse> => {
      const formData = new FormData()
      if (params.file) {
        formData.append('stl_file', params.file)
      }
      formData.append('material', params.material)
      formData.append('description', params.description)

      const { data } = await apiClient.post<CreateImplantResponse>('/api/implants', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })

      // Store mesh blob in IndexedDB for 3D visualization across refreshes
      if (params.file) {
        await storeMeshBlob(data.implant_id, params.file)
      }

      return data
    },
  })
}

export function useConfirmImplant(implantId: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (confirmData: ConfirmImplantRequest): Promise<ZoneTable> => {
      const { data } = await apiClient.post<ZoneTable>(`/api/implants/${implantId}/confirm`, confirmData)
      return data
    },
    onSuccess: (table) => {
      queryClient.setQueryData(queryKeys.implantZones(implantId), table)
    },
  })
}

/** Edits to send for a changed zone list: a kind only when the user changed it, typed targets only when they are typed ones. */
export function zonesToEdits(next: Zone[], previous: Zone[] | undefined): ZoneEditRequest {
  const before = new Map((previous ?? []).map((z) => [z.id, z]))
  return {
    zones: next.map((z) => {
      const old = before.get(z.id)
      const typedK = z.requirement.stiffness_gpa.z
      const typedS = z.requirement.strength_mpa.z
      return {
        id: z.id,
        range_mm: z.range_mm,
        kind: z.kind !== 'undecided' && old && old.kind !== z.kind ? z.kind : null,
        stiffness_z: typedK.source === 'requested' ? typedK.value : null,
        strength_z: typedS.source === 'requested' ? typedS.value : null,
      }
    }),
  }
}

/** The zone table of a confirmed implant (zones, cell size, load summary, warnings) and a way to edit it. */
export function useImplantZones(implantId: string) {
  const queryClient = useQueryClient()

  const query = useQuery<ZoneTable>({
    queryKey: queryKeys.implantZones(implantId),
    queryFn: async () => {
      const { data } = await apiClient.get<ZoneTable>(`/api/implants/${implantId}/zones`)
      return data
    },
    enabled: !!implantId,
  })

  const updateMutation = useMutation({
    mutationFn: async (edits: ZoneEditRequest): Promise<ZoneTable> => {
      const { data } = await apiClient.put<ZoneTable>(`/api/implants/${implantId}/zones`, edits)
      return data
    },
    onSuccess: (table) => {
      queryClient.setQueryData(queryKeys.implantZones(implantId), table)
    },
  })

  return {
    ...query,
    data: query.data?.zones,
    table: query.data,
    updateZones: (zones: Zone[]) => updateMutation.mutate(zonesToEdits(zones, query.data?.zones)),
    isUpdating: updateMutation.isPending,
    updateError: updateMutation.error,
  }
}

export function useSearchImplantZones(implantId: string) {
  return useMutation({
    mutationFn: async (): Promise<Record<string, string>> => {
      const { data } = await apiClient.post<Record<string, string>>(
        `/api/implants/${implantId}/search`,
      )
      return data
    },
  })
}

/** Candidates of one zone; polls while the zone's search is queued or running. */
export function useZoneCandidates(implantId: string, zoneId: string) {
  return useQuery<ZoneCandidates>({
    queryKey: queryKeys.zoneCandidates(implantId, zoneId),
    queryFn: async () => {
      const { data } = await apiClient.get<ZoneCandidates>(
        `/api/implants/${implantId}/zones/${zoneId}/candidates`,
      )
      return data
    },
    enabled: !!implantId && !!zoneId,
    refetchInterval: (q) => {
      const st = q.state.data?.job?.status
      return st === 'queued' || st === 'running' ? 1500 : false
    },
  })
}

/** The lattice cell chosen for each lattice zone of a finished implant, for the 3D model. */
export function useZoneLattices(
  implantId: string,
  chosen: { zoneId: string; candidateId: string }[],
): { lattices: Record<string, Lattice>; pending: boolean } {
  return useQueries({
    queries: chosen.map((c) => ({
      queryKey: queryKeys.zoneCandidates(implantId, c.zoneId),
      queryFn: async () => {
        const { data } = await apiClient.get<ZoneCandidates>(`/api/implants/${implantId}/zones/${c.zoneId}/candidates`)
        return data
      },
    })),
    combine: (results) => {
      const lattices: Record<string, Lattice> = {}
      results.forEach((r, i) => {
        const found = r.data?.candidates.find((cand) => cand.id === chosen[i].candidateId)
        if (found) lattices[chosen[i].zoneId] = found.lattice
      })
      return { lattices, pending: results.some((r) => r.isPending) }
    },
  })
}

export function useAssembleImplant(implantId: string) {
  return useMutation({
    mutationFn: async (choices: Record<string, string>): Promise<{ job_id: string; status: string }> => {
      const { data } = await apiClient.post<{ job_id: string; status: string }>(
        `/api/implants/${implantId}/assemble`,
        { choices },
      )
      return data
    },
  })
}

export interface AssembleJob {
  job_id: string
  status: 'queued' | 'running' | 'done' | 'failed' | 'cancelled'
  stage: string | null
  progress: number
  message: string | null
  queue_position: number | null
}

/** Progress of the assemble job (tile, assemble, check, export). */
export function useAssembleJob(jobId: string | undefined) {
  return useQuery<AssembleJob>({
    queryKey: ['implant-assemble-job', jobId],
    queryFn: async () => {
      const { data } = await apiClient.get<AssembleJob>(`/api/jobs/${jobId}`)
      return data
    },
    enabled: !!jobId,
    refetchInterval: (q) => {
      const st = q.state.data?.status
      return st === 'done' || st === 'failed' || st === 'cancelled' ? false : 1000
    },
  })
}

export function useImplantResult(implantId: string) {
  return useQuery<ImplantResult>({
    queryKey: queryKeys.implantResult(implantId),
    queryFn: async () => {
      const { data } = await apiClient.get<ImplantResult>(`/api/implants/${implantId}/result`)
      return data
    },
    enabled: !!implantId,
  })
}

export function useStoredMesh(implantId: string) {
  return useQuery<Blob | null>({
    queryKey: ['stored-mesh', implantId],
    queryFn: () => getMeshBlob(implantId),
    enabled: !!implantId,
    staleTime: Infinity,
  })
}

