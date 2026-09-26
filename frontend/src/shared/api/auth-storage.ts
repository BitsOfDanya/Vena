const API_KEY_STORAGE = "vena.apiKey.v1"

export function getStoredApiKey(): string | null {
  if (typeof window === "undefined") return null
  try {
    return localStorage.getItem(API_KEY_STORAGE)
  } catch {
    return null
  }
}

export function setStoredApiKey(value: string | null): void {
  if (typeof window === "undefined") return
  try {
    if (!value) localStorage.removeItem(API_KEY_STORAGE)
    else localStorage.setItem(API_KEY_STORAGE, value)
  } catch {
    // ignore quota / private mode
  }
}
