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
  import SelectionHud from './SelectionHud.svelte'
  import TokenEditor from './TokenEditor.svelte'
  import TokenStamp from './TokenStamp.svelte'

  let { zoom = $bindable(1) }: { zoom?: number } = $props()

  let host: HTMLElement
  let engine: Engine | null = null
  let menu = $state<{ x: number; y: number; id: string | null } | null>(null)
  let editing = $state<MapObject | null>(null)
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
    })
    e.mount(host).then(() => {
      if (disposed) {
        e.destroy()
        return
      }
      engine = e
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
    if (obj && store.controls(obj) && (obj.kind === 'token' || obj.kind === 'image')) editing = obj
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

  function onDrop(e: DragEvent) {
    e.preventDefault()
    dropActive = false
    if (!store.isGm || !engine) return
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

<div
  class="map"
  class:drop={dropActive}
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

{#if stamping}
  <TokenStamp source={stamping.file} onDone={endStamp} onCancel={() => endStamp(null)} />
{/if}

<style>
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
  .text-input {
    position: fixed;
    z-index: 30;
    min-width: 200px;
    transform: translateY(-50%);
  }
</style>
