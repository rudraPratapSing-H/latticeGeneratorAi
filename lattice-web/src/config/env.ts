export const API_BASE = (import.meta.env.VITE_API_URL ?? '').replace(/\/$/, '')

export const USE_MOCK = import.meta.env.VITE_USE_MOCK === 'true'

export const ENABLE_IMPLANT = import.meta.env.VITE_ENABLE_IMPLANT !== 'false'
