import { randomUUID } from 'node:crypto'
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'

export function loadMachineIdentity(appData: string, legacyUserData: string): string {
  const directory = join(appData, 'lms-print-client')
  const identityPath = join(directory, 'machine-id.txt')
  const legacyPath = join(legacyUserData, 'machine-id.txt')
  mkdirSync(directory, { recursive: true })
  const source = existsSync(identityPath) ? identityPath : existsSync(legacyPath) ? legacyPath : null
  const identity = source ? readFileSync(source, 'utf8').trim() : randomUUID()
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(identity)) {
    throw new Error('本机标识文件损坏，请保留该文件并联系管理员恢复工位绑定')
  }
  if (!existsSync(identityPath)) writeFileSync(identityPath, identity, { encoding: 'utf8', flag: 'wx' })
  return identity
}
