<script lang="ts">
  import { onMount } from 'svelte'
  import { Engine } from '../canvas/Engine'
  import { snapCenter, type Point } from '../canvas/grid'
  import type { MapObject } from '../net/protocol'
  import { TOKEN_COLORS } from '../theme'
  import { store } from '../state/game.svelte'
  import { uid } from '../util/ids'
  import type { StampResult } from '../util/stamp'
  import { imageSize, pickFile, uploadImage } from '../util/upload'
  import ContextMenu from './ContextMenu.svelte'
  import HandBar from './HandBar.svelte'
  import PinEditor from './PinEditor.svelte'
  import QuickBar from './QuickBar.svelte'
  import SelectionHud from './SelectionHud.svelte'
  import TokenEditor from './TokenEditor.svelte'
  import TokenStamp from './TokenStamp.svelte'

  let { zoom = $bindable(1) }: { zoom?: number } = $props()

  let host: HTMLElement
  let engine: Engine | null = null
  let menu = $state<{ x: number; y: number; id: string | null } | null>(null)
  let editing = $state<MapObject | null>(null)
  let editingPin = $state<MapObject | null>(null)
  // Pin whose notes are shown, and where (client pixels).
  let pinNote = $state<{ id: string; x: number; y: number } | null>(null)
  const pinShown = $derived.by(() => {
    void store.objectsVersion
    return pinNote ? store.objects.get(pinNote.id) : undefined
  })
  let textInput = $state<{ world: Point; x: number; y: number; value: string } | null>(null)
  let dropActive = $state(false)
  let stamping = $state<{ file: File; resolve: (result: StampResult | null) => void } | null>(null)

  /** Let the user frame a picture as a token; null if they cancel. */
  function stampFile(file: File): Promise<StampResult | null> {
    return new Promise((resolve) => (stamping = { file, resolve }))
  }

  function endStamp(result: StampResult | null) {
    stamping?.resolve(result)
    stamping = null
  }

  onMount(() => {
    let disposed = false
    const e = new Engine(store, {
      onEdit: (id) => openEditor(id),
      onContext: (id, x, y) => (menu = { x, y, id }),
      onTextRequest: (world, x, y) => (textInput = { world, x, y, value: '' }),
      onZoom: (z) => (zoom = z),
      onPin: (id, x, y) => (pinNote = { id, x, y }),
    })
    e.mount(host).then(() => {
      if (disposed) {
        e.destroy()
        return
      }
      engine = e
      store.viewCenter = () => e.viewCenter()
      if (import.meta.env.DEV) Object.assign(window, { __engine: e, __store: store })
    })
    return () => {
      disposed = true
      engine?.destroy()
      engine = null
    }
  })

  function openEditor(id: string) {
    const obj = store.objects.get(id)
    if (!obj || !store.controls(obj)) return
    if (obj.kind === 'pin') {
      pinNote = null
      editingPin = obj
    } else if (obj.kind === 'token' || obj.kind === 'image') editing = obj
  }

  export function zoomBy(factor: number) {
    engine?.zoomBy(factor)
  }

  export function fit() {
    engine?.fitPage()
  }

  export function addToken() {
    const page = store.page
    if (!engine || !page) return
    const center = snapCenter(page, engine.viewCenter(), page.grid_size, page.grid_size)
    const n = [...store.objects.values()].filter((o) => o.kind === 'token').length + 1
    const id = uid()
    store.createObjects([
      {
        id,
        page_id: page.id,
        kind: 'token',
        layer: store.layer === 'map' ? 'objects' : store.layer,
        x: center.x,
        y: center.y,
        width: page.grid_size,
        height: page.grid_size,
        rotation: 0,
        props: { name: `Token ${n}`, color: randomColor(), bar1: { value: 10, max: 10 } },
      },
    ])
    store.setSelection([id])
  }

  export async function uploadAndPlace(file?: File, at?: Point) {
    const page = store.page
    if (!engine || !page) return
    const picked = file ?? (await pickFile())
    if (!picked) return
    const isMap = store.layer === 'map'
    try {
      // Tokens are framed first (the dialog uploads them); maps go up untouched.
      const framed = isMap ? { image: await uploadImage(picked), stamp: null } : await stampFile(picked)
      if (!framed) return
      const url = framed.image
      const size = await imageSize(url).catch(() => ({ w: page.grid_size, h: page.grid_size }))
      const point = at ?? engine.viewCenter()
      // Maps keep their natural size; tokens fit one cell.
      const scale = isMap ? 1 : page.grid_size / Math.max(size.w, size.h)
      const w = Math.max(1, size.w * scale)
      const h = Math.max(1, size.h * scale)
      const pos = page.snap && !isMap ? snapCenter(page, point, w, h) : point
      const name = picked.name.replace(/\.[^.]+$/, '')
      store.createObjects([
        {
          id: uid(),
          page_id: page.id,
          kind: isMap ? 'image' : 'token',
          layer: store.layer,
          x: pos.x,
          y: pos.y,
          width: w,
          height: h,
          rotation: 0,
          props: isMap
            ? { image: url, name }
            : { image: url, name, show_name: true, ...(framed.stamp && { stamp: framed.stamp }) },
        },
      ])
    } catch (e) {
      store.toast((e as Error).message)
    }
  }

  /** Token for a journal character dropped on the map: linked, named and pictured after it. */
  function placeCharacter(id: string, at: Point) {
    const page = store.page
    const c = store.character(id)
    if (!page || !c) return
    // 5e size: Large = 2×2 cells, Tiny = half a cell…
    const cells = { tiny: 0.5, small: 1, medium: 1, large: 2, huge: 3, gargantuan: 4 }[c.sheet?.size ?? 'medium']
    const side = page.grid_size * cells
    const pos = page.snap ? snapCenter(page, at, side, side) : at
    const tokenId = uid()
    store.createObjects([
      {
        id: tokenId,
        page_id: page.id,
        kind: 'token',
        layer: store.layer === 'map' ? 'objects' : store.layer,
        x: pos.x,
        y: pos.y,
        width: side,
        height: side,
        rotation: 0,
        props: {
          name: c.name,
          show_name: true,
          represents: c.id,
          ...(c.avatar ? { image: c.avatar } : { color: randomColor() }),
          ...(c.player_id && { controlled_by: [c.player_id] }),
        },
      },
    ])
    store.setSelection([tokenId])
  }

  /** A picture from the art library: a map image on the map layer, otherwise a one-cell token.
   *  Library pictures are already prepared, so no stamp dialog. */
  function placeAsset(data: { url: string; name: string; width: number; height: number }, at: Point) {
    const page = store.page
    if (!page) return
    const isMap = store.layer === 'map'
    const w0 = data.width || page.grid_size
    const h0 = data.height || page.grid_size
    const scale = isMap ? 1 : page.grid_size / Math.max(w0, h0)
    const w = Math.max(1, w0 * scale)
    const h = Math.max(1, h0 * scale)
    const pos = page.snap && !isMap ? snapCenter(page, at, w, h) : at
    const id = uid()
    store.createObjects([
      {
        id,
        page_id: page.id,
        kind: isMap ? 'image' : 'token',
        layer: store.layer,
        x: pos.x,
        y: pos.y,
        width: w,
        height: h,
        rotation: 0,
        props: isMap ? { image: data.url, name: data.name } : { image: data.url, name: data.name, show_name: true },
      },
    ])
    store.setSelection([id])
  }

  /** A rollable table dropped on the map: a multi-sided token with its items' pictures. */
  function placeTable(tableId: string, at: Point) {
    const page = store.page
    const table = store.tables.find((t) => t.id === tableId)
    if (!page || !table) return
    const sides = table.items.map((i) => i.image).filter((u): u is string => !!u)
    if (!sides.length) {
      store.toast(`"${table.name}" has no pictures: add images to its items first`)
      return
    }
    const pos = page.snap ? snapCenter(page, at, page.grid_size, page.grid_size) : at
    const id = uid()
    store.createObjects([
      {
        id,
        page_id: page.id,
        kind: 'token',
        layer: store.layer === 'map' ? 'objects' : store.layer,
        x: pos.x,
        y: pos.y,
        width: page.grid_size,
        height: page.grid_size,
        rotation: 0,
        props: { name: table.name, image: sides[0], sides, side: 0 },
      },
    ])
    store.setSelection([id])
  }

  function onDrop(e: DragEvent) {
    e.preventDefault()
    dropActive = false
    if (!engine) return
    // Cards from my hand: anyone may play them.
    const card = e.dataTransfer?.getData('application/x-frolls-card')
    if (card) {
      const { deck_id, card_id, face_down } = JSON.parse(card)
      const at = engine.clientToWorld(e.clientX, e.clientY)
      store.deckAction(deck_id, 'play', { card_ids: [card_id], x: at.x, y: at.y, face_down })
      return
    }
    if (!store.isGm) return
    const asset = e.dataTransfer?.getData('application/x-frolls-asset')
    if (asset) {
      placeAsset(JSON.parse(asset), engine.clientToWorld(e.clientX, e.clientY))
      return
    }
    const tableId = e.dataTransfer?.getData('application/x-frolls-table')
    if (tableId) {
      placeTable(tableId, engine.clientToWorld(e.clientX, e.clientY))
      return
    }
    const monster = e.dataTransfer?.getData('application/x-frolls-monster')
    if (monster) {
      const at = engine.clientToWorld(e.clientX, e.clientY)
      const page = store.page
      const pos = page?.snap ? snapCenter(page, at, page.grid_size, page.grid_size) : at
      store.placeMonster(monster, pos.x, pos.y)
      return
    }
    const characterId = e.dataTransfer?.getData('application/x-frolls-character')
    if (characterId) {
      placeCharacter(characterId, engine.clientToWorld(e.clientX, e.clientY))
      return
    }
    const files = [...(e.dataTransfer?.files ?? [])].filter((f) => f.type.startsWith('image/'))
    const at = engine.clientToWorld(e.clientX, e.clientY)
    // One after the other, so each token gets its own stamp dialog.
    files.reduce<Promise<void>>(
      (prev, f, i) => prev.then(() => uploadAndPlace(f, { x: at.x + i * 20, y: at.y + i * 20 })),
      Promise.resolve(),
    )
  }

  function commitText() {
    if (textInput && engine) engine.createText(textInput.world, textInput.value)
    textInput = null
  }

  function randomColor() {
    return TOKEN_COLORS[Math.floor(Math.random() * TOKEN_COLORS.length)]
  }
</script>

<svelte:window onkeydown={(e) => e.key === 'Escape' && (pinNote = null)} />

<div
  class="map"
  class:drop={dropActive}
  class:picking={!!store.targetPick || store.pickingSheetTarget}
  role="application"
  aria-label="Game map"
  ondragenter={(e) => {
    if (store.isGm && e.dataTransfer?.types.includes('Files')) dropActive = true
  }}
  ondragleave={(e) => {
    if (e.currentTarget === e.target) dropActive = false
  }}
  ondragover={(e) => e.preventDefault()}
  ondrop={onDrop}
>
  <div class="canvas-host" bind:this={host}></div>

  <SelectionHud onEdit={openEditor} />

  {#if pinNote && pinShown}
    <div
      class="pin-note panel"
      role="dialog"
      aria-label={pinShown.props.title || 'Map pin'}
      style:left="{Math.min(pinNote.x + 12, window.innerWidth - 300)}px"
      style:top="{Math.min(pinNote.y, window.innerHeight - 220)}px"
    >
      <header>
        <strong>{pinShown.props.icon ?? '📍'} {pinShown.props.title || 'Map pin'}</strong>
        <button class="icon-btn" aria-label="Close" onclick={() => (pinNote = null)}>✕</button>
      </header>
      {#if pinShown.props.notes}<p class="notes">{pinShown.props.notes}</p>{/if}
      {#if store.isGm && pinShown.props.gm_notes}<p class="notes gm">{pinShown.props.gm_notes}</p>{/if}
      {#if !pinShown.props.notes && !(store.isGm && pinShown.props.gm_notes)}<p class="muted notes">No notes.</p>{/if}
      {#if store.isGm}<button class="btn small" onclick={() => openEditor(pinShown.id)}>Edit pin</button>{/if}
    </div>
  {/if}
  <QuickBar />
  <HandBar />

  {#if textInput}
    <!-- svelte-ignore a11y_autofocus -->
    <input
      class="text-input"
      style:left="{textInput.x}px"
      style:top="{textInput.y}px"
      bind:value={textInput.value}
      autofocus
      placeholder="Type and press Enter"
      onkeydown={(e) => {
        if (e.key === 'Enter') commitText()
        if (e.key === 'Escape') textInput = null
      }}
      onblur={commitText}
    />
  {/if}
</div>

{#if menu}
  <ContextMenu
    x={menu.x}
    y={menu.y}
    objectId={menu.id}
    onEdit={openEditor}
    onDuplicate={() => engine?.duplicateSelection()}
    onClose={() => (menu = null)}
  />
{/if}

{#if editing}
  <TokenEditor obj={editing} onClose={() => (editing = null)} />
{/if}

{#if editingPin}
  <PinEditor obj={editingPin} onClose={() => (editingPin = null)} />
{/if}

{#if stamping}
  <TokenStamp source={stamping.file} onDone={endStamp} onCancel={() => endStamp(null)} />
{/if}

<style>
  .map.picking :global(canvas) {
    cursor: crosshair !important;
  }
  .map {
    position: relative;
    flex: 1;
    min-width: 0;
    min-height: 0;
    overflow: hidden;
  }
  .map.drop::after {
    content: 'Drop to upload the image';
    position: absolute;
    inset: 12px;
    display: grid;
    place-items: center;
    border: 3px dashed var(--accent);
    border-radius: 12px;
    background: var(--backdrop);
    font-size: 1.2rem;
    font-weight: 700;
    pointer-events: none;
  }
  .canvas-host {
    position: absolute;
    inset: 0;
  }
  .canvas-host :global(canvas) {
    display: block;
    touch-action: none;
  }
  .pin-note {
    position: fixed;
    z-index: 40;
    width: 280px;
    max-height: 60vh;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 10px 12px;
  }
  .pin-note header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }
  .notes {
    margin: 0;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    font-size: 0.85rem;
  }
  .notes.gm {
    border-left: 3px solid var(--gm);
    padding-left: 8px;
    color: var(--text-muted);
  }
  .text-input {
    position: fixed;
    z-index: 30;
    min-width: 200px;
    transform: translateY(-50%);
  }
</style>
