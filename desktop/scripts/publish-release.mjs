#!/usr/bin/env node
/**
 * Publish electron-builder artifacts to the OmniAide backend.
 *
 * Usage:
 *   OMNIAIDE_SERVER=https://mqgeek.com/ominaide \
 *   OMNIAIDE_TOKEN=<admin access token> \
 *   npm run publish:release
 */
import { readFile, readdir, stat } from 'node:fs/promises'
import { join, resolve } from 'node:path'

const server = (process.env.OMNIAIDE_SERVER || 'https://mqgeek.com/ominaide').replace(/\/+$/, '')
const token = process.env.OMNIAIDE_TOKEN || ''
const releaseDir = resolve(process.cwd(), process.env.RELEASE_DIR || 'release')

if (!token) {
  console.error('OMNIAIDE_TOKEN is required (admin access token)')
  process.exit(1)
}

const allowed = /\.(dmg|zip|exe|blockmap|yml|yaml)$/i

const entries = await readdir(releaseDir, { withFileTypes: true })
const files = []
for (const entry of entries) {
  if (!entry.isFile() || !allowed.test(entry.name)) continue
  const path = join(releaseDir, entry.name)
  const info = await stat(path)
  files.push({ name: entry.name, path, size: info.size })
}

if (!files.length) {
  console.error(`No release artifacts found in ${releaseDir}`)
  process.exit(1)
}

for (const file of files) {
  const body = new FormData()
  const data = await readFile(file.path)
  body.append('file', new Blob([data]), file.name)
  const res = await fetch(`${server}/api/desktop/releases/upload`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body,
  })
  if (!res.ok) {
    console.error(`[publish] ${file.name} failed: ${res.status} ${await res.text()}`)
    process.exit(1)
  }
  console.log(`[publish] ${file.name} (${(file.size / 1024 / 1024).toFixed(1)} MB)`)
}

console.log(`Published ${files.length} file(s) to ${server}/api/desktop/releases`)
