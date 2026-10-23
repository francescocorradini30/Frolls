<script lang="ts">
  import { untrack } from 'svelte'
  import type { Bar, Layer, MapObject } from '../net/protocol'
  import { store } from '../state/game.svelte'
  import { BARS, DEFAULT_TOKEN_COLOR } from '../theme'
  import { STATUSES } from '../util/statuses'
  import type { StampResult, StoredStamp } from '../util/stamp'
  import { pickFile, pickFiles, uploadImage } from '../util/upload'
  import TokenStamp from './TokenStamp.svelte'

  let { obj, onClose }: { obj: MapObject; onClose: () => void } = $props()

  // The form edits a snapshot of the object taken when the dialog opens.
  const start = untrack(() => obj)
  const p = start.props

  let tab = $state<'base' | 'bars' | 'status' | 'sides'>('base')
  let name = $state<string>(p.name ?? '')
  let image = $state<string>(p.image ?? '')
  let stamp = $state<StoredStamp | null>(p.stamp ?? null)
  let color = $state<string>(p.color ?? DEFAULT_TOKEN_COLOR)
  let layer = $state<Layer>(start.layer)
  let controlledBy = $state<string[]>([...(p.controlled_by ?? [])])
  let gmNotes = $state<string>(p.gm_notes ?? '')
  let represents = $state<string>(p.represents ?? '')
  let bars = $state<Bar[]>(BARS.map((b) => ({ value: null, max: null, ...(p[b.key] ?? {}) })))
  let statuses = $state<string[]>([...(p.statuses ?? [])])
  // Multi-sided token: the pictures it can show (a card keeps its own two sides).
  let sides = $state<string[]>([...(p.sides ?? [])])
  const isCard = !!p.card
  let uploading = $state(false)
  // Picture being framed in the token stamp: a new file, or the original of the current image.
  let stamping = $state<{ source: File | string; initial: StoredStamp | null } | null>(null)

  const isToken = start.kind === 'token'
  const players = $derived(
    store.players.filter((pl) => !pl.is_gm).sort((a, b) => Number(b.online) - Number(a.online)),
  )

  const characters = $derived([...store.characters].sort((a, b) => a.name.localeCompare(b.name)))

  /** Linking a character: the token takes its name, its avatar if it has no picture,
   *  and its player as controller if nobody controls it yet. */
  function link(id: string) {
    represents = id
    const c = store.character(id)
    if (!c) return
    name = c.name
    if (!image && c.avatar) {
      image = c.avatar
      stamp = null
    }
    if (c.player_id && !controlledBy.length) controlledBy = [c.player_id]
  }

  function toggle(list: string[], id: string): string[] {
    return list.includes(id) ? list.filter((x) => x !== id) : [...list, id]
  }

  async function chooseImage() {
    const file = await pickFile()
    if (!file) return
    if (isToken) stamping = { source: file, initial: null }
    else await upload(file)
  }

  /** Frame the token again, starting from its original picture and previous settings. */
  function editImage() {
    stamping = { source: stamp?.source ?? image, initial: stamp }
  }

  function stamped(result: StampResult) {
    image = result.image
    stamp = result.stamp
    stamping = null
  }

  function removeImage() {
    image = ''
    stamp = null
  }

  async function upload(file: File) {
    uploading = true
    stamp = null
    try {
      image = await uploadImage(file)
    } catch (e) {
      store.toast((e as Error).message)
    } finally {
      uploading = false
    }
  }

  async function addSides() {
    const files = await pickFiles()
    if (!files.length) return
    uploading = true
    try {
      for (const f of files) sides = [...sides, await uploadImage(f)]
    } catch (e) {
      store.toast((e as Error).message)
    } finally {
      uploading = false
    }
  }

  function showSide(url: string) {
    image = url
    stamp = null
  }

  function moveSide(i: number, by: number) {
    const j = i + by
    if (j < 0 || j >= sides.length) return
    const next = [...sides]
    ;[next[i], next[j]] = [next[j], next[i]]
    sides = next
  }

  function num(v: unknown): number | null {
    if (v === null || v === undefined || v === '') return null
    const n = Number(v)
    return Number.isFinite(n) ? n : null
  }

  function save() {
    const props: Record<string, unknown> = {
      name: name.trim() || null,
      image: image || null,
      stamp: image && stamp ? $state.snapshot(stamp) : null,
      color,
      statuses: statuses.length ? statuses : null,
    }
    if (!isCard) {
      const side = sides.indexOf(image)
      props.sides = sides.length ? $state.snapshot(sides) : null
      props.side = side >= 0 ? side : null
    }
    bars.forEach((b, i) => {
      const value = num(b.value)
      const max = num(b.max)
      props[BARS[i].key] = value === null && max === null ? null : { value, max }
    })
    if (store.isGm) {
      props.controlled_by = controlledBy.length ? controlledBy : null
      props.gm_notes = gmNotes.trim() || null
      if (isToken) props.represents = represents || null
    }
    const patch: Parameters<typeof store.updateObjects>[0][0] = { id: obj.id, props }
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
        <button class:active={tab === 'status'} onclick={() => (tab = 'status')}>Statuses</button>
        {#if !isCard}<button class:active={tab === 'sides'} onclick={() => (tab = 'sides')}>Sides</button>{/if}
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
            {#if image && isToken}<button class="btn small" onclick={editImage}>Edit token</button>{/if}
            {#if image}<button class="btn small" onclick={removeImage}>Remove image</button>{/if}
            {#if !image}<label class="row"><input type="color" bind:value={color} /> color</label>{/if}
          </div>
        </div>

        <label class="field"><span>Name</span><input bind:value={name} maxlength="120" /></label>

        {#if store.isGm && isToken}
          <div class="field">
            <span>Represents character</span>
            <div class="row">
              <select value={represents} onchange={(e) => link(e.currentTarget.value)} aria-label="Represents character">
                <option value="">None</option>
                {#each characters as c (c.id)}<option value={c.id}>{c.name}{c.archived ? ' (archived)' : ''}</option>{/each}
              </select>
              {#if store.character(represents)}
                <button class="btn small" onclick={() => (store.openCharacterId = represents)}>Open journal</button>
              {/if}
            </div>
          </div>
        {:else if store.character(represents)}
          <button class="btn small journal-link" onclick={() => (store.openCharacterId = represents)}>Open character journal</button>
        {/if}

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
            <span class="swatch" style:background={BARS[i].color}></span>
            <strong>{BARS[i].label}</strong>
            <input type="number" placeholder="value" bind:value={bar.value} aria-label={`${BARS[i].label} value`} />
            <span>/</span>
            <input type="number" placeholder="max" bind:value={bar.max} aria-label={`${BARS[i].label} max`} />
          </div>
        {/each}
      {:else if tab === 'sides'}
        <p class="muted hint">
          A multi-sided token switches between these pictures: a coin, a door open or shut, a creature that
          changes shape. Right-click the token to pick a side or a random one.
        </p>
        <div class="sides">
          {#each sides as side, i (i)}
            <div class="side" class:current={side === image}>
              <button class="side-pic" title="Show this side" aria-label={`Show side ${i + 1}`} onclick={() => showSide(side)}
                style:background-image={`url(${side})`}></button>
              <div class="side-tools">
                <span>{i + 1}</span>
                <button class="icon-btn" aria-label="Move left" onclick={() => moveSide(i, -1)}>‹</button>
                <button class="icon-btn" aria-label="Move right" onclick={() => moveSide(i, 1)}>›</button>
                <button class="icon-btn" aria-label={`Remove side ${i + 1}`} onclick={() => (sides = sides.filter((_, k) => k !== i))}>✕</button>
              </div>
            </div>
          {/each}
        </div>
        <div class="row">
          <button class="btn small" onclick={addSides} disabled={uploading}>{uploading ? 'Uploading…' : 'Upload sides'}</button>
          {#if image && !sides.includes(image)}
            <button class="btn small" onclick={() => (sides = [...sides, image])}>Add current image</button>
          {/if}
        </div>
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

{#if stamping}
  <TokenStamp source={stamping.source} initial={stamping.initial} onDone={stamped} onCancel={() => (stamping = null)} />
{/if}

<style>
  .hint {
    margin: 0;
    font-size: 0.8rem;
  }
  .sides {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(92px, 1fr));
    gap: 8px;
  }
  .side {
    display: flex;
    flex-direction: column;
    gap: 2px;
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 4px;
  }
  .side.current {
    border-color: var(--accent);
    box-shadow: 0 0 0 1px var(--accent);
  }
  .side-pic {
    aspect-ratio: 1;
    border: none;
    border-radius: 6px;
    background: var(--surface-3) center / contain no-repeat;
    cursor: pointer;
  }
  .side-tools {
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-size: 0.75rem;
    color: var(--text-muted);
  }
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
  .row {
    display: flex;
    gap: 6px;
    align-items: center;
  }
  .row select {
    flex: 1;
    min-width: 0;
  }
  .journal-link {
    align-self: flex-start;
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
    width: 80px;
  }
  .bar-row input[type='number'] {
    width: 80px;
  }
  .swatch {
    width: 10px;
    height: 10px;
    border-radius: 2px;
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
