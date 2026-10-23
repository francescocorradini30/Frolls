// Shared setup of the browser tests: an isolated backend (port 8001, database frolls_e2e
// wiped on every run) and frontend (port 5174), a local Chrome or Edge, tabs that join the
// game, and helpers. It never touches the dev game.
import { execFileSync, spawn } from 'node:child_process'
import { existsSync, mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright-core'

export const API_PORT = 8001
export const WEB_PORT = Number(process.env.WEB_PORT ?? 5174)
export const BASE = `http://localhost:${WEB_PORT}/`
export const OUT = fileURLToPath(new URL('./out', import.meta.url))
const BACKEND = fileURLToPath(new URL('../backend', import.meta.url))
const FRONTEND = fileURLToPath(new URL('../frontend', import.meta.url))
const PYTHON = `${BACKEND}/.venv/Scripts/python.exe`
mkdirSync(OUT, { recursive: true })

export const errors = []
export const results = []
export const check = (name, ok, extra = '') => results.push(`${ok ? 'OK  ' : 'FAIL'} ${name} ${ok ? '' : extra}`)

async function waitFor(url) {
  for (let i = 0; i < 100; i++) {
    try {
      if ((await fetch(url)).ok) return
    } catch {}
    await new Promise((r) => setTimeout(r, 200))
  }
  throw new Error(`${url} is not responding`)
}

/** Start the isolated servers on an empty database; returns a stop function. */
export async function startServers() {
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
    FROLLS_DEV_LOGIN: 'true',
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
  const stop = () => servers.forEach((s) => s.kill())
  process.on('exit', stop)
  await waitFor(`http://localhost:${API_PORT}/health`)
  await waitFor(BASE)
  return stop
}

export async function launchBrowser(args = []) {
  const candidates = [
    process.env.CHROME_PATH,
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    '/usr/bin/google-chrome',
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  ].filter(Boolean)
  const executablePath = candidates.find((p) => existsSync(p))
  if (!executablePath) throw new Error('Chrome/Edge not found: set CHROME_PATH')
  return chromium.launch({ executablePath, headless: !process.env.HEADED, args })
}

/** A new browser tab (own context, so its own player) that joins the game. */
export async function tab(browser, name, gm) {
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

export const state = (page) =>
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
export const toClient = (page, x, y) => page.evaluate(([x, y]) => window.__engine.worldToClient(x, y), [x, y])
export const drag = async (page, a, b, steps = 8) => {
  await page.mouse.move(a.x, a.y)
  await page.mouse.down()
  await page.mouse.move(b.x, b.y, { steps })
  await page.mouse.up()
}

/** Print the results and set the exit code. */
export function report() {
  console.log(results.join('\n'))
  if (errors.length) console.log('JavaScript errors:', errors)
  const failed = results.filter((r) => r.startsWith('FAIL')).length
  console.log(`\n${results.length - failed}/${results.length} checks passed. Screenshots in ${OUT}`)
  process.exitCode = failed || errors.length ? 1 : 0
}
