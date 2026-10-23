// Performance targets of the MVP, measured in a real browser:
//   - 60 fps with an 8192×8192 map and 100 tokens while the camera moves;
//   - a token move visible to another player in under 150 ms;
//   - the game page loaded (map and tokens drawn) in under 3 s.
// Isolated servers and database: see harness.mjs. Usage: npm run perf
// Headless Chrome may render without the GPU (SwiftShader): the renderer is printed, and
// the fps target is only meaningful with a hardware renderer (HEADED=1 npm run perf).
import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { BASE, OUT, check, launchBrowser, report, results, startServers, tab as openTab } from './harness.mjs'

const stopServers = await startServers()
const browser = await launchBrowser(['--ignore-gpu-blocklist', '--enable-gpu-rasterization', '--use-angle=d3d11'])
const tab = (name, gm) => openTab(browser, name, gm)
const PYTHON = fileURLToPath(new URL('../backend/.venv/Scripts/python.exe', import.meta.url))

// An 8192² map picture (JPEG, so the upload stays under the size limit).
const mapFile = `${OUT}/perf-map.jpg`
execFileSync(PYTHON, [
  '-c',
  `from PIL import Image, ImageDraw
im = Image.new('RGB', (8192, 8192), (40, 44, 60))
d = ImageDraw.Draw(im)
for i in range(0, 8192, 64):
    d.line([(i, 0), (8192 - i, 8192)], fill=(60 + i % 120, 80, 120), width=9)
    d.ellipse([i, (i * 7) % 8000, i + 180, (i * 7) % 8000 + 180], fill=(120, 90 + i % 100, 70))
im.save(r'${mapFile}', quality=80)`,
])

let gm, pl
try {
  gm = await tab('Master', true)
  pl = await tab('Aria', false)
  const renderer = await gm.evaluate(() => {
    const gl = document.createElement('canvas').getContext('webgl2')
    const info = gl?.getExtension('WEBGL_debug_renderer_info')
    return info ? gl.getParameter(info.UNMASKED_RENDERER_WEBGL) : 'unknown'
  })
  console.log(`Renderer: ${renderer}`)

  const upload = await gm.evaluate(async (bytes) => {
    const form = new FormData()
    form.append('file', new Blob([new Uint8Array(bytes)], { type: 'image/jpeg' }), 'map.jpg')
    return (await fetch('/api/assets', { method: 'POST', body: form })).json()
  }, [...readFileSync(mapFile)])
  const cells = Math.ceil(8192 / 70)
  await gm.evaluate(
    ({ url, cells }) => {
      const s = window.__store
      s.send({ type: 'page.update', id: s.page.id, patch: { width: cells, height: cells } })
      const objs = [
        { id: 'perf-map', page_id: s.page.id, kind: 'image', layer: 'map', x: 4096, y: 4096, width: 8192, height: 8192, rotation: 0, props: { image: url } },
      ]
      for (let i = 0; i < 100; i++) {
        const x = 35 + 70 * ((i * 7) % cells)
        const y = 35 + 70 * ((i * 13) % cells)
        objs.push({
          id: `perf-t${i}`,
          page_id: s.page.id,
          kind: 'token',
          layer: 'objects',
          x,
          y,
          width: 70,
          height: 70,
          rotation: 0,
          props: { name: `Token ${i}`, color: '#8a7cff', ...(i % 2 ? { image: url } : {}), bar1: { value: 10, max: 10 } },
        })
      }
      s.createObjects(objs)
    },
    { url: upload.url, cells },
  )
  await gm.waitForFunction(() => window.__engine.views.size >= 101, null, { timeout: 15000 })
  await pl.waitForFunction(() => window.__engine.views.size >= 101, null, { timeout: 15000 })
  await gm.waitForTimeout(2500)

  // FPS: frames drawn in 4 s while the camera pans and zooms every frame.
  const fps = await gm.evaluate(
    () =>
      new Promise((resolve) => {
        const e = window.__engine
        e.fitPage()
        let frames = 0
        const start = performance.now()
        const step = (now) => {
          frames++
          const t = (now - start) / 1000
          e.zoomBy(t % 2 < 1 ? 1.004 : 1 / 1.004)
          e.centerOn(4096 + Math.sin(t) * 2500, 4096 + Math.cos(t) * 2500)
          if (now - start < 4000) requestAnimationFrame(step)
          else resolve(frames / ((now - start) / 1000))
        }
        requestAnimationFrame(step)
      }),
  )
  check(`60 fps with an 8192² map and 100 tokens (measured ${fps.toFixed(1)} fps, ${renderer})`, fps >= 55)
  await gm.screenshot({ path: `${OUT}/perf-map.png` })

  // Movement latency: GM moves a token, the player's tab sees the update.
  const latencies = []
  for (let i = 0; i < 10; i++) {
    await pl.evaluate(() => {
      window.__moved = new Promise((resolve) => {
        const off = window.__store.on('upsert', (objs) => {
          if (objs.some((o) => o.id === 'perf-t0')) {
            off()
            resolve(Date.now())
          }
        })
      })
    })
    const sent = await gm.evaluate((i) => {
      const s = window.__store
      const t = s.objects.get('perf-t0')
      const at = Date.now()
      s.updateObjects([{ id: t.id, x: t.x + (i % 2 ? -70 : 70) }])
      return at
    }, i)
    const seen = await pl.evaluate(() => window.__moved)
    latencies.push(seen - sent)
  }
  latencies.sort((a, b) => a - b)
  const median = latencies[Math.floor(latencies.length / 2)]
  check(`a move is visible to the others in < 150 ms (median ${median} ms, max ${latencies.at(-1)} ms)`, median < 150)

  // Page load: a fresh tab until the map and every token are drawn.
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 850 } })
  const page = await ctx.newPage()
  const t0 = Date.now()
  await page.goto(BASE)
  await page.getByPlaceholder('e.g. Aria the Ranger').fill('Late')
  await page.getByRole('button', { name: 'Join' }).click()
  await page.waitForFunction(() => window.__engine?.views.size >= 101, null, { timeout: 15000 })
  const load = Date.now() - t0
  check(`the game loads in < 3 s (${load} ms with 101 objects and an 8192² map)`, load < 3000)
} catch (e) {
  results.push(`FAIL aborted: ${e.message.split('\n')[0]}`)
} finally {
  await browser.close()
  stopServers()
  report()
}
