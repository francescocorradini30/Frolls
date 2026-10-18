// End-to-end check of the game mechanics with two real browser tabs (GM + player).
// Starts its own backend (port 8001, database frolls_e2e wiped on every run) and frontend
// (port 5174), so it never touches the dev game. Needs a local Chrome or Edge.
// Usage: npm run e2e            (headless)
//        HEADED=1 npm run e2e   (watch it)
import { execFileSync, spawn } from 'node:child_process'
import { existsSync, mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright-core'

const API_PORT = 8001
const WEB_PORT = 5174
const BASE = `http://localhost:${WEB_PORT}/`
const OUT = fileURLToPath(new URL('./out', import.meta.url))
const BACKEND = fileURLToPath(new URL('../backend', import.meta.url))
const FRONTEND = fileURLToPath(new URL('../frontend', import.meta.url))
const PYTHON = `${BACKEND}/.venv/Scripts/python.exe`
mkdirSync(OUT, { recursive: true })

// Something else on our ports (e.g. a dev Vite that fell back to 5174) would silently
// serve the wrong app.
for (const port of [API_PORT, WEB_PORT]) {
  const busy = await fetch(`http://localhost:${port}/`).then(
    () => true,
    () => false,
  )
  if (busy) throw new Error(`port ${port} already in use: stop the process using it`)
}

const apiEnv = {
  ...process.env,
  FROLLS_DATABASE_URL: 'postgresql+asyncpg://frolls:frolls@localhost:5432/frolls_e2e',
}
// Empty database: drop everything, then recreate the schema from the migrations.
for (const target of ['base', 'head']) {
  execFileSync(PYTHON, ['-m', 'alembic', target === 'base' ? 'downgrade' : 'upgrade', target], {
    cwd: BACKEND,
    env: apiEnv,
    stdio: 'ignore',
  })
}
const servers = [
  spawn(PYTHON, ['-m', 'uvicorn', 'app.main:app', '--port', String(API_PORT)], { cwd: BACKEND, env: apiEnv }),
  spawn(process.execPath, ['node_modules/vite/bin/vite.js', '--port', String(WEB_PORT), '--strictPort'], {
    cwd: FRONTEND,
    env: {
      ...process.env,
      FROLLS_API_URL: `http://localhost:${API_PORT}`,
      FROLLS_VITE_CACHE_DIR: 'node_modules/.vite-e2e',
    },
  }),
]
const stopServers = () => servers.forEach((s) => s.kill())
process.on('exit', stopServers)

async function waitFor(url) {
  for (let i = 0; i < 100; i++) {
    try {
      if ((await fetch(url)).ok) return
    } catch {}
    await new Promise((r) => setTimeout(r, 200))
  }
  throw new Error(`${url} is not responding`)
}
await waitFor(`http://localhost:${API_PORT}/health`)
await waitFor(BASE)

const candidates = [
  process.env.CHROME_PATH,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  '/usr/bin/google-chrome',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
].filter(Boolean)
const executablePath = candidates.find((p) => existsSync(p))
if (!executablePath) throw new Error('Chrome/Edge not found: set CHROME_PATH')
const browser = await chromium.launch({ executablePath, headless: !process.env.HEADED })
const errors = []
const results = []
const check = (name, ok, extra = '') => results.push(`${ok ? 'OK  ' : 'FAIL'} ${name} ${ok ? '' : extra}`)

async function tab(name, gm) {
  const ctx = await browser.newContext({ viewport: { width: 1400, height: 850 } })
  const page = await ctx.newPage()
  page.on('pageerror', (e) => errors.push(`${name}: ${e.message}`))
  page.on('console', (m) => m.type() === 'error' && errors.push(`${name} console: ${m.text()}`))
  await page.goto(BASE)
  await page.getByPlaceholder('e.g. Aria the Ranger').fill(name)
  if (gm) await page.getByRole('button', { name: 'Game Master' }).click()
  await page.getByRole('button', { name: 'Join' }).click()
  await page.waitForSelector('canvas')
  await page.waitForFunction(() => window.__engine && window.__store?.page)
  await page.waitForTimeout(500)
  return page
}
const state = (page) =>
  page.evaluate(() => {
    const s = window.__store
    return JSON.parse(
      JSON.stringify({
        objects: [...s.objects.values()],
        selection: s.selection,
        page: s.page,
        game: s.game,
        players: s.players,
        tool: s.tool,
      }),
    )
  })
const toClient = (page, x, y) => page.evaluate(([x, y]) => window.__engine.worldToClient(x, y), [x, y])
const drag = async (page, a, b, steps = 8) => {
  await page.mouse.move(a.x, a.y)
  await page.mouse.down()
  await page.mouse.move(b.x, b.y, { steps })
  await page.mouse.up()
}

let gm, pl
try {
gm = await tab('Master', true)

pl = await tab('Aria', false)

// 1. GM creates token
await gm.getByTitle('New token').click()
await gm.waitForTimeout(400)
let g = await state(gm)
const tok = g.objects.find((o) => o.kind === 'token')
check('GM creates token', !!tok)
let p = await state(pl)
check('player sees token', p.objects.some((o) => o.id === tok.id))

// Labels of the rulers other players are showing on this tab.
const remoteRulers = (page) =>
  page.evaluate(() => [...window.__engine.remoteRulers.values()].map((r) => r.label.text))
const waitRemoteRulers = (page, count) =>
  page
    .waitForFunction((n) => window.__engine.remoteRulers.size === n, count, { timeout: 3000 })
    .then(() => true, () => false)

// 2. GM drags token ~3 cells right, snapped
const from = await toClient(gm, tok.x, tok.y)
const zoom = await gm.evaluate(() => window.__engine.zoom)
await gm.mouse.move(from.x, from.y)
await gm.mouse.down()
// Mid-drag the token must already sit on a cell centre, not glide freely.
await gm.mouse.move(from.x + 70 * 1.4 * zoom, from.y + 70 * 0.3 * zoom, { steps: 6 })
const mid = await gm.evaluate((id) => {
  const r = window.__engine.views.get(id).root
  return { x: r.x, y: r.y }
}, tok.id)
check('token stays on cell centres while dragged', mid.x % 70 === 35 && mid.y % 70 === 35, `${mid.x},${mid.y}`)
await gm.mouse.move(from.x + 70 * 3 * zoom + 5, from.y, { steps: 6 })
const dragLabel = await gm.evaluate(() => window.__engine.overlayLabel.text)
const seenDrag = (await waitRemoteRulers(pl, 1)) && (await pl.waitForFunction(
  (t) => [...window.__engine.remoteRulers.values()][0]?.label.text === t, dragLabel, { timeout: 3000 },
).then(() => true, () => false))
check('player sees the GM drag distance live', seenDrag, `${dragLabel} vs ${await remoteRulers(pl)}`)
await gm.mouse.up()
check('drag distance disappears for the player on drop', await waitRemoteRulers(pl, 0))
await gm.waitForTimeout(500)
g = await state(gm)
p = await state(pl)
const moved = g.objects.find((o) => o.id === tok.id)
const pMoved = p.objects.find((o) => o.id === tok.id)
check('drag moves token with snap', moved.x === tok.x + 210, `x ${tok.x} -> ${moved.x}`)
check('player receives the position', pMoved.x === moved.x && pMoved.y === moved.y)

// 3. Player cannot drag uncontrolled token
const pc = await toClient(pl, moved.x, moved.y)
await drag(pl, pc, { x: pc.x + 100, y: pc.y })
await pl.waitForTimeout(400)
p = await state(pl)
check('player can NOT move tokens of others', p.objects.find((o) => o.id === tok.id).x === moved.x)

// 4. GM gives control to Aria via editor (double click)
const ariaId = await pl.evaluate(() => window.__store.me.id)
const gc = await toClient(gm, moved.x, moved.y)
await gm.mouse.dblclick(gc.x, gc.y)
const dialog = gm.getByRole('dialog', { name: 'Token settings' })
await dialog.waitFor()
await dialog.locator('label.field input').first().fill('Aria the Ranger')
await dialog.locator(`[data-player-id="${ariaId}"]`).click()
await dialog.getByRole('button', { name: 'Bars' }).click()
await dialog.getByLabel('HP value', { exact: true }).fill('22')
await dialog.getByLabel('HP max', { exact: true }).fill('30')
await dialog.getByRole('button', { name: 'Statuses' }).click()
await dialog.getByTitle('Poisoned').click()
await dialog.getByRole('button', { name: 'Save' }).click()
await gm.waitForTimeout(500)
p = await state(pl)
let t2 = p.objects.find((o) => o.id === tok.id)
check(
  'editor: name, control, bars, statuses',
  t2.props.name === 'Aria the Ranger' &&
    t2.props.controlled_by?.includes(ariaId) &&
    t2.props.bar1?.value === 22 &&
    t2.props.statuses?.includes('poisoned'),
  JSON.stringify(t2.props),
)

// 4b. Resize keeps the opposite corner fixed and lands on grid lines
await gm.evaluate((id) => window.__store.setSelection([id]), tok.id)
const box = (o) => ({ l: o.x - o.width / 2, t: o.y - o.height / 2, r: o.x + o.width / 2, b: o.y + o.height / 2 })
const b0 = box(t2)
await drag(gm, await toClient(gm, b0.r, b0.b), await toClient(gm, b0.r + 75, b0.b + 60))
await gm.waitForTimeout(400)
const b1 = box((await state(gm)).objects.find((o) => o.id === tok.id))
check('resize from bottom-right keeps top-left', b1.l === b0.l && b1.t === b0.t && b1.r === b0.r + 70 && b1.b === b0.b + 70, JSON.stringify({ b0, b1 }))
await drag(gm, await toClient(gm, b1.l, b1.t), await toClient(gm, b1.l + 65, b1.t + 72))
await gm.waitForTimeout(400)
const b2 = box((await state(pl)).objects.find((o) => o.id === tok.id))
check('resize from top-left keeps bottom-right', b2.r === b1.r && b2.b === b1.b && b2.l === b1.l + 70 && b2.t === b1.t + 70, JSON.stringify({ b1, b2 }))
await gm.screenshot({ path: `${OUT}/resize-handles.png` })
// Image off the grid with a size of 100 px (1.43 cells): resizing gives whole cells on grid lines.
const imgId = await gm.evaluate(() => {
  const s = window.__store
  const id = crypto.randomUUID()
  s.createObjects([
    { id, page_id: s.page.id, kind: 'image', layer: 'objects', x: 1213, y: 333, width: 100, height: 100, rotation: 0, props: { name: 'odd' } },
  ])
  s.setSelection([id])
  return id
})
await gm.waitForTimeout(400)
await drag(gm, await toClient(gm, 1263, 383), await toClient(gm, 1263 + 80, 383 + 50))
await gm.waitForTimeout(400)
const img = (await state(gm)).objects.find((o) => o.id === imgId)
// Top-left was at 1163,283: it settles on the nearest grid line (1190,280).
check(
  'resize gives whole cells aligned to the grid',
  img.width === 210 && img.height === 140 && img.x - img.width / 2 === 1190 && img.y - img.height / 2 === 280,
  JSON.stringify(img && { x: img.x, y: img.y, w: img.width, h: img.height }),
)
await gm.evaluate((id) => window.__store.deleteObjects([id]), imgId)

// 5. Player drags own token now
t2 = (await state(pl)).objects.find((o) => o.id === tok.id)
const pc2 = await toClient(pl, t2.x, t2.y)
const pz = await pl.evaluate(() => window.__engine.zoom)
await drag(pl, pc2, { x: pc2.x, y: pc2.y + 70 * 2 * pz + 4 })
await pl.waitForTimeout(500)
g = await state(gm)
check('player moves own token', g.objects.find((o) => o.id === tok.id).y === t2.y + 140)

// 6. Player HUD: name and statuses only, no bar fields
await pl.evaluate((id) => window.__store.setSelection([id]), tok.id)
await pl.waitForTimeout(200)
check('HUD has no bar fields', (await pl.locator('.hud input').count()) === 0)
await pl.locator('.hud').getByRole('button', { name: 'Statuses' }).click()
await pl.locator('.hud .statuses').getByTitle('Prone').click()
await pl.waitForTimeout(400)
g = await state(gm)
check('HUD: toggle status', g.objects.find((o) => o.id === tok.id).props.statuses?.includes('prone'))
await pl.screenshot({ path: `${OUT}/hud.png` })

// 7. GM layer secret token
await gm.getByTitle(/GM layer/).click()
await gm.getByTitle('New token').click()
await gm.waitForTimeout(400)
g = await state(gm)
p = await state(pl)
const secret = g.objects.find((o) => o.layer === 'gm')
check('GM layer token hidden from players', !!secret && !p.objects.some((o) => o.id === secret.id))
await gm.getByTitle(/Objects & Tokens layer/).click()

// 8. Player draws rectangle
await pl.evaluate(() => (window.__store.tool = 'draw-rect'))
await drag(pl, await toClient(pl, 100, 100), await toClient(pl, 300, 250))
await pl.waitForTimeout(400)
g = await state(gm)
check('player draws a rectangle', g.objects.some((o) => o.kind === 'path' && o.props.shape === 'rect'))

// 9. Freehand
await pl.evaluate(() => (window.__store.tool = 'draw-free'))
const f1 = await toClient(pl, 400, 100)
await pl.mouse.move(f1.x, f1.y)
await pl.mouse.down()
for (let i = 1; i <= 20; i++) await pl.mouse.move(f1.x + i * 6, f1.y + Math.sin(i / 2) * 20)
await pl.mouse.up()
await pl.waitForTimeout(400)
g = await state(gm)
const free = g.objects.find((o) => o.kind === 'path' && o.props.shape === 'free')
check('freehand drawing', !!free && free.props.points.length > 10)

// 10. Template cone, 3 cells
await pl.evaluate(() => (window.__store.tool = 'template-cone'))
const c1 = await toClient(pl, 735, 735)
const c2 = await toClient(pl, 945, 735)
await pl.mouse.move(c1.x, c1.y)
await pl.mouse.down()
await pl.mouse.move(c2.x, c2.y, { steps: 6 })
await pl.screenshot({ path: `${OUT}/template-drag.png` })
await pl.mouse.up()
await pl.waitForTimeout(400)
g = await state(gm)
const cone = g.objects.find((o) => o.kind === 'template')
check('cone template created (3 cells)', !!cone && Math.abs(cone.props.size - 210) < 2, cone && `size ${cone.props.size}`)

// 11. Ruler (screenshot)
await pl.evaluate(() => (window.__store.tool = 'ruler'))
// Start right next to a grid corner: the ruler must still begin at the cell centre.
const r1 = await toClient(pl, 138, 488)
const r2 = await toClient(pl, 105 + 280, 525 + 210)
await pl.mouse.move(r1.x, r1.y)
await pl.mouse.down()
const rulerStart = await pl.evaluate(() => window.__engine.gesture.start)
check('ruler starts at a cell centre', rulerStart.x === 105 && rulerStart.y === 455, JSON.stringify(rulerStart))
await pl.mouse.move(r2.x, r2.y, { steps: 6 })
await pl.screenshot({ path: `${OUT}/ruler.png` })
const rulerLabel = await pl.evaluate(() => window.__engine.overlayLabel.text)
const seenRuler = await gm.waitForFunction(
  (t) => [...window.__engine.remoteRulers.values()][0]?.label.text === t, rulerLabel, { timeout: 3000 },
).then(() => true, () => false)
check('GM sees the player ruler live', seenRuler, `${rulerLabel} vs ${await remoteRulers(gm)}`)
await gm.screenshot({ path: `${OUT}/ruler-shared.png` })
await pl.mouse.up()
check('ruler disappears for the GM on release', await waitRemoteRulers(gm, 0))
await pl.evaluate(() => (window.__store.tool = 'select'))

// 12. Text tool (GM)
await gm.evaluate(() => (window.__store.tool = 'text'))
const tp = await toClient(gm, 900, 200)
await gm.mouse.click(tp.x, tp.y)
await gm.locator('.text-input').fill('Dragon Tavern')
await gm.locator('.text-input').press('Enter')
await gm.waitForTimeout(400)
p = await state(pl)
check('text on the map', p.objects.some((o) => o.kind === 'text' && o.props.text === 'Dragon Tavern'))
await gm.evaluate(() => (window.__store.tool = 'select'))

// 13. Turn order
await gm.evaluate((id) => window.__store.setSelection([id]), tok.id)
if (!(await gm.locator('div.tracker').isVisible())) await gm.locator('button.tracker').click()
await gm.getByRole('button', { name: 'Add selected' }).click({ timeout: 4000 })
await gm.waitForTimeout(500)
p = await state(pl)
check('turn order: entry added', p.game.turn_order.length === 1)
check('tracker opens by itself for the player', await pl.locator('div.tracker').isVisible())

// 14. Context menu: right click on token -> to GM layer hides from player
const rc = await toClient(gm, g.objects.find((o) => o.id === tok.id).x, g.objects.find((o) => o.id === tok.id).y)
await gm.mouse.click(rc.x, rc.y, { button: 'right' })
await gm.getByRole('menu').getByRole('button', { name: /GM$/ }).click()
await gm.waitForTimeout(400)
p = await state(pl)
check('context menu: move to GM layer', !p.objects.some((o) => o.id === tok.id))
check('turn order entry hidden from players when token on GM layer', p.game.turn_order.length === 0)
await gm.evaluate((id) => window.__store.updateObjects([{ id, layer: 'objects' }]), tok.id)
await gm.waitForTimeout(300)

// 15. Whisper
await pl.getByLabel('Chat message').fill('/w gm I have a secret plan')
await pl.keyboard.press('Enter')
await gm.waitForTimeout(400)
check('whisper to GM', (await gm.locator('.log').innerText()).includes('I have a secret plan'))

// 16. New page + move players
await gm.getByTitle('New page').click()
await gm.waitForTimeout(400)
const pages = await gm.evaluate(() => window.__store.pages.map((x) => ({ id: x.id, name: x.name })))
const newPage = pages[pages.length - 1]
await gm.locator('.tab', { hasText: newPage.name }).locator('.tab-menu').click()
const menuLayout = await gm.evaluate(() => {
  const bar = document.querySelector('.topbar').getBoundingClientRect()
  const menu = document.querySelector('.topbar .menu').getBoundingClientRect()
  const strip = document.querySelector('.topbar .pages')
  return { overflows: menu.bottom > bar.bottom + 100, noScroll: strip.scrollHeight <= strip.clientHeight }
})
check('page menu drops below the top bar', menuLayout.overflows && menuLayout.noScroll)
await gm.screenshot({ path: `${OUT}/page-menu.png` })
await gm.getByRole('button', { name: 'Move all players here' }).click()
await pl.waitForTimeout(500)
p = await state(pl)
check('player moved to the new page', p.page.id === newPage.id)
await gm.evaluate((id) => window.__store.send({ type: 'game.player_page', page_id: id }), pages[0].id)
await pl.waitForTimeout(500)
await gm.evaluate((id) => window.__store.send({ type: 'page.delete', id }), newPage.id)
await gm.waitForTimeout(300)

// 17. Reload persistence (same tab identity)
await pl.reload()
await pl.waitForFunction(() => window.__engine && window.__store?.page)
await pl.waitForTimeout(600)
p = await state(pl)
check(
  'after reload: same identity and saved state',
  p.objects.some((o) => o.id === tok.id) && p.players.filter((x) => x.id === ariaId).length === 1,
)

// 18. Zoom wheel
const before = await gm.evaluate(() => window.__engine.zoom)
await gm.mouse.move(600, 400)
await gm.mouse.wheel(0, -300)
await gm.waitForTimeout(200)
check('mouse wheel zoom', (await gm.evaluate(() => window.__engine.zoom)) > before)
await gm.evaluate(() => window.__engine.fitPage())

// 19. Settings tab: the wheel can pan instead of zooming, and the choice persists
await gm.getByRole('button', { name: 'My Settings', exact: true }).click()
await gm.getByRole('button', { name: 'Pan the map' }).click()
const z0 = await gm.evaluate(() => window.__engine.zoom)
const o0 = await toClient(gm, 0, 0)
await gm.mouse.move(600, 400)
await gm.mouse.wheel(0, 200)
await gm.waitForTimeout(200)
const o1 = await toClient(gm, 0, 0)
check(
  'settings: wheel pans the map',
  (await gm.evaluate(() => window.__engine.zoom)) === z0 && Math.abs(o1.y - o0.y - -200) < 1,
  `zoom ${z0} dy ${o1.y - o0.y}`,
)
await gm.reload()
await gm.waitForFunction(() => window.__engine && window.__store?.page)
check('personal settings saved', (await gm.evaluate(() => window.__store.settings.wheel)) === 'pan')

// 20. Measurement system: metric by default, GM switch converts the page for everyone
p = await state(pl)
const metric = p.page.scale_number === 1.5 && p.page.scale_unit === 'm' && p.game.settings.measurement === 'metric'
await gm.getByRole('button', { name: 'My Settings', exact: true }).click()
await gm.getByRole('button', { name: 'Imperial' }).click()
await pl.waitForFunction(() => window.__store.page?.scale_unit === 'ft', null, { timeout: 3000 }).catch(() => {})
p = await state(pl)
check(
  'units: metric by default, GM switches to imperial',
  metric && p.page.scale_number === 5 && p.page.scale_unit === 'ft',
  `${p.page.scale_number} ${p.page.scale_unit}`,
)
await gm.getByRole('button', { name: 'Metric' }).click()
await gm.waitForTimeout(300)
await gm.screenshot({ path: `${OUT}/settings.png` })

// 21. Page settings: the grid opacity slider reaches both ends
await gm.getByRole('button', { name: /Page$/ }).click()
const slider = gm.locator('input[type="range"]').first()
const sb = await slider.boundingBox()
const opacity = () => gm.evaluate(() => window.__store.page.grid_opacity)
await gm.mouse.move(sb.x + sb.width / 2, sb.y + sb.height / 2)
await gm.mouse.down()
await gm.mouse.move(sb.x - 40, sb.y + sb.height / 2, { steps: 8 })
await gm.mouse.up()
await gm.waitForTimeout(300)
const low = await opacity()
await gm.mouse.move(sb.x + sb.width / 2, sb.y + sb.height / 2)
await gm.mouse.down()
await gm.mouse.move(sb.x + sb.width + 40, sb.y + sb.height / 2, { steps: 8 })
await gm.mouse.up()
await gm.waitForTimeout(300)
const high = await opacity()
await slider.screenshot({ path: `${OUT}/opacity-slider.png` })
check('grid opacity slider reaches 0% and 100%', low === 0 && high === 1, `${low} / ${high}`)

// 22. The grid is drawn over the map layer, under tokens
const order = await gm.evaluate(() => window.__engine.world.children.map((c) => c.label || ''))
check('grid sits between map layer and objects', order.indexOf('layer:map') < order.indexOf('grid') && order.indexOf('grid') < order.indexOf('layer:objects'), order.join(','))

// 23. Token stamp: an image dropped on the map is framed before becoming a token
await gm.evaluate(() => (window.__store.layer = 'objects'))
const pngBase64 = await gm.evaluate(() => {
  const c = document.createElement('canvas')
  c.width = 300
  c.height = 200
  const ctx = c.getContext('2d')
  ctx.fillStyle = 'rgb(200 80 120)'
  ctx.fillRect(0, 0, 300, 200)
  ctx.fillStyle = 'rgb(80 200 160)'
  ctx.fillRect(100, 50, 100, 100)
  return c.toDataURL('image/png').split(',')[1]
})
const tokensBefore = (await state(gm)).objects.filter((o) => o.kind === 'token').length
await gm.evaluate((b64) => {
  const bytes = Uint8Array.from(atob(b64), (ch) => ch.charCodeAt(0))
  const dt = new DataTransfer()
  dt.items.add(new File([bytes], 'hero.png', { type: 'image/png' }))
  const map = document.querySelector('.map')
  const r = map.getBoundingClientRect()
  map.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, clientX: r.left + r.width / 2, clientY: r.top + r.height / 2, bubbles: true }))
}, pngBase64)
const stampDialog = gm.getByRole('dialog', { name: 'Token stamp' })
await stampDialog.waitFor({ timeout: 3000 })
const stampCanvas = await stampDialog.locator('canvas').boundingBox()
await drag(gm, { x: stampCanvas.x + 170, y: stampCanvas.y + 170 }, { x: stampCanvas.x + 200, y: stampCanvas.y + 150 })
await stampDialog.getByRole('button', { name: 'Double' }).click()
await gm.screenshot({ path: `${OUT}/token-stamp.png` })
await stampDialog.getByRole('button', { name: 'Create token' }).click()
await gm.waitForFunction((n) => [...window.__store.objects.values()].filter((o) => o.kind === 'token').length > n, tokensBefore, { timeout: 5000 }).catch(() => {})
const stamped = (await state(gm)).objects.filter((o) => o.kind === 'token').at(-1)
const stampedSize = stamped && (await gm.evaluate((src) => new Promise((ok) => {
  const i = new Image()
  i.onload = () => ok([i.naturalWidth, i.naturalHeight])
  i.onerror = () => ok(null)
  i.src = src
}), stamped.props.image))
check(
  'dropped image framed into a 512 px square token',
  !!stamped && stamped.props.name === 'hero' && stampedSize?.[0] === 512 && stampedSize?.[1] === 512 && stamped.width === 70,
  JSON.stringify({ name: stamped?.props.name, stampedSize, w: stamped?.width }),
)

// 24. Token editor: "Upload image" opens the stamp too
await gm.evaluate(() => window.__store.setSelection([]))
const sc = await toClient(gm, stamped.x, stamped.y)
await gm.mouse.dblclick(sc.x, sc.y)
const editor = gm.getByRole('dialog', { name: 'Token settings' })
await editor.waitFor()
const chooser = gm.waitForEvent('filechooser')
await editor.getByRole('button', { name: 'Upload image' }).click()
await (await chooser).setFiles({ name: 'villain.png', mimeType: 'image/png', buffer: Buffer.from(pngBase64, 'base64') })
await stampDialog.waitFor({ timeout: 3000 })
// Double click on the rotation slider puts it back to 0°.
const rotation = stampDialog.getByLabel('Rotation')
await rotation.fill('90')
await rotation.dblclick()
check('stamp rotation resets on double click', (await rotation.inputValue()) === '0')
await stampDialog.getByRole('button', { name: 'Create token' }).click()
await stampDialog.waitFor({ state: 'detached', timeout: 5000 })
await gm.waitForFunction(() => !document.querySelector('.dialog button[disabled]'), null, { timeout: 5000 }).catch(() => {})
await editor.getByRole('button', { name: 'Save' }).click()
await gm.waitForTimeout(500)
const restamped = (await state(gm)).objects.find((o) => o.id === stamped.id)
check('editor upload goes through the stamp', restamped.props.image !== stamped.props.image && restamped.props.image.endsWith('.png'), restamped.props.image)

} catch (e) {
  results.push(`FAIL aborted: ${e.message.split('\n')[0]}`)
} finally {
  await gm?.screenshot({ path: `${OUT}/gm-final.png` })
  await pl?.screenshot({ path: `${OUT}/pl-final.png` })
  console.log(results.join('\n'))
  if (errors.length) console.log('JavaScript errors:', errors)
  await browser.close()
  stopServers()
  const failed = results.filter((r) => r.startsWith('FAIL')).length
  console.log(`\n${results.length - failed}/${results.length} checks passed. Screenshots in ${OUT}`)
  process.exitCode = failed || errors.length ? 1 : 0
}
