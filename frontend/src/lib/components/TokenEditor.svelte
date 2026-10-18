<script lang="ts">
  import { untrack } from 'svelte'
  import type { Aura, Bar, Layer, MapObject } from '../net/protocol'
  import { store } from '../state/game.svelte'
  import { AURA_COLORS, BAR_COLORS, DEFAULT_TOKEN_COLOR } from '../theme'
  import { STATUSES } from '../util/statuses'
  import { pickFile, uploadImage } from '../util/upload'

  let { obj, onClose }: { obj: MapObject; onClose: () => void } = $props()

  // The form edits a snapshot of the object taken when the dialog opens.
  const start = untrack(() => obj)
  const gridSize = store.page?.grid_size ?? 70
  const p = start.props

  let tab = $state<'base' | 'bars' | 'auras' | 'status'>('base')
  let name = $state<string>(p.name ?? '')
  let showName = $state<boolean>(p.show_name !== false)
  let image = $state<string>(p.image ?? '')
  let color = $state<string>(p.color ?? DEFAULT_TOKEN_COLOR)
  let cellsW = $state(Math.round((start.width / gridSize) * 100) / 100)
  let cellsH = $state(Math.round((start.height / gridSize) * 100) / 100)
  let layer = $state<Layer>(start.layer)
  let controlledBy = $state<string[]>([...(p.controlled_by ?? [])])
  let gmNotes = $state<string>(p.gm_notes ?? '')
  let flipH = $state<boolean>(!!p.flip_h)
  let flipV = $state<boolean>(!!p.flip_v)
  let bars = $state<Bar[]>([0, 1, 2].map((i) => ({ value: null, max: null, ...(p[`bar${i + 1}`] ?? {}) })))
  let auras = $state<Aura[]>(
    [0, 1].map((i) => ({ radius: 0, color: AURA_COLORS[i], square: false, ...(p[`aura${i + 1}`] ?? {}) })),
  )
  let statuses = $state<string[]>([...(p.statuses ?? [])])
  let uploading = $state(false)

  const isToken = start.kind === 'token'
  const players = $derived(
    store.players.filter((pl) => !pl.is_gm).sort((a, b) => Number(b.online) - Number(a.online)),
  )

  function toggle(list: string[], id: string): string[] {
    return list.includes(id) ? list.filter((x) => x !== id) : [...list, id]
  }

  async function chooseImage() {
    const file = await pickFile()
    if (!file) return
    uploading = true
    try {
      image = await uploadImage(file)
    } catch (e) {
      store.toast((e as Error).message)
    } finally {
      uploading = false
    }
  }

  function num(v: unknown): number | null {
    if (v === null || v === undefined || v === '') return null
    const n = Number(v)
    return Number.isFinite(n) ? n : null
  }

  function save() {
    const props: Record<string, unknown> = {
      name: name.trim() || null,
      show_name: showName,
      image: image || null,
      color,
      flip_h: flipH || null,
      flip_v: flipV || null,
      statuses: statuses.length ? statuses : null,
    }
    bars.forEach((b, i) => {
      const value = num(b.value)
      const max = num(b.max)
      props[`bar${i + 1}`] = value === null && max === null ? null : { value, max }
    })
    auras.forEach((a, i) => {
      const radius = num(a.radius)
      props[`aura${i + 1}`] = radius ? { radius, color: a.color, square: a.square } : null
    })
    if (store.isGm) {
      props.controlled_by = controlledBy.length ? controlledBy : null
      props.gm_notes = gmNotes.trim() || null
    }
    const patch: Parameters<typeof store.updateObjects>[0][0] = {
      id: obj.id,
      width: Math.max(0.25, num(cellsW) ?? 1) * gridSize,
      height: Math.max(0.25, num(cellsH) ?? 1) * gridSize,
      props,
    }
    if (store.isGm && layer !== obj.layer) patch.layer = layer
    store.updateObjects([patch])
    onClose()
  }
</script>

<div class="backdrop" role="presentation" onclick={onClose}>
  <div
    class="dialog panel"
    role="dialog"
    aria-modal="true"
    aria-label="Token settings"
    tabindex="-1"
    onclick={(e) => e.stopPropagation()}
    onkeydown={(e) => e.key === 'Escape' && onClose()}
  >
    <header>
      <strong>{isToken ? 'Token' : 'Image'}: {name || 'unnamed'}</strong>
      <button class="icon-btn" aria-label="Close" onclick={onClose}>✕</button>
    </header>

    {#if isToken}
      <nav class="tabs">
        <button class:active={tab === 'base'} onclick={() => (tab = 'base')}>Details</button>
        <button class:active={tab === 'bars'} onclick={() => (tab = 'bars')}>Bars</button>
        <button class:active={tab === 'auras'} onclick={() => (tab = 'auras')}>Auras</button>
        <button class:active={tab === 'status'} onclick={() => (tab = 'status')}>Statuses</button>
      </nav>
    {/if}

    <div class="body">
      {#if tab === 'base'}
        <div class="preview-row">
          <div class="preview" style:background={image ? `center / contain no-repeat url(${image})` : color}></div>
          <div class="col">
            <button class="btn small" onclick={chooseImage} disabled={uploading}>
              {uploading ? 'Uploading…' : 'Upload image'}
            </button>
            {#if image}<button class="btn small" onclick={() => (image = '')}>Remove image</button>{/if}
            {#if !image}<label class="row"><input type="color" bind:value={color} /> color</label>{/if}
          </div>
        </div>

        <label class="field"><span>Name</span><input bind:value={name} maxlength="120" /></label>
        <label class="check"><input type="checkbox" bind:checked={showName} /> Show name on the map</label>

        <div class="grid2">
          <label class="field"><span>Width (cells)</span><input type="number" step="0.5" min="0.25" bind:value={cellsW} /></label>
          <label class="field"><span>Height (cells)</span><input type="number" step="0.5" min="0.25" bind:value={cellsH} /></label>
        </div>
        <div class="row">
          <label class="check"><input type="checkbox" bind:checked={flipH} /> Flip horizontal</label>
          <label class="check"><input type="checkbox" bind:checked={flipV} /> Flip vertical</label>
        </div>

        {#if store.isGm}
          <label class="field">
            <span>Layer</span>
            <select bind:value={layer}>
              <option value="map">Map</option>
              <option value="objects">Objects & Tokens</option>
              <option value="gm">GM (hidden from players)</option>
            </select>
          </label>

          {#if isToken}
            <div class="field">
              <span>Controlled by</span>
              <div class="chips">
                <button class="chip" class:on={controlledBy.includes('all')} onclick={() => (controlledBy = toggle(controlledBy, 'all'))}>
                  All players
                </button>
                {#each players as pl (pl.id)}
                  <button
                    class="chip"
                    class:on={controlledBy.includes(pl.id)}
                    class:offline={!pl.online}
                    data-player-id={pl.id}
                    title={pl.online ? 'Online' : 'Offline'}
                    onclick={() => (controlledBy = toggle(controlledBy, pl.id))}
                  >
                    <i style:background={pl.color}></i>{pl.name}
                  </button>
                {/each}
              </div>
            </div>
          {/if}

          <label class="field">
            <span>GM Notes (hidden from players)</span>
            <textarea rows="3" bind:value={gmNotes}></textarea>
          </label>
        {/if}
      {:else if tab === 'bars'}
        {#each bars as bar, i (i)}
          <div class="bar-row">
            <span class="swatch" style:background={BAR_COLORS[i]}></span>
            <strong>Bar {i + 1}</strong>
            <input type="number" placeholder="value" bind:value={bar.value} aria-label={`Bar ${i + 1} value`} />
            <span>/</span>
            <input type="number" placeholder="max" bind:value={bar.max} aria-label={`Bar ${i + 1} max`} />
          </div>
        {/each}
        <p class="muted hint">Usually: bar 1 = hit points, bar 2 = AC, bar 3 = other. Leave empty to hide.</p>
      {:else if tab === 'auras'}
        {#each auras as aura, i (i)}
          <div class="bar-row">
            <strong>Aura {i + 1}</strong>
            <input type="number" min="0" step="5" bind:value={aura.radius} aria-label={`Aura ${i + 1} radius`} />
            <span>{store.page?.scale_unit ?? 'ft'}</span>
            <input type="color" bind:value={aura.color} aria-label={`Aura ${i + 1} color`} />
            <label class="check"><input type="checkbox" bind:checked={aura.square} /> square</label>
          </div>
        {/each}
        <p class="muted hint">Radius starts at the token edge. 0 = no aura.</p>
      {:else}
        <div class="statuses">
          {#each STATUSES as s (s.id)}
            <button class="status" class:on={statuses.includes(s.id)} title={s.label} onclick={() => (statuses = toggle(statuses, s.id))}>
              <span>{s.icon}</span><small>{s.label}</small>
            </button>
          {/each}
        </div>
      {/if}
    </div>

    <footer>
      <button class="btn" onclick={onClose}>Cancel</button>
      <button class="btn primary" onclick={save}>Save</button>
    </footer>
  </div>
</div>

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    z-index: 100;
    display: grid;
    place-items: center;
    padding: 16px;
    background: var(--backdrop);
  }
  .dialog {
    width: min(520px, 100%);
    max-height: 90vh;
    display: flex;
    flex-direction: column;
  }
  header,
  footer {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 14px;
  }
  header {
    border-bottom: 1px solid var(--border);
    justify-content: space-between;
  }
  footer {
    border-top: 1px solid var(--border);
    justify-content: flex-end;
  }
  .tabs {
    display: flex;
    gap: 2px;
    padding: 6px 10px 0;
    border-bottom: 1px solid var(--border);
  }
  .tabs button {
    border: none;
    background: none;
    padding: 8px 12px;
    cursor: pointer;
    border-bottom: 2px solid transparent;
    color: var(--text-muted);
  }
  .tabs button.active {
    color: var(--text);
    border-bottom-color: var(--accent);
  }
  .body {
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding: 14px;
    overflow-y: auto;
  }
  .preview-row {
    display: flex;
    gap: 14px;
    align-items: center;
  }
  .preview {
    width: 72px;
    height: 72px;
    border-radius: 8px;
    border: 1px solid var(--border);
    flex-shrink: 0;
  }
  .col {
    display: flex;
    flex-direction: column;
    gap: 6px;
    align-items: flex-start;
  }
  .grid2 {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }
  .check {
    display: flex;
    gap: 6px;
    align-items: center;
    font-size: 0.85rem;
  }
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 5px 10px;
    border-radius: 999px;
    border: 1px solid var(--border);
    background: var(--surface-2);
    cursor: pointer;
  }
  .chip.on {
    border-color: var(--accent);
    background: color-mix(in srgb, var(--accent) 20%, var(--surface-2));
  }
  .chip.offline {
    opacity: 0.55;
  }
  .chip i {
    width: 9px;
    height: 9px;
    border-radius: 50%;
  }
  .bar-row {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .bar-row strong {
    width: 64px;
  }
  .bar-row input[type='number'] {
    width: 80px;
  }
  .bar-row input[type='color'] {
    width: 36px;
    height: 30px;
    padding: 2px;
  }
  .swatch {
    width: 10px;
    height: 10px;
    border-radius: 2px;
  }
  .hint {
    font-size: 0.8rem;
    margin: 0;
  }
  .statuses {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(96px, 1fr));
    gap: 6px;
  }
  .status {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    padding: 6px 4px;
    border-radius: 6px;
    border: 1px solid var(--border);
    background: var(--surface-2);
    cursor: pointer;
  }
  .status span {
    font-size: 1.3rem;
  }
  .status small {
    font-size: 0.7rem;
    color: var(--text-muted);
  }
  .status.on {
    border-color: var(--accent);
    background: color-mix(in srgb, var(--accent) 20%, var(--surface-2));
  }
</style>
