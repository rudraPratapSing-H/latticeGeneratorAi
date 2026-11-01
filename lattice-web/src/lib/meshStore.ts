/**
 * Tiny IndexedDB wrapper to store uploaded implant STL files locally.
 * Zero external dependencies.
 * Ensures the 3D preview and mesh analysis survive page refresh.
 */

const DB_NAME = 'lattice-designer-mesh-db'
const DB_VERSION = 1
const STORE_NAME = 'implant-meshes'

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof window === 'undefined' || !window.indexedDB) {
      reject(new Error('IndexedDB not supported in this environment'))
      return
    }

    const request = indexedDB.open(DB_NAME, DB_VERSION)

    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME)
      }
    }

    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

export async function storeMeshBlob(implantId: string, blob: Blob): Promise<void> {
  try {
    const db = await openDb()
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, 'readwrite')
      const store = tx.objectStore(STORE_NAME)
      const request = store.put(blob, implantId)

      request.onsuccess = () => resolve()
      request.onerror = () => reject(request.error)
    })
  } catch (err) {
    console.warn('Could not store mesh in IndexedDB:', err)
  }
}

export async function getMeshBlob(implantId: string): Promise<Blob | null> {
  try {
    const db = await openDb()
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, 'readonly')
      const store = tx.objectStore(STORE_NAME)
      const request = store.get(implantId)

      request.onsuccess = () => resolve(request.result as Blob | null)
      request.onerror = () => reject(request.error)
    })
  } catch (err) {
    console.warn('Could not retrieve mesh from IndexedDB:', err)
    return null
  }
}

export async function removeMeshBlob(implantId: string): Promise<void> {
  try {
    const db = await openDb()
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, 'readwrite')
      const store = tx.objectStore(STORE_NAME)
      const request = store.delete(implantId)

      request.onsuccess = () => resolve()
      request.onerror = () => reject(request.error)
    })
  } catch (err) {
    console.warn('Could not remove mesh from IndexedDB:', err)
  }
}

