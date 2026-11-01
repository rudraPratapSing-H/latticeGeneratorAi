export const queryKeys = {
  health: ['health'] as const,
  materials: ['materials'] as const,
  limits: (material: string) => ['limits', material] as const,
  reach: (hash: string) => ['reach', hash] as const,
  job: (id: string) => ['job', id] as const,
  design: (id: string) => ['design', id] as const,
  implant: (id: string) => ['implant', id] as const,
  implantZones: (id: string) => ['implant', id, 'zones'] as const,
  zoneCandidates: (implantId: string, zoneId: string) =>
    ['implant', implantId, 'zones', zoneId, 'candidates'] as const,
  implantResult: (id: string) => ['implant', id, 'result'] as const,
}
