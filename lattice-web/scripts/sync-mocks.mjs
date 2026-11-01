#!/usr/bin/env node
/**
 * Copies real fixture files from ../mock/ into src/mocks/fixtures/real/.
 * The mock adapter prefers files from real/ over temporary fixtures.
 * Run: node scripts/sync-mocks.mjs
 */
import { existsSync, mkdirSync, readdirSync, copyFileSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const mockDir = join(__dirname, '..', '..', 'mock')
const targetDir = join(__dirname, '..', 'src', 'mocks', 'fixtures', 'real')

if (!existsSync(mockDir)) {
  console.log('No ../mock/ directory found. Nothing to sync.')
  process.exit(0)
}

mkdirSync(targetDir, { recursive: true })

const files = readdirSync(mockDir).filter((f) => f.endsWith('.json'))

if (files.length === 0) {
  console.log('../mock/ exists but contains no .json files.')
  process.exit(0)
}

let copied = 0
for (const file of files) {
  copyFileSync(join(mockDir, file), join(targetDir, file))
  copied++
  console.log(`  ✓ ${file}`)
}

console.log(`Synced ${copied} file(s) to src/mocks/fixtures/real/`)

