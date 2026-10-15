import { describe, expect, it } from 'vitest'
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { loadMachineIdentity } from '../../src/main/machineIdentity'

describe('machine identity persistence', () => {
  it('preserves an existing binding when userData changes across launch modes', () => {
    const root = mkdtempSync(join(tmpdir(), 'lms-identity-'))
    try {
      const legacy = join(root, 'legacy')
      mkdirSync(legacy)
      const original = '68d1b7f2-8826-44ae-9805-f7992bf973d7'
      writeFileSync(join(legacy, 'machine-id.txt'), original)
      expect(loadMachineIdentity(root, legacy)).toBe(original)
      expect(loadMachineIdentity(root, join(root, 'another-launch'))).toBe(original)
    } finally { rmSync(root, { recursive: true, force: true }) }
  })
  it('never silently replaces a corrupted existing identity', () => {
    const root = mkdtempSync(join(tmpdir(), 'lms-identity-'))
    try {
      const identity = loadMachineIdentity(root, root)
      expect(loadMachineIdentity(root, root)).toBe(identity)
      writeFileSync(join(root, 'lms-print-client', 'machine-id.txt'), 'broken')
      expect(() => loadMachineIdentity(root, root)).toThrow('标识文件损坏')
    } finally { rmSync(root, { recursive: true, force: true }) }
  })
})
