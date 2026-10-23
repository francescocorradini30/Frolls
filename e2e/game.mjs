// End-to-end check of the game mechanics with two real browser tabs (GM + player).
// Isolated servers and database: see harness.mjs. Needs a local Chrome or Edge.
// Usage: npm run e2e            (headless)
//        HEADED=1 npm run e2e   (watch it)
import { OUT, check, drag, launchBrowser, report, results, startServers, state, tab as openTab, toClient } from './harness.mjs'

const stopServers = await startServers()
const browser = await launchBrowser()
const tab = (name, gm) => openTab(browser, name, gm)

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
const hpBubble = pl.getByRole('textbox', { name: 'HP', exact: true })
await hpBubble.fill('-5')
await hpBubble.press('Enter')
await pl.waitForTimeout(400)
g = await state(gm)
const hpBar = g.objects.find((o) => o.id === tok.id).props.bar1
check('HP bubble: relative -5, max shown below', hpBar.value === 17 && (await pl.locator('.bubble .max').first().innerText()) === '30', JSON.stringify(hpBar))
await pl.locator('.hud-wrap').screenshot({ path: `${OUT}/hud-bubbles.png` })
// Close-up of the token: bars sit inside the bottom of its box.
const tokNow = g.objects.find((o) => o.id === tok.id)
await pl.evaluate((t) => {
  window.__store.setSelection([])
  window.__engine.zoomBy(3 / window.__engine.zoom)
  window.__engine.centerOn(t.x, t.y)
}, tokNow)
await pl.waitForTimeout(200)
const tcl = await toClient(pl, tokNow.x, tokNow.y)
const half = (Math.max(tokNow.width, tokNow.height) / 2) * 3 + 40
await pl.screenshot({ path: `${OUT}/token-bars.png`, clip: { x: tcl.x - half, y: tcl.y - half, width: half * 2, height: half * 2 } })
await pl.evaluate((id) => {
  window.__engine.fitPage()
  window.__store.setSelection([id])
}, tok.id)
await pl.waitForTimeout(200)
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

// 10. Spell area circle, 3 cells
await pl.evaluate(() => (window.__store.tool = 'template-circle'))
const c1 = await toClient(pl, 735, 735)
const c2 = await toClient(pl, 945, 735)
await pl.mouse.move(c1.x, c1.y)
await pl.mouse.down()
await pl.mouse.move(c2.x, c2.y, { steps: 6 })
await pl.screenshot({ path: `${OUT}/template-drag.png` })
await pl.mouse.up()
await pl.waitForTimeout(400)
g = await state(gm)
const area = g.objects.find((o) => o.kind === 'template')
check('circle area created (3 cells radius)', !!area && area.props.shape === 'circle' && Math.abs(area.props.size - 245) < 2, area && `size ${area.props.size}`)
const areasBefore = g.objects.filter((o) => o.kind === 'template').length
const c3 = await toClient(pl, 315, 315)
await pl.mouse.click(c3.x, c3.y)
await pl.waitForTimeout(300)
g = await state(gm)
check('click with circle tool creates no area', g.objects.filter((o) => o.kind === 'template').length === areasBefore)
await pl.evaluate(() => (window.__store.tool = 'select'))
const m1 = await toClient(pl, 735, 735)
const m2 = await toClient(pl, 785, 755)
await pl.mouse.move(m1.x, m1.y)
await pl.mouse.down()
await pl.mouse.move(m2.x, m2.y, { steps: 6 })
await pl.mouse.up()
await pl.waitForTimeout(400)
g = await state(gm)
const movedArea = g.objects.find((o) => o.id === area?.id)
check('moved area snaps to a cell centre', !!movedArea && movedArea.x === 805 && movedArea.y === 735, movedArea && `at ${movedArea.x},${movedArea.y}`)

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
await stampDialog.getByRole('button', { name: 'Double' }).click()
await stampDialog.getByRole('button', { name: 'Create token' }).click()
await stampDialog.waitFor({ state: 'detached', timeout: 5000 })
await gm.waitForFunction(() => !document.querySelector('.dialog button[disabled]'), null, { timeout: 5000 }).catch(() => {})
await editor.getByRole('button', { name: 'Save' }).click()
await gm.waitForTimeout(500)
const restamped = (await state(gm)).objects.find((o) => o.id === stamped.id)
check('editor upload goes through the stamp', restamped.props.image !== stamped.props.image && restamped.props.image.endsWith('.webp'), restamped.props.image)

// 25. "Edit token" reframes it from the original picture, with the previous settings
const rc2 = await toClient(gm, restamped.x, restamped.y)
await gm.mouse.dblclick(rc2.x, rc2.y)
await editor.waitFor()
await editor.getByRole('button', { name: 'Edit token' }).click()
await stampDialog.waitFor({ timeout: 3000 })
const kept = await stampDialog.getByRole('button', { name: 'Double' }).evaluate((b) => b.classList.contains('on'))
await stampDialog.getByRole('button', { name: 'Bevel' }).click()
await stampDialog.getByRole('button', { name: 'Update token' }).click()
await stampDialog.waitFor({ state: 'detached', timeout: 5000 })
await editor.getByRole('button', { name: 'Save' }).click()
await gm.waitForTimeout(500)
const edited = (await state(gm)).objects.find((o) => o.id === stamped.id)
check(
  'edit token keeps the original and the settings',
  kept && edited.props.stamp?.border === 'bevel' && edited.props.stamp.source === restamped.props.stamp?.source && edited.props.image !== restamped.props.image,
  JSON.stringify({ kept, before: restamped.props.stamp, after: edited.props.stamp }),
)

// 26. Undo / redo with the keyboard, seen by the other player too
const idsBefore = new Set((await state(gm)).objects.map((o) => o.id))
await gm.keyboard.press('Escape')
await gm.getByTitle('New token').click()
await gm.waitForTimeout(400)
const fresh = (await state(gm)).objects.find((o) => !idsBefore.has(o.id))
const fc = await toClient(gm, fresh.x, fresh.y)
await gm.mouse.click(fc.x, fc.y)
await gm.keyboard.press('ArrowRight')
await gm.waitForTimeout(300)
const xOf = async (page) => (await state(page)).objects.find((o) => o.id === fresh.id)?.x
const undoTitle = await gm.getByLabel('Undo').getAttribute('title')
check('undo button names the last change', undoTitle.startsWith('Undo: moved token'), undoTitle)
await gm.keyboard.press('Control+z')
await gm.waitForTimeout(400)
check('Ctrl+Z undoes the move, for everyone', (await xOf(gm)) === fresh.x && (await xOf(pl)) === fresh.x)
await gm.keyboard.press('Control+y')
await gm.waitForTimeout(400)
check('Ctrl+Y redoes it', (await xOf(gm)) === fresh.x + 70 && (await xOf(pl)) === fresh.x + 70)

// 27. GM history: list and revert
await gm.getByRole('button', { name: 'History' }).click()
const historyRow = gm.locator('.history li').first()
await historyRow.waitFor({ timeout: 3000 })
const rowText = await historyRow.innerText()
check('history lists the latest change first', rowText.includes('redid: moved token'), rowText)
const rowSeq = rowText.match(/#\d+/)[0]
await historyRow.getByRole('button', { name: 'Revert' }).click()
await gm.waitForTimeout(400)
check('history revert brings the token back', (await xOf(pl)) === fresh.x)
const revertedRow = gm.locator('.history li', { hasText: `${rowSeq} ·` })
check('reverted entry is marked', (await revertedRow.innerText()).includes('reverted'))
await pl.keyboard.press('Control+z')
await pl.waitForTimeout(400)
check('a player cannot undo the GM change', (await xOf(gm)) === fresh.x)

// 28. Reconnect: only what changed while offline is sent back
await pl.evaluate(() => {
  const s = window.__store
  window.__resumed = false
  const receive = s.receive.bind(s)
  s.receive = (m) => {
    if (m.type === 'page.resume') window.__resumed = true
    receive(m)
  }
  // Drop the connection without letting it reconnect by itself.
  s.socket.closed = true
  s.socket.ws.close()
})
await pl.waitForTimeout(300)
await gm.evaluate((id) => window.__store.updateObjects([{ id, x: 1015 }]), fresh.id)
await gm.waitForTimeout(300)
await pl.evaluate(() => window.__store.connect(window.__store.identityValue))
await pl.waitForFunction(() => window.__resumed, null, { timeout: 5000 }).catch(() => {})
check('reconnect resumes instead of reloading the page', await pl.evaluate(() => window.__resumed))
check('change made while offline arrives', (await xOf(pl)) === 1015)

// 29. Journal: the GM creates a character and gives it to the player
await gm.getByRole('button', { name: 'Journal' }).click()
await gm.getByRole('button', { name: '+ Character' }).click()
const sheet = gm.getByRole('dialog', { name: 'Character' })
await sheet.waitFor({ timeout: 3000 })
await sheet.getByLabel('Name', { exact: true }).fill('Aria the Ranger')
await sheet.getByLabel('Played by').selectOption({ label: 'Aria' })
await sheet.getByRole('button', { name: '+ Attribute' }).click()
await sheet.getByLabel('Attribute name').fill('hp')
await sheet.getByLabel('Current value').fill('18')
await sheet.getByLabel('GM Notes (hidden from players)').fill('Secretly a noble')
await sheet.getByLabel('Bio').fill('Raised by [Aria the Ranger] herself.')
await sheet.getByRole('button', { name: 'Save' }).click()
await sheet.waitFor({ state: 'detached', timeout: 3000 })
const heroOf = (page) => page.evaluate(() => window.__store.characters.find((c) => c.name === 'Aria the Ranger'))
await gm.waitForFunction(() => window.__store.characters.some((c) => c.name === 'Aria the Ranger' && c.attributes.length), null, { timeout: 3000 }).catch(() => {})
const hero = await heroOf(gm)
check('GM creates a character', hero?.player_id === ariaId && hero.attributes[0]?.current === '18', JSON.stringify(hero))
await pl.getByRole('button', { name: 'Journal' }).click()
const plRow = pl.locator('.journal .character', { hasText: 'Aria the Ranger' })
await plRow.waitFor({ timeout: 3000 })
check('the player sees the character they play', true)
check('the player never receives GM notes', (await heroOf(pl)).gm_notes === undefined)
await plRow.click()
const plSheet = pl.getByRole('dialog', { name: 'Character' })
await plSheet.waitFor()
check('player sheet: no GM notes, links in the bio', (await plSheet.getByLabel('GM Notes (hidden from players)').count()) === 0 && (await plSheet.locator('.bio .link').count()) === 1)
await plSheet.getByRole('button', { name: 'Close' }).first().click()

// 30. Folders
await gm.getByRole('button', { name: '+ Folder' }).click()
await gm.getByPlaceholder('Folder name').fill('Heroes')
await gm.getByPlaceholder('Folder name').press('Enter')
await gm.locator('.journal .character', { hasText: 'Aria the Ranger' }).click()
await sheet.getByLabel('Folder').selectOption({ label: 'Heroes' })
await sheet.getByRole('button', { name: 'Save' }).click()
await gm.waitForTimeout(400)
const folder = await gm.evaluate(() => window.__store.folders.find((f) => f.name === 'Heroes'))
check('character goes into a folder', !!folder && (await heroOf(gm)).folder_id === folder.id)
await gm.screenshot({ path: `${OUT}/gm-journal.png` })
check('players do not receive the GM folders', (await pl.evaluate(() => window.__store.folders.length)) === 0)

// 31. Drag the character onto the map: a linked token
const beforeDrop = new Set((await state(gm)).objects.map((o) => o.id))
await gm.locator('.journal .character', { hasText: 'Aria the Ranger' }).dragTo(gm.locator('.map'), { targetPosition: { x: 300, y: 300 } })
await gm.waitForTimeout(500)
const dropped = (await state(gm)).objects.find((o) => !beforeDrop.has(o.id))
check(
  'dragging a character onto the map places its linked token',
  dropped?.props.represents === hero.id && dropped.props.name === 'Aria the Ranger' && dropped.props.controlled_by?.includes(ariaId),
  JSON.stringify(dropped?.props),
)

// 32. Link an existing token from its settings
await gm.keyboard.press('Escape')
await gm.getByTitle('New token').click()
await gm.waitForTimeout(400)
const plain = (await state(gm)).objects.find((o) => !beforeDrop.has(o.id) && o.id !== dropped?.id)
const plainAt = await toClient(gm, plain.x, plain.y)
await gm.mouse.dblclick(plainAt.x, plainAt.y)
await dialog.waitFor()
await dialog.getByLabel('Represents character').selectOption({ label: 'Aria the Ranger' })
const linkedName = await dialog.locator('label.field input').first().inputValue()
await dialog.getByRole('button', { name: 'Save' }).click()
await gm.waitForTimeout(400)
const linked = (await state(gm)).objects.find((o) => o.id === plain.id)
check('token settings link a character', linked.props.represents === hero.id && linkedName === 'Aria the Ranger', JSON.stringify(linked.props))

// 33. Chat names: the player speaks as their character, the GM picks one
await pl.getByRole('button', { name: /Chat/ }).click()
await pl.getByLabel('Chat message').fill('Ready for adventure')
await pl.getByLabel('Chat message').press('Enter')
await gm.getByRole('button', { name: /Chat/ }).click()
await gm.getByLabel('Speaking as').selectOption({ label: 'As Aria the Ranger' })
await gm.getByLabel('Chat message').fill('The GM speaks for you')
await gm.getByLabel('Chat message').press('Enter')
await gm.waitForTimeout(500)
const speakers = await gm.evaluate(() => window.__store.chat.slice(-2).map((m) => m.speaker))
check('player chat uses the character name; GM speaks as a character', speakers.every((s) => s === 'Aria the Ranger'), JSON.stringify(speakers))
await gm.getByLabel('Speaking as').selectOption({ index: 0 })

const lastChat = (page) => page.evaluate(() => JSON.parse(JSON.stringify(window.__store.chat.at(-1))))

// 34. A player macro in the quick bar, with a roll query
await pl.getByRole('button', { name: 'Macros' }).click()
await pl.getByRole('button', { name: '+ Macro' }).click()
await pl.getByLabel('Macro name').fill('Hit')
await pl.getByLabel('Macro action').fill('/r 1d20+?{Bonus|2}')
await pl.getByRole('button', { name: 'Save' }).click()
const barButton = pl.locator('.quickbar button', { hasText: 'Hit' })
await barButton.waitFor({ timeout: 3000 })
await barButton.click()
const questions = pl.getByRole('dialog', { name: 'Roll questions' })
await questions.waitFor({ timeout: 3000 })
check('a roll query opens one dialog with the default', (await questions.getByLabel('Bonus').inputValue()) === '2')
await questions.getByLabel('Bonus').fill('4')
await questions.getByRole('button', { name: 'Roll' }).click()
await pl.waitForTimeout(500)
check('the macro rolls with the answer', (await lastChat(pl)).roll?.main?.expression === '1d20+4', JSON.stringify((await lastChat(pl)).roll?.main?.expression))

// 35. Roll template card
await pl.getByRole('button', { name: /Chat/ }).click()
await pl.getByLabel('Chat message').fill('&{template:default} {{name=Longbow}} {{Attack=[[1d20+7]]}}')
await pl.getByLabel('Chat message').press('Enter')
const card = gm.locator('.template').last()
await card.waitFor({ timeout: 3000 })
check('roll template shows as a card', (await card.locator('.template-title').innerText()) === 'Longbow' && (await card.locator('.inline').count()) === 1)

// 36. Token action of the character, with its attribute
await gm.locator('.journal .character', { hasText: 'Aria the Ranger' }).click().catch(async () => {
  await gm.getByRole('button', { name: 'Journal' }).click()
  await gm.locator('.journal .character', { hasText: 'Aria the Ranger' }).click()
})
await sheet.getByRole('button', { name: '+ Ability' }).click()
await sheet.getByLabel('Ability name').fill('Shoot')
await sheet.getByLabel('Ability action').fill('/r 1d20+@{hp}')
await sheet.getByRole('button', { name: 'Save' }).click()
await gm.waitForTimeout(400)
const heroTokenAt = await toClient(pl, dropped.x, dropped.y)
await pl.mouse.click(heroTokenAt.x, heroTokenAt.y)
const shoot = pl.locator('.quickbar button', { hasText: 'Shoot' })
await shoot.waitFor({ timeout: 3000 })
await shoot.click()
await pl.waitForTimeout(500)
check('token action uses the character attribute', (await lastChat(pl)).roll?.main?.expression === '1d20+18', JSON.stringify((await lastChat(pl)).roll?.main))

// 37. @{target|…}: click a token to pick the target
await gm.getByRole('button', { name: /Chat/ }).click()
await gm.getByLabel('Chat message').fill('Target HP [[@{target|hp}]]')
await gm.getByLabel('Chat message').press('Enter')
await gm.waitForFunction(() => window.__store.targetPick, null, { timeout: 3000 })
const targetAt = await toClient(gm, fresh.x, fresh.y)
await gm.mouse.click(targetAt.x, targetAt.y)
await gm.waitForTimeout(500)
check('clicking a target token completes @{target|hp}', (await lastChat(gm)).roll?.inline?.[0]?.total === 10, JSON.stringify((await lastChat(gm)).roll))

// 38. 5e sheet: create it, change a score, roll from it
await gm.getByRole('button', { name: 'Journal' }).click()
await gm.locator('.journal .character', { hasText: 'Aria the Ranger' }).click()
await sheet.getByRole('button', { name: 'Create character sheet' }).click()
const strength = sheet.getByLabel('Strength score')
await strength.waitFor({ timeout: 3000 })
await strength.fill('16')
await strength.press('Tab')
await gm.waitForFunction(() => window.__store.characters.find((c) => c.name === 'Aria the Ranger')?.derived?.modifiers.str === 3, null, { timeout: 3000 }).catch(() => {})
check('the sheet computes the modifier', (await sheet.getByTitle('Strength check').innerText()) === '+3')
await sheet.getByTitle('Strength save').click()
await gm.waitForTimeout(500)
let lastCard = (await lastChat(gm)).roll?.template
check('a save from the sheet goes to chat', lastCard?.title === 'Aria the Ranger: Strength save', JSON.stringify(lastCard))
await sheet.getByRole('radio', { name: 'Adv' }).click()
await sheet.getByTitle('Strength check').click()
await gm.waitForTimeout(500)
const advRoll = (await lastChat(gm)).roll?.inline?.[0]?.expression
check('advantage rolls 2d20 and keeps the highest', advRoll === '2d20kh1+3', advRoll)
await sheet.getByRole('radio', { name: 'Normal' }).click()
await sheet.getByRole('button', { name: '+ Attack' }).click()
await sheet.getByTitle('Damage roll').waitFor({ timeout: 3000 })
await sheet.getByTitle('Damage roll').click()
await gm.waitForTimeout(500)
lastCard = (await lastChat(gm)).roll?.template
await gm.screenshot({ path: `${OUT}/gm-sheet.png` })
check('attack damage from the sheet', lastCard?.title === 'Aria the Ranger: Attack damage' && (await lastChat(gm)).roll.inline[0].expression === '1d6+3', JSON.stringify(lastCard))
await sheet.getByRole('button', { name: 'Close' }).first().click()

// 39. Damage from a chat card to the selected token: hit points of the sheet and of the token
const heroHp = () => gm.evaluate(() => {
  const c = window.__store.characters.find((x) => x.name === 'Aria the Ranger')
  return c?.sheet?.hp.current
})
const heroTokenHp = () => gm.evaluate((id) => window.__store.objects.get(id)?.props.bar1?.value, dropped.id)
check('a linked token shows the sheet hit points', (await heroTokenHp()) === (await heroHp()), `${await heroTokenHp()} vs ${await heroHp()}`)
await gm.getByRole('button', { name: /Chat/ }).click()
const dropAt = await toClient(gm, dropped.x, dropped.y)
await gm.mouse.click(dropAt.x, dropAt.y)
const damageTaken = (await lastChat(gm)).roll.inline[0].total
await gm.locator('.chat-button', { hasText: /^To selected$/ }).last().click()
await gm.waitForFunction((hp) => {
  const c = window.__store.characters.find((x) => x.name === 'Aria the Ranger')
  return c?.sheet?.hp.current !== hp
}, 10, { timeout: 3000 }).catch(() => {})
const afterHit = await heroHp()
check('applying damage lowers the sheet hit points', afterHit === Math.max(0, 10 - damageTaken), `${afterHit} after ${damageTaken}`)
await gm.waitForTimeout(300)
check('…and the token shows them', (await heroTokenHp()) === afterHit)
await gm.getByRole('button', { name: 'Journal' }).click()
await gm.locator('.journal .character', { hasText: 'Aria the Ranger' }).click()
await sheet.getByRole('button', { name: 'Long rest' }).click()
await gm.waitForTimeout(500)
check('a long rest restores the hit points', (await heroHp()) === 10 && (await heroTokenHp()) === 10)
await sheet.getByRole('button', { name: 'Close' }).first().click()

// 40. Combat: initiative for the selected tokens, action economy, next turn
await gm.keyboard.press('Escape')
// Selecting on the map is covered above; here two known tokens are selected directly.
await gm.evaluate((ids) => window.__store.setSelection(ids), [dropped.id, fresh.id])
const tracker = gm.locator('div.tracker')
if (!(await tracker.isVisible())) await gm.getByTitle('Turn Order').click()
await tracker.getByRole('button', { name: '🎲 Initiative' }).click()
await gm.waitForFunction((ids) => {
  const order = window.__store.game?.turn_order ?? []
  return ids.every((id) => order.some((e) => e.object_id === id))
}, [dropped.id, fresh.id], { timeout: 3000 }).catch(() => {})
const combat = await gm.evaluate(() => JSON.parse(JSON.stringify(window.__store.game)))
const rolled = combat.turn_order.filter((e) => [dropped.id, fresh.id].includes(e.object_id))
check('initiative puts the selected tokens in the tracker', rolled.length === 2 && combat.settings.round >= 1, JSON.stringify(combat.turn_order))
const values = combat.turn_order.map((e) => Number(e.value))
check('the tracker is sorted, highest first', values.every((v, i) => i === 0 || values[i - 1] >= v), values.join(','))
await tracker.locator('.economy .chip', { hasText: /^Action$/ }).click()
await gm.waitForTimeout(400)
check('the action of the current combatant can be marked as used', await gm.evaluate(() => !!window.__store.game.turn_order[0].used?.action))
const firstBefore = combat.turn_order[0].id
await tracker.getByRole('button', { name: 'Next turn ▶' }).click()
await gm.waitForTimeout(400)
const afterNext = await gm.evaluate(() => JSON.parse(JSON.stringify(window.__store.game.turn_order)))
check('next turn moves on and resets the actions', afterNext[0].id !== firstBefore && !afterNext[0].used?.action)
await gm.screenshot({ path: `${OUT}/gm-combat.png` })

// 41. Spells: a slot, an effect on the target, concentration on the caster
const effectsOf = (id) => gm.evaluate((oid) => (window.__store.objects.get(oid)?.props.effects ?? []).map((e) => e.name), id)
await gm.getByRole('button', { name: 'Journal' }).click()
await gm.locator('.journal .character', { hasText: 'Aria the Ranger' }).click()
await sheet.getByLabel('Spellcasting ability').selectOption('wis')
await sheet.getByLabel('Level 1 slots').fill('2')
await sheet.getByLabel('Level 1 slots').press('Tab')
await sheet.getByRole('button', { name: '+ Spell' }).click()
const spellEdit = sheet.locator('.attack-edit').last()
await spellEdit.getByLabel('Name').fill('Bless')
await spellEdit.getByLabel('Name').press('Tab')
await gm.waitForTimeout(300)
await spellEdit.getByLabel('concentration').check()
await gm.waitForTimeout(300)
await spellEdit.getByLabel('Effect').selectOption('bless')
await gm.waitForTimeout(500)
await gm.evaluate((id) => window.__store.setSelection([id]), fresh.id)
await sheet.getByRole('button', { name: 'Cast' }).click()
await gm.waitForTimeout(800)
const heroSheet = await gm.evaluate(() => JSON.parse(JSON.stringify(window.__store.characters.find((c) => c.name === 'Aria the Ranger').sheet)))
check('casting uses a spell slot', heroSheet.spellcasting.slots['1']?.used === 1, JSON.stringify(heroSheet.spellcasting))
check('the spell puts its effect on the target', (await effectsOf(fresh.id)).includes('Bless'), JSON.stringify(await effectsOf(fresh.id)))
const heroStatuses = await gm.evaluate((id) => window.__store.objects.get(id)?.props.statuses ?? [], dropped.id)
check('the caster concentrates', heroStatuses.includes('concentrating'), JSON.stringify(heroStatuses))
await sheet.getByRole('button', { name: 'Close' }).first().click()

// 42. Effects from the token HUD: list, add a preset, remove
await gm.evaluate((id) => window.__store.setSelection([id]), fresh.id)
await gm.getByRole('button', { name: /^Effects/ }).click()
await gm.getByRole('button', { name: '+ Add effect' }).click()
const effectDialog = gm.getByRole('dialog', { name: 'Add effect' })
await effectDialog.getByLabel('Effect').selectOption('shield')
await effectDialog.getByRole('button', { name: 'Apply' }).click()
await gm.waitForTimeout(500)
check('an effect added from the HUD', (await effectsOf(fresh.id)).includes('Shield'), JSON.stringify(await effectsOf(fresh.id)))
await gm.getByRole('button', { name: /^Effects/ }).click()
await gm.getByRole('button', { name: 'Remove Shield' }).click()
await gm.waitForTimeout(500)
check('an effect removed from the HUD', !(await effectsOf(fresh.id)).includes('Shield'))
await gm.screenshot({ path: `${OUT}/gm-effects.png` })

// 43. Compendium: a monster dragged onto the map, a spell added to a sheet
await gm.getByRole('button', { name: 'Compendium' }).click()
await gm.getByLabel('Search the compendium').fill('goblin warrior')
const goblinRow = gm.locator('.compendium .result', { has: gm.locator('.name', { hasText: /^Goblin Warrior$/ }) })
await goblinRow.waitFor({ timeout: 3000 })
await goblinRow.dragTo(gm.locator('.map'), { targetPosition: { x: 420, y: 520 } })
await gm.waitForFunction(() => [...window.__store.objects.values()].some((o) => o.props.name === 'Goblin Warrior 1'), null, { timeout: 4000 }).catch(() => {})
const goblinToken = (await state(gm)).objects.find((o) => o.props.name === 'Goblin Warrior 1')
check('a compendium monster dropped on the map becomes a numbered token', !!goblinToken && goblinToken.props.bar1?.max === 10, JSON.stringify(goblinToken?.props))
const goblinNpc = await gm.evaluate(() => window.__store.characters.find((c) => c.name === 'Goblin Warrior')?.sheet?.cr)
check('…and an NPC in the journal with its stat block', goblinNpc === '1/4', goblinNpc)
await gm.locator('.compendium .seg button', { hasText: 'Spells' }).click()
await gm.getByLabel('Search the compendium').fill('fireball')
await gm.locator('.compendium .result', { has: gm.locator('.name', { hasText: /^Fireball$/ }) }).click()
await gm.getByLabel('Add the spell to').selectOption({ label: 'Aria the Ranger' })
await gm.getByRole('button', { name: 'Add spell' }).click()
await gm.waitForTimeout(600)
const heroSpells = await gm.evaluate(() => window.__store.characters.find((c) => c.name === 'Aria the Ranger').sheet.spells.map((s) => s.name))
check('a compendium spell added to a sheet', heroSpells.includes('Fireball'), JSON.stringify(heroSpells))
await gm.screenshot({ path: `${OUT}/gm-compendium.png` })

// 44. Fog of war: on, the player loses the monster under it; a revealed rectangle brings it back
const plSees = (id) => pl.evaluate((oid) => window.__store.objects.has(oid), id)
await gm.keyboard.press('Escape')
await gm.getByRole('button', { name: 'Fog of war' }).click()
await gm.getByLabel('fog on this page').check()
await pl.waitForFunction(() => window.__engine.fogSprite.visible, null, { timeout: 4000 }).catch(() => {})
check('the fog covers the map for the player', await pl.evaluate(() => window.__engine.fogSprite.visible && window.__engine.fogSprite.alpha === 1))
check('tokens under the fog are not sent to the player', !(await plSees(fresh.id)))
await gm.getByRole('button', { name: 'Reveal a rectangle' }).click()
const freshPos = (await state(gm)).objects.find((o) => o.id === fresh.id)
const fa = await toClient(gm, freshPos.x - 80, freshPos.y - 80)
const fb = await toClient(gm, freshPos.x + 80, freshPos.y + 80)
await drag(gm, fa, fb)
await pl.waitForFunction((oid) => window.__store.objects.has(oid), fresh.id, { timeout: 4000 }).catch(() => {})
check('a revealed rectangle shows what is under it', await plSees(fresh.id))
await gm.screenshot({ path: `${OUT}/gm-fog.png` })
await pl.screenshot({ path: `${OUT}/pl-fog.png` })
await gm.getByRole('button', { name: 'Fog of war' }).click()
await gm.getByLabel('fog on this page').uncheck()
await gm.keyboard.press('Escape')
await gm.evaluate(() => (window.__store.tool = 'select'))

// 45. Rollable tables: the GM fills one, a player rolls it in chat; hidden, it disappears
const png = () => ({ name: 'pic.png', mimeType: 'image/png', buffer: Buffer.from(pngBase64, 'base64') })
await gm.getByRole('button', { name: 'Collections' }).click()
await pl.getByRole('button', { name: 'Collections' }).click()
await gm.getByRole('button', { name: '+ Table' }).click()
await gm.getByRole('button', { name: 'Edit table-1' }).click()
await gm.getByLabel('Table name').fill('loot')
await gm.getByRole('button', { name: '+ Item', exact: true }).click()
await gm.getByLabel('Item 1 name').fill('Golden idol')
await gm.getByRole('button', { name: '+ Item', exact: true }).click()
await gm.getByLabel('Item 2 name').fill('Rusty key')
await gm.getByLabel('Item 2 weight').fill('0')
const itemPic = gm.waitForEvent('filechooser')
await gm.getByRole('button', { name: 'Picture of item 1' }).click()
await (await itemPic).setFiles(png())
await gm.waitForFunction(() => document.querySelector('.items .thumb')?.style.backgroundImage.includes('/uploads/'), null, { timeout: 4000 }).catch(() => {})
await gm.locator('.collections').getByRole('button', { name: 'Save' }).click()
await pl.getByRole('button', { name: '🎲 loot' }).waitFor({ timeout: 3000 }).catch(() => {})
check('a rollable table appears for the players', await pl.getByRole('button', { name: '🎲 loot' }).isVisible())
await pl.getByRole('button', { name: '🎲 loot' }).click()
await pl.getByRole('button', { name: 'Chat' }).click()
await pl.locator('.roll .total.text').last().waitFor({ timeout: 3000 }).catch(() => {})
const drawn = await pl.locator('.roll .total.text').last().textContent().catch(() => '')
check('rolling a table draws by weight (weight 0 never comes up)', drawn?.trim() === 'Golden idol', drawn)
check('the drawn item shows its picture', await pl.locator('.roll .item img').last().isVisible())
await gm.getByRole('button', { name: 'Edit loot' }).click()
await gm.getByLabel('Players can see and roll it').uncheck()
await gm.locator('.collections').getByRole('button', { name: 'Save' }).click()
await pl.waitForFunction(() => !window.__store.tables.length, null, { timeout: 3000 }).catch(() => {})
check('a hidden table disappears for the players', await pl.evaluate(() => !window.__store.tables.length))

// 46. A table dragged onto the map is a multi-sided token; a side chosen from the menu
const sidesBefore = (await state(gm)).objects.length
await gm.getByRole('button', { name: '🎲 loot' }).dragTo(gm.locator('.map'), { targetPosition: { x: 520, y: 300 } })
await gm.waitForFunction((n) => window.__store.objects.size > n, sidesBefore, { timeout: 3000 }).catch(() => {})
const sided = (await state(gm)).objects.find((o) => o.props.name === 'loot')
check('a table dropped on the map becomes a token with its pictures as sides', sided?.props.sides?.length === 1, JSON.stringify(sided?.props))
const side2 = restamped.props.image
await gm.evaluate(([id, url]) => window.__store.updateProps(id, { sides: [...window.__store.objects.get(id).props.sides, url] }), [sided.id, side2])
await gm.waitForTimeout(300)
const sc46 = await toClient(gm, sided.x, sided.y)
await gm.evaluate((id) => window.__store.setSelection([id]), sided.id)
await gm.mouse.click(sc46.x, sc46.y, { button: 'right' })
await gm.getByRole('button', { name: 'Side 2' }).click()
await gm.waitForFunction((id) => window.__store.objects.get(id).props.side === 1, sided.id, { timeout: 3000 }).catch(() => {})
check('choosing a side from the menu shows that picture', await gm.evaluate(([id, url]) => {
  const o = window.__store.objects.get(id)
  return o.props.side === 1 && o.props.image === url
}, [sided.id, side2]))
await gm.evaluate((id) => window.__store.deleteObjects([id]), sided.id)

// 47. Card decks: the GM builds one and deals, the player plays a card face down from the hand
await gm.getByRole('button', { name: '+ Deck' }).click()
await gm.getByRole('button', { name: 'Edit Deck 1' }).click()
await gm.getByLabel('Deck name').fill('Fate')
for (let i = 0; i < 3; i++) await gm.getByRole('button', { name: '+ Text card' }).click()
await gm.locator('.collections').getByRole('button', { name: 'Save' }).click()
await gm.getByText('3 in the deck').waitFor({ timeout: 3000 }).catch(() => {})
await gm.getByLabel('Deal from Fate to').selectOption({ label: 'Aria' })
await gm.getByRole('button', { name: 'Deal', exact: true }).click()
await pl.locator('.hand .card').first().waitFor({ timeout: 3000 }).catch(() => {})
check("a dealt card arrives in the player's hand", (await pl.locator('.hand .card').count()) === 1)
check('the GM sees how many cards the player holds', await gm.getByText('Aria: 1 in hand').isVisible())
await pl.locator('.hand .card').first().click()
await pl.getByRole('button', { name: 'Play face down' }).click()
await gm.waitForFunction(() => [...window.__store.objects.values()].some((o) => o.props.card), null, { timeout: 3000 }).catch(() => {})
const playedCard = (await state(gm)).objects.find((o) => o.props.card)
const plCard = (await state(pl)).objects.find((o) => o.id === playedCard?.id)
check('a card played face down: the GM knows which one', !!playedCard?.props.card && playedCard.props.side === 1, JSON.stringify(playedCard?.props))
check('the player who played it can turn it over', !!plCard?.props.card)
await pl.evaluate((id) => window.__store.tokenSide([id], 0), playedCard.id)
await gm.waitForFunction((id) => window.__store.objects.get(id)?.props.side === 0, playedCard.id, { timeout: 3000 }).catch(() => {})
check('flipped face up for everyone', await gm.evaluate((id) => window.__store.objects.get(id)?.props.side === 0, playedCard.id))
await gm.screenshot({ path: `${OUT}/gm-cards.png` })
await gm.getByRole('button', { name: 'Recall' }).click()
await gm.waitForFunction(() => ![...window.__store.objects.values()].some((o) => o.props.card), null, { timeout: 3000 }).catch(() => {})
await pl.waitForTimeout(400)
check('recall brings back the cards from the table and the hands', (await pl.locator('.hand .card').count()) === 0 && (await gm.getByText('3 in the deck').isVisible()))

// 48. Art library: upload, folder and tags, search, drag onto the map
await gm.getByRole('button', { name: 'Art library' }).click()
const libChooser = gm.waitForEvent('filechooser')
await gm.getByRole('button', { name: '+ Upload' }).click()
await (await libChooser).setFiles([{ ...png(), name: 'forest.png' }, { ...png(), name: 'cave.png' }])
await gm.waitForFunction(() => window.__store.assets.length === 2, null, { timeout: 5000 }).catch(() => {})
const libAssets = await gm.evaluate(() => JSON.parse(JSON.stringify(window.__store.assets)))
check('several pictures uploaded at once, stored as WebP with thumbnails', libAssets.length === 2 && libAssets.every((a) => a.url.endsWith('.webp') && a.thumb), JSON.stringify(libAssets))
await gm.getByRole('button', { name: 'forest' }).click()
await gm.getByLabel('Folder').fill('Outdoors')
await gm.getByLabel('Folder').press('Enter')
await gm.getByLabel('Tags').fill('Green, trees')
await gm.getByLabel('Tags').press('Enter')
await gm.waitForFunction(() => window.__store.assets.find((a) => a.name === 'forest')?.tags.length === 2, null, { timeout: 3000 }).catch(() => {})
await gm.getByLabel('Search the art library').fill('tree')
check('search finds pictures by tag', (await gm.locator('.library .tile').count()) === 1)
const libBefore = (await state(gm)).objects.length
await gm.locator('.library .tile').first().dragTo(gm.locator('.map'), { targetPosition: { x: 380, y: 260 } })
await gm.waitForFunction((n) => window.__store.objects.size > n, libBefore, { timeout: 3000 }).catch(() => {})
const libToken = (await state(gm)).objects.find((o) => o.props.name === 'forest')
check('a library picture dragged onto the map becomes a token', !!libToken && libToken.props.image === libAssets.find((a) => a.name === 'forest').url)
check('the art library is private to each player', await pl.evaluate(() => window.__store.assets.length === 0))
await gm.screenshot({ path: `${OUT}/gm-library.png` })
await gm.getByRole('button', { name: 'Chat' }).click()

// 49. Lock: a locked token can't be dragged; unlocked from the menu it moves again
await gm.keyboard.press('Escape')
const lockTok = libToken
const lc = await toClient(gm, lockTok.x, lockTok.y)
await gm.evaluate((id) => window.__store.setSelection([id]), lockTok.id)
await gm.mouse.click(lc.x, lc.y, { button: 'right' })
await gm.getByRole('button', { name: '🔒 Lock' }).click()
await gm.waitForFunction((id) => window.__store.objects.get(id)?.props.locked, lockTok.id, { timeout: 3000 }).catch(() => {})
await drag(gm, lc, { x: lc.x + 150, y: lc.y })
await gm.waitForTimeout(300)
const afterLock = (await state(gm)).objects.find((o) => o.id === lockTok.id)
check('a locked token does not move when dragged', afterLock.x === lockTok.x && afterLock.y === lockTok.y, JSON.stringify([afterLock.x, lockTok.x]))
check('…and dragging it shows no error', await gm.evaluate(() => !window.__store.toasts.some((t) => t.text.includes('invalid message'))))
await gm.mouse.click(lc.x, lc.y, { button: 'right' })
await gm.getByRole('button', { name: '🔓 Unlock' }).click()
await gm.waitForFunction((id) => !window.__store.objects.get(id)?.props.locked, lockTok.id, { timeout: 3000 }).catch(() => {})
await drag(gm, lc, { x: lc.x + 150, y: lc.y })
await gm.waitForTimeout(300)
check('unlocked, it moves again', (await state(gm)).objects.find((o) => o.id === lockTok.id).x !== lockTok.x)

await gm.evaluate((id) => window.__store.deleteObjects([id]), lockTok.id)

// 51. Ruler with waypoints: Space adds a stop, the label is the total along the path
await gm.evaluate(() => (window.__store.tool = 'ruler'))
const pg = await gm.evaluate(() => ({ s: window.__store.page.grid_size }))
const wp0 = await toClient(gm, pg.s * 14.5, pg.s * 12.5)
const wp1 = await toClient(gm, pg.s * 17.5, pg.s * 12.5)
const wp2 = await toClient(gm, pg.s * 14.5, pg.s * 12.5)
await gm.mouse.move(wp0.x, wp0.y)
await gm.mouse.down()
await gm.mouse.move(wp1.x, wp1.y, { steps: 6 })
await gm.keyboard.press('Space')
await gm.mouse.move(wp2.x, wp2.y, { steps: 6 })
const wpLabel = await gm.evaluate(() => window.__engine.overlayLabel.text)
await pl.waitForFunction(() => window.__engine.remoteRulers.size === 1 && [...window.__engine.remoteRulers.values()][0].label.text.length > 0, null, { timeout: 3000 }).catch(() => {})
await pl.waitForFunction((t) => [...window.__engine.remoteRulers.values()][0]?.label.text === t, wpLabel, { timeout: 3000 }).catch(() => {})
const wpRemote = await pl.evaluate(() => [...window.__engine.remoteRulers.values()][0]?.label.text)
await gm.mouse.up()
check('a waypoint ruler measures out and back (3 + 3 cells)', wpLabel === '9 m' || wpLabel === '30 ft', wpLabel)
check('the other players see the same path', wpRemote === wpLabel, wpRemote)

// 52. Eraser: drag over a drawing deletes it
await gm.evaluate(() => (window.__store.tool = 'draw-line'))
const e0 = await toClient(gm, pg.s * 8, pg.s * 8)
const e1 = await toClient(gm, pg.s * 11, pg.s * 8)
await drag(gm, e0, e1)
await gm.waitForTimeout(300)
const lines = (await state(gm)).objects.filter((o) => o.kind === 'path' && o.props.shape === 'line').length
await gm.keyboard.press('e')
const em = await toClient(gm, pg.s * 9.5, pg.s * 7)
const em2 = await toClient(gm, pg.s * 9.5, pg.s * 9)
await drag(gm, em, em2)
await gm.waitForTimeout(500)
const linesAfter = (await state(gm)).objects.filter((o) => o.kind === 'path' && o.props.shape === 'line').length
check('the eraser deletes the drawing it crosses', linesAfter === lines - 1, JSON.stringify([lines, linesAfter]))
await gm.evaluate(() => (window.__store.tool = 'select'))

// 53. Map pins: the GM places one with notes, the player clicks it and reads them
await gm.getByRole('button', { name: 'Map pin' }).click()
const pinAt = await toClient(gm, pg.s * 14, pg.s * 4)
await gm.mouse.click(pinAt.x, pinAt.y)
const pinDialog = gm.getByRole('dialog', { name: 'Map pin' })
await pinDialog.waitFor({ timeout: 3000 })
await pinDialog.getByLabel('Title', { exact: true }).fill('Old mill')
await pinDialog.getByLabel('Notes (players see them)').fill('The miller owes 5 gp.')
await pinDialog.getByLabel('GM notes (hidden from players)').fill('He is a wererat.')
await pinDialog.getByRole('button', { name: 'Save' }).click()
await pl.waitForFunction(() => [...window.__store.objects.values()].some((o) => o.kind === 'pin' && o.props.title === 'Old mill'), null, { timeout: 3000 }).catch(() => {})
const plPin = (await state(pl)).objects.find((o) => o.kind === 'pin')
check('a map pin reaches the players without its GM notes', !!plPin && plPin.props.notes === 'The miller owes 5 gp.' && !plPin.props.gm_notes, JSON.stringify(plPin?.props))
const pp = await toClient(pl, plPin.x, plPin.y - 25 / (await pl.evaluate(() => window.__engine.zoom)))
await pl.mouse.click(pp.x, pp.y)
const pinNoteDialog = pl.getByRole('dialog', { name: 'Old mill' })
await pinNoteDialog.waitFor({ timeout: 3000 }).catch(() => {})
check('clicking a pin shows its notes', (await pinNoteDialog.textContent().catch(() => ''))?.includes('owes 5 gp'))
await pl.screenshot({ path: `${OUT}/pl-pin.png` })
await pl.keyboard.press('Escape')

// 55. A picture larger than the GPU allows is drawn in tiles (limit lowered for the test)
await gm.evaluate(() => window.__engine.limitTextureSize(128))
const bigUrl = libAssets.find((a) => a.name === 'cave').url
await gm.evaluate((url) => {
  const s = window.__store
  s.createObjects([{ id: 'big-map', page_id: s.page.id, kind: 'image', layer: 'map', x: 1400, y: 1400, width: 300, height: 200, rotation: 0, props: { image: url } }])
}, bigUrl)
await gm.waitForFunction(() => window.__engine.views.get('big-map')?.root.getChildByLabel('tiles', true)?.children.length > 0, null, { timeout: 4000 }).catch(() => {})
const tileCount = await gm.evaluate(() => window.__engine.views.get('big-map')?.root.getChildByLabel('tiles', true)?.children.length ?? 0)
check('a picture over the GPU limit is cut into tiles', tileCount === 6, String(tileCount))
await gm.evaluate(() => {
  window.__engine.limitTextureSize(16384)
  window.__store.deleteObjects(['big-map'])
})


// 56. Action bar: the player selects their token, presses 1 and clicks the goblin;
// the attack resolves on the server, both tabs get the card, and Undo takes it back.
await gm.evaluate((ariaId) => {
  const s = window.__store
  const sheet = (kind, extra) => ({ kind, abilities: { str: 16, dex: 14, con: 12, int: 10, wis: 10, cha: 10 }, hp: { current: 30, max: 30, temp: 0 }, ...extra })
  s.send({ type: 'char.create', id: 'ab-hero', character: { name: 'Bree', player_id: ariaId, sheet: sheet('pc', { attacks: [{ id: 'axe', name: 'Battleaxe', damage: '1d8', damage_type: 'slashing' }] }) } })
  s.send({ type: 'char.create', id: 'ab-gob', character: { name: 'Bar Goblin', sheet: sheet('npc', { ac: 5, hp: { current: 40, max: 40, temp: 0 } }) } })
}, ariaId)
await gm.waitForFunction(() => window.__store.characters.some((c) => c.id === 'ab-gob'), null, { timeout: 3000 })
await gm.evaluate((ariaId) => {
  const s = window.__store
  const t = (id, x, props) => ({ id, page_id: s.page.id, kind: 'token', layer: 'objects', x, y: 1645, width: 70, height: 70, rotation: 0, props })
  s.createObjects([
    t('ab-h', 1505, { name: 'Bree', represents: 'ab-hero', controlled_by: [ariaId] }),
    t('ab-g', 1575, { name: 'Bar Goblin', represents: 'ab-gob' }),
  ])
}, ariaId)
await pl.waitForFunction(() => window.__store.objects.has('ab-h') && window.__store.objects.has('ab-g'), null, { timeout: 4000 })
await pl.evaluate(() => window.__engine.centerOn(1540, 1645))
const heroAt = await toClient(pl, 1505, 1645)
await pl.mouse.click(heroAt.x, heroAt.y)
await pl.locator('.bar .slot').first().waitFor({ timeout: 3000 }).catch(() => {})
check('the action bar shows the attacks of my token', (await pl.locator('.bar .slot').first().textContent().catch(() => ''))?.includes('Battleaxe'))
await pl.keyboard.press('1')
check('pressing 1 starts target mode', await pl.evaluate(() => window.__store.targeting?.label === 'Battleaxe'))
await pl.screenshot({ path: `${OUT}/pl-targeting.png` })
const gobAt = await toClient(pl, 1575, 1645)
await pl.mouse.move(gobAt.x, gobAt.y)
await pl.mouse.click(gobAt.x, gobAt.y)
const cardSeen = (page) =>
  page.waitForFunction(() => window.__store.chat.some((m) => m.roll?.card?.action === 'Battleaxe'), null, { timeout: 4000 }).then(() => true, () => false)
check('clicking the goblin resolves the attack: the card reaches both tabs', (await cardSeen(pl)) && (await cardSeen(gm)))
const gobHp = () => gm.evaluate(() => window.__store.objects.get('ab-g')?.props.bar1?.value)
const hpAfter = await gobHp()
check('the hit is applied to the goblin', hpAfter < 40, String(hpAfter))
await pl.screenshot({ path: `${OUT}/pl-combat-card.png` })
await pl.locator('.card', { hasText: 'Battleaxe' }).last().getByRole('button', { name: 'Undo' }).click()
await gm.waitForFunction(() => window.__store.objects.get('ab-g')?.props.bar1?.value === 40, null, { timeout: 4000 }).catch(() => {})
check('Undo on the card gives the hit points back, for everyone', (await gobHp()) === 40)
check('…and the card shows it was undone', await pl.waitForFunction(() => !!window.__store.chat.findLast((m) => m.roll?.card?.action === 'Battleaxe')?.roll.card.undone_by, null, { timeout: 3000 }).then(() => true, () => false))
await gm.evaluate(() => window.__store.deleteObjects(['ab-h', 'ab-g']))

} catch (e) {
  results.push(`FAIL aborted: ${e.message.split('\n')[0]}`)
} finally {
  await gm?.screenshot({ path: `${OUT}/gm-final.png` })
  await pl?.screenshot({ path: `${OUT}/pl-final.png` })
  await browser.close()
  stopServers()
  report()
}
