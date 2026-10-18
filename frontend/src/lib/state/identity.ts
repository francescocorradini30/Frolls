import type { Player } from '../net/protocol'
import { uid } from '../util/ids'

export type Identity = Omit<Player, 'online'>

// sessionStorage is per browser tab: each tab is a different player.
const KEY = 'frolls.identity'

export function loadIdentity(): Identity | null {
  try {
    const raw = sessionStorage.getItem(KEY)
    return raw ? (JSON.parse(raw) as Identity) : null
  } catch {
    return null
  }
}

export function saveIdentity(identity: Identity): void {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(identity))
  } catch {
    // Private mode etc.: identity just won't survive a reload.
  }
}

export function clearIdentity(): void {
  try {
    sessionStorage.removeItem(KEY)
  } catch {
    // ignore
  }
}

export function newIdentity(name: string, color: string, isGm: boolean): Identity {
  return { id: uid(), name, color, is_gm: isGm }
}
