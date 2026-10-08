const storageKey = 'footlytics.access-token'
const listeners = new Set<() => void>()

function readInitialToken(): string | null {
  try {
    return window.sessionStorage.getItem(storageKey)
  } catch {
    console.warn('Session storage unavailable. Sign-in will last until page reload.')
    return null
  }
}

let accessToken = readInitialToken()

export function getAccessToken(): string | null {
  return accessToken
}

export function setAccessToken(token: string | null): void {
  accessToken = token
  try {
    if (token) window.sessionStorage.setItem(storageKey, token)
    else window.sessionStorage.removeItem(storageKey)
  } catch {
    console.warn('Session storage unavailable. Sign-in will last until page reload.')
  }
  listeners.forEach((notify) => notify())
}

export function subscribeToToken(notify: () => void): () => void {
  listeners.add(notify)
  return () => { listeners.delete(notify) }
}
