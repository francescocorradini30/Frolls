/** An uploaded image: the server stores pictures as WebP with a thumbnail
 *  (none for animated GIFs and SVGs); width/height after any scaling down. */
export interface Uploaded {
  url: string
  thumb: string | null
  width: number
  height: number
}

export async function uploadFile(file: File): Promise<Uploaded> {
  const body = new FormData()
  body.append('file', file)
  const res = await fetch('/api/assets', { method: 'POST', body })
  if (!res.ok) {
    const detail = await res.json().catch(() => null)
    throw new Error(detail?.detail ?? `Upload failed (${res.status})`)
  }
  return (await res.json()) as Uploaded
}

export async function uploadImage(file: File): Promise<string> {
  return (await uploadFile(file)).url
}

/** Natural size of an image URL, to size new tokens and maps. */
export function imageSize(url: string): Promise<{ w: number; h: number }> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve({ w: img.naturalWidth, h: img.naturalHeight })
    img.onerror = reject
    img.src = url
  })
}

export function pickFile(accept = 'image/*'): Promise<File | null> {
  return new Promise((resolve) => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = accept
    input.onchange = () => resolve(input.files?.[0] ?? null)
    input.click()
  })
}

export function pickFiles(accept = 'image/*'): Promise<File[]> {
  return new Promise((resolve) => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = accept
    input.multiple = true
    input.onchange = () => resolve([...(input.files ?? [])])
    input.click()
  })
}

/** File name without its extension, as a default name. */
export function baseName(file: File): string {
  return file.name.replace(/\.[^.]+$/, '') || 'Image'
}
