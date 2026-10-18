// End-to-end check of the game mechanics with two real browser tabs (GM + player).
// Needs the app running (`npm run dev`) and a local Chrome or Edge.
// Usage: npm run e2e            (headless)
//        HEADED=1 npm run e2e   (watch it)
import { existsSync, mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright-core'

const BASE = process.env.FROLLS_URL ?? 'http://localhost:5173/'
const OUT = fileURLToPath(new URL('./out', import.meta.url))
mkdirSync(OUT, { recursive: true })

const candidates = [
  process.env.CHROME_PATH,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  '/usr/bin/google-chrome',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
].filter(Boolean)
const executablePath = candidates.find((p) => existsSync(p))
if (!executablePath) throw new Error('Chrome/Edge non trovato: imposta CHROME_PATH')
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
  await page.getByPlaceholder('Es. Aria la Ranger').fill(name)
  if (gm) await page.getByRole('button', { name: 'Game Master' }).click()
  await page.getByRole('button', { name: 'Entra' }).click()
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

// Clean slate
await gm.evaluate(() => {
  const s = window.__store
  const ids = [...s.objects.keys()]
  if (ids.length) s.deleteObjects(ids)
  s.send({ type: 'turn.set', order: [], round: 0 })
})
await gm.waitForTimeout(400)
if (await gm.locator('div.tracker').isVisible()) await gm.locator('div.tracker').getByLabel('Chiudi').click()
pl = await tab('Aria', false)

// 1. GM creates token
await gm.getByTitle('Nuovo token').click()
await gm.waitForTimeout(400)
let g = await state(gm)
const tok = g.objects.find((o) => o.kind === 'token')
check('GM crea token', !!tok)
let p = await state(pl)
check('giocatore vede token', p.objects.some((o) => o.id === tok.id))

// 2. GM drags token ~3 cells right, snapped
const from = await toClient(gm, tok.x, tok.y)
const zoom = await gm.evaluate(() => window.__engine.zoom)
await drag(gm, from, { x: from.x + 70 * 3 * zoom + 5, y: from.y }, 12)
await gm.waitForTimeout(500)
g = await state(gm)
p = await state(pl)
const moved = g.objects.find((o) => o.id === tok.id)
const pMoved = p.objects.find((o) => o.id === tok.id)
check('drag sposta token con snap', moved.x === tok.x + 210, `x ${tok.x} -> ${moved.x}`)
check('giocatore riceve la posizione', pMoved.x === moved.x && pMoved.y === moved.y)

// 3. Player cannot drag uncontrolled token
const pc = await toClient(pl, moved.x, moved.y)
await drag(pl, pc, { x: pc.x + 100, y: pc.y })
await pl.waitForTimeout(400)
p = await state(pl)
check('giocatore NON muove token altrui', p.objects.find((o) => o.id === tok.id).x === moved.x)

// 4. GM gives control to Aria via editor (double click)
const ariaId = await pl.evaluate(() => window.__store.me.id)
const gc = await toClient(gm, moved.x, moved.y)
await gm.mouse.dblclick(gc.x, gc.y)
const dialog = gm.getByRole('dialog', { name: 'Impostazioni token' })
await dialog.waitFor()
await dialog.locator('label.field input').first().fill('Aria la Ranger')
await dialog.locator(`[data-player-id="${ariaId}"]`).click()
await dialog.getByRole('button', { name: 'Barre' }).click()
await dialog.getByLabel('Barra 1 valore').fill('22')
await dialog.getByLabel('Barra 1 massimo').fill('30')
await dialog.getByRole('button', { name: 'Aure' }).click()
await dialog.getByLabel('Aura 1 raggio').fill('10')
await dialog.getByRole('button', { name: 'Stati' }).click()
await dialog.getByTitle('Avvelenato').click()
await dialog.getByRole('button', { name: 'Salva' }).click()
await gm.waitForTimeout(500)
p = await state(pl)
const t2 = p.objects.find((o) => o.id === tok.id)
check(
  'editor: nome, controllo, barre, aura, stati',
  t2.props.name === 'Aria la Ranger' &&
    t2.props.controlled_by?.includes(ariaId) &&
    t2.props.bar1?.value === 22 &&
    t2.props.aura1?.radius === 10 &&
    t2.props.statuses?.includes('poisoned'),
  JSON.stringify(t2.props),
)

// 5. Player drags own token now
const pc2 = await toClient(pl, t2.x, t2.y)
const pz = await pl.evaluate(() => window.__engine.zoom)
await drag(pl, pc2, { x: pc2.x, y: pc2.y + 70 * 2 * pz + 4 })
await pl.waitForTimeout(500)
g = await state(gm)
check('giocatore muove il proprio token', g.objects.find((o) => o.id === tok.id).y === t2.y + 140)

// 6. Player HUD relative bar change -5
await pl.evaluate((id) => window.__store.setSelection([id]), tok.id)
await pl.waitForTimeout(200)
const hpInput = pl.locator('.hud .bar input').first()
await hpInput.fill('-5')
await hpInput.press('Enter')
await pl.waitForTimeout(400)
g = await state(gm)
check('HUD: barra relativa -5', g.objects.find((o) => o.id === tok.id).props.bar1.value === 17)

// 7. GM layer secret token
await gm.getByTitle(/Livello GM/).click()
await gm.getByTitle('Nuovo token').click()
await gm.waitForTimeout(400)
g = await state(gm)
p = await state(pl)
const secret = g.objects.find((o) => o.layer === 'gm')
check('token su livello GM invisibile ai giocatori', !!secret && !p.objects.some((o) => o.id === secret.id))
await gm.getByTitle(/Livello oggetti/).click()

// 8. Player draws rectangle
await pl.evaluate(() => (window.__store.tool = 'draw-rect'))
await drag(pl, await toClient(pl, 100, 100), await toClient(pl, 300, 250))
await pl.waitForTimeout(400)
g = await state(gm)
check('giocatore disegna un rettangolo', g.objects.some((o) => o.kind === 'path' && o.props.shape === 'rect'))

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
check('disegno a mano libera', !!free && free.props.points.length > 10)

// 10. Template cone 15ft
await pl.evaluate(() => (window.__store.tool = 'template-cone'))
const c1 = await toClient(pl, 700, 700)
const c2 = await toClient(pl, 910, 700)
await pl.mouse.move(c1.x, c1.y)
await pl.mouse.down()
await pl.mouse.move(c2.x, c2.y, { steps: 6 })
await pl.screenshot({ path: `${OUT}/template-drag.png` })
await pl.mouse.up()
await pl.waitForTimeout(400)
g = await state(gm)
const cone = g.objects.find((o) => o.kind === 'template')
check('area cono creata (~15ft)', !!cone && Math.abs(cone.props.size - 210) < 2, cone && `size ${cone.props.size}`)

// 11. Ruler (screenshot)
await pl.evaluate(() => (window.__store.tool = 'ruler'))
const r1 = await toClient(pl, 105, 525)
const r2 = await toClient(pl, 105 + 280, 525 + 210)
await pl.mouse.move(r1.x, r1.y)
await pl.mouse.down()
await pl.mouse.move(r2.x, r2.y, { steps: 6 })
await pl.screenshot({ path: `${OUT}/ruler.png` })
await pl.mouse.up()
await pl.evaluate(() => (window.__store.tool = 'select'))

// 12. Text tool (GM)
await gm.evaluate(() => (window.__store.tool = 'text'))
const tp = await toClient(gm, 900, 200)
await gm.mouse.click(tp.x, tp.y)
await gm.locator('.text-input').fill('Taverna del Drago')
await gm.locator('.text-input').press('Enter')
await gm.waitForTimeout(400)
p = await state(pl)
check('testo sulla mappa', p.objects.some((o) => o.kind === 'text' && o.props.text === 'Taverna del Drago'))
await gm.evaluate(() => (window.__store.tool = 'select'))

// 13. Turn order
await gm.evaluate((id) => window.__store.setSelection([id]), tok.id)
if (!(await gm.locator('div.tracker').isVisible())) await gm.locator('button.tracker').click()
await gm.getByRole('button', { name: 'Aggiungi selezionati' }).click({ timeout: 4000 })
await gm.waitForTimeout(500)
p = await state(pl)
check('iniziativa: voce aggiunta', p.game.turn_order.length === 1)
check('tracker si apre da solo al giocatore', await pl.locator('div.tracker').isVisible())

// 14. Context menu: right click on token -> to GM layer hides from player
const rc = await toClient(gm, g.objects.find((o) => o.id === tok.id).x, g.objects.find((o) => o.id === tok.id).y)
await gm.mouse.click(rc.x, rc.y, { button: 'right' })
await gm.getByRole('menu').getByRole('button', { name: /GM$/ }).click()
await gm.waitForTimeout(400)
p = await state(pl)
check('menu contestuale: sposta su livello GM', !p.objects.some((o) => o.id === tok.id))
check('voce iniziativa nascosta ai giocatori se token su GM', p.game.turn_order.length === 0)
await gm.evaluate((id) => window.__store.updateObjects([{ id, layer: 'objects' }]), tok.id)
await gm.waitForTimeout(300)

// 15. Whisper
await pl.getByLabel('Messaggio chat').fill('/w gm ho un piano segreto')
await pl.keyboard.press('Enter')
await gm.waitForTimeout(400)
check('sussurro al GM', (await gm.locator('.log').innerText()).includes('ho un piano segreto'))

// 16. New page + move players
await gm.getByTitle('Nuova pagina').click()
await gm.waitForTimeout(400)
const pages = await gm.evaluate(() => window.__store.pages.map((x) => ({ id: x.id, name: x.name })))
const newPage = pages[pages.length - 1]
await gm.locator('.tab', { hasText: newPage.name }).locator('.tab-menu').click()
await gm.getByRole('button', { name: 'Sposta qui tutti i giocatori' }).click()
await pl.waitForTimeout(500)
p = await state(pl)
check('giocatore spostato sulla nuova pagina', p.page.id === newPage.id)
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
  'dopo reload: stessa identità e stato salvato',
  p.objects.some((o) => o.id === tok.id) && p.players.filter((x) => x.id === ariaId).length === 1,
)

// 18. Zoom wheel
const before = await gm.evaluate(() => window.__engine.zoom)
await gm.mouse.move(600, 400)
await gm.mouse.wheel(0, -300)
await gm.waitForTimeout(200)
check('zoom con rotellina', (await gm.evaluate(() => window.__engine.zoom)) > before)
await gm.evaluate(() => window.__engine.fitPage())

} catch (e) {
  results.push(`FAIL interrotto: ${e.message.split('\n')[0]}`)
} finally {
  await gm?.screenshot({ path: `${OUT}/gm-final.png` })
  await pl?.screenshot({ path: `${OUT}/pl-final.png` })
  console.log(results.join('\n'))
  if (errors.length) console.log('Errori JavaScript:', errors)
  await browser.close()
  const failed = results.filter((r) => r.startsWith('FAIL')).length
  console.log(`\n${results.length - failed}/${results.length} controlli superati. Screenshot in ${OUT}`)
  process.exitCode = failed || errors.length ? 1 : 0
}
