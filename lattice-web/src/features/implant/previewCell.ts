import candidates from '@/mocks/fixtures/real/implant/candidates_z3.json'
import type { Lattice } from '@/api/types'

/**
 * An illustrative lattice cell for the zone previews drawn before the searches have run. The real cell of each zone
 * is chosen on the next page; this one only shows what a lattice zone looks like.
 */
export const PREVIEW_LATTICE = candidates.candidates[0].lattice as unknown as Lattice
