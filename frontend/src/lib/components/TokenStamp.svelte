<script lang="ts">
  import { onDestroy, onMount, untrack } from 'svelte'
  import { store } from '../state/game.svelte'
  import { palette, STAMP_BORDER_COLORS } from '../theme'
  import {
    drawStamp,
    exportStamp,
    loadImage,
    STAMP_SIZE,
    type StampBorder,
    type StampOptions,
    type StampResult,
  } from '../util/stamp'
  import { uploadImage } from '../util/upload'

  let {
    source,
    initial,
    onDone,
    onCancel,
  }: {
    /** A picture just picked (uploaded on confirm) or the URL of an original already uploaded. */
    source: File | string
    /** Settings of a previous framing, to edit it. */
    initial?: StampOptions | null
    onDone: (result: StampResult) => void
    onCancel: () => void
  } = $props()

  const VIEW_PX = 340
  // The token fills this share of the preview; the rest shows the picture around it.
  const TOKEN_SHARE = 0.74
  const BORDERS: { value: StampBorder; label: string }[] = [
    { value: 'none', label: 'None' },
    { value: 'thin', label: 'Thin' },
    { value: 'solid', label: 'Solid' },
    { value: 'double', label: 'Double' },
    { value: 'bevel', label: 'Bevel' },
  ]

  const DEFAULTS: StampOptions = {
    border: 'none',
    borderColor: STAMP_BORDER_COLORS[0],
    background: null,
    x: 0,
    y: 0,
    zoom: 1,
    rotation: 0,
  }

  // The dialog is mounted for one picture: reading the props once is intended.
  const src = untrack(() => source)
  let opts = $state<StampOptions>({ ...DEFAULTS, ...untrack(() => initial) })
  let backgroundColor = $state<string>(palette.ink800)
  let img = $state<HTMLImageElement | null>(null)
  let busy = $state(false)
  let canvas: HTMLCanvasElement
  let drag: { x: number; y: number; ox: number; oy: number } | null = null
  const url = typeof src === 'string' ? src : URL.createObjectURL(src)
  const dpr = window.devicePixelRatio || 1

  onMount(() => {
    loadImage(url).then(
      (i) => (img = i),
      (e: Error) => {
        store.toast(e.message)
        onCancel()
      },
    )
  })
  onDestroy(() => {
    if (typeof src !== 'string') URL.revokeObjectURL(url)
  })

  $effect(() => {
    if (!img || !canvas) return
    const view = Math.round(VIEW_PX * dpr)
    canvas.width = canvas.height = view
    drawStamp(canvas.getContext('2d')!, img, opts, { size: view * TOKEN_SHARE, view, preview: true })
  })

  /** Preview CSS pixels -> output pixels. */
  const toOutput = (px: number) => px / ((VIEW_PX * TOKEN_SHARE) / STAMP_SIZE)

  function onPointerDown(e: PointerEvent) {
    canvas.setPointerCapture(e.pointerId)
    drag = { x: e.clientX, y: e.clientY, ox: opts.x, oy: opts.y }
  }

  function onPointerMove(e: PointerEvent) {
    if (!drag) return
    opts.x = drag.ox + toOutput(e.clientX - drag.x)
    opts.y = drag.oy + toOutput(e.clientY - drag.y)
  }

  function onWheel(e: WheelEvent) {
    e.preventDefault()
    opts.zoom = clampZoom(opts.zoom * Math.exp(-e.deltaY * 0.0015))
  }

  const clampZoom = (z: number) => Math.min(6, Math.max(0.2, z))

  function reset() {
    opts = { ...opts, x: 0, y: 0, zoom: 1, rotation: 0 }
  }

  /** URL of the original picture, uploading it if it is a new file. */
  const original = (): Promise<string> => (typeof src === 'string' ? Promise.resolve(src) : uploadImage(src))

  async function finish(framed: boolean) {
    if (!img || busy) return
    busy = true
    try {
      const sourceUrl = await original()
      if (!framed) {
        onDone({ image: sourceUrl, stamp: null })
        return
      }
      const options = $state.snapshot(opts)
      const name = typeof src === 'string' ? 'token' : src.name
      const image = await uploadImage(await exportStamp(img, options, name))
      onDone({ image, stamp: { ...options, source: sourceUrl } })
    } catch (e) {
      store.toast((e as Error).message)
    } finally {
      busy = false
    }
  }
</script>

<div class="backdrop" role="presentation" onclick={onCancel}>
  <div
    class="dialog panel"
    role="dialog"
    aria-modal="true"
    aria-label="Token stamp"
    tabindex="-1"
    onclick={(e) => e.stopPropagation()}
    onkeydown={(e) => {
      e.stopPropagation()
      if (e.key === 'Escape') onCancel()
    }}
  >
    <header>
      <strong>Frame your token</strong>
      <button class="icon-btn" aria-label="Close" onclick={onCancel}>✕</button>
    </header>

    <div class="body">
      <div class="stage">
        <canvas
          bind:this={canvas}
          style:width="{VIEW_PX}px"
          style:height="{VIEW_PX}px"
          aria-label="Token preview: drag to move the picture, scroll to zoom"
          onpointerdown={onPointerDown}
          onpointermove={onPointerMove}
          onpointerup={() => (drag = null)}
          onpointercancel={() => (drag = null)}
          onwheel={onWheel}
        ></canvas>
        <p class="muted hint">Drag to move · scroll to zoom</p>
      </div>

      <div class="controls">
        <label class="field">
          <span>Zoom</span>
          <input type="range" min="0.2" max="6" step="0.01" bind:value={opts.zoom} aria-label="Zoom" />
        </label>
        <label class="field">
          <span>Rotation: {Math.round(opts.rotation)}°</span>
          <input
            type="range"
            min="-180"
            max="180"
            step="1"
            bind:value={opts.rotation}
            ondblclick={() => (opts.rotation = 0)}
            title="Double click to reset"
            aria-label="Rotation"
          />
        </label>
        <button type="button" class="btn small" onclick={reset}>Reset position</button>

        <div class="field">
          <span>Border</span>
          <div class="segmented">
            {#each BORDERS as b (b.value)}
              <button type="button" class:on={opts.border === b.value} onclick={() => (opts.border = b.value)}>{b.label}</button>
            {/each}
          </div>
        </div>

        {#if opts.border !== 'none'}
          <div class="field">
            <span>Border color</span>
            <div class="swatches">
              {#each STAMP_BORDER_COLORS as c (c)}
                <button
                  type="button"
                  class="swatch"
                  class:active={opts.borderColor === c}
                  style:background={c}
                  aria-label={`Border color ${c}`}
                  onclick={() => (opts.borderColor = c)}
                ></button>
              {/each}
              <input type="color" bind:value={opts.borderColor} aria-label="Custom border color" />
            </div>
          </div>
        {/if}

        <div class="field">
          <span>Background</span>
          <div class="row">
            <label class="check">
              <input
                type="checkbox"
                checked={opts.background !== null}
                onchange={(e) => (opts.background = e.currentTarget.checked ? backgroundColor : null)}
              />
              Fill behind the picture
            </label>
            {#if opts.background !== null}
              <input
                type="color"
                bind:value={backgroundColor}
                oninput={(e) => (opts.background = e.currentTarget.value)}
                aria-label="Background color"
              />
            {/if}
          </div>
        </div>
      </div>
    </div>

    <footer>
      <button class="btn" onclick={onCancel}>Cancel</button>
      <button class="btn" onclick={() => finish(false)} disabled={!img || busy} title="Use the picture as it is">Use original</button>
      <button class="btn primary" onclick={() => finish(true)} disabled={!img || busy}>
        {busy ? 'Saving…' : initial ? 'Update token' : 'Create token'}
      </button>
    </footer>
  </div>
</div>

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    z-index: 110;
    display: grid;
    place-items: center;
    padding: 16px;
    background: var(--backdrop);
  }
  .dialog {
    width: min(720px, 100%);
    max-height: 92vh;
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
  .body {
    display: flex;
    gap: 18px;
    padding: 16px;
    overflow-y: auto;
    flex-wrap: wrap;
    justify-content: center;
  }
  .stage {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6px;
  }
  canvas {
    max-width: 100%;
    border-radius: 12px;
    border: 1px solid var(--border);
    background:
      var(--halftone) 0 0 / 10px 10px,
      var(--bg);
    cursor: grab;
    touch-action: none;
  }
  canvas:active {
    cursor: grabbing;
  }
  .controls {
    flex: 1;
    min-width: 240px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .segmented {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }
  .segmented button {
    padding: 5px 10px;
    border-radius: 999px;
    border: 1px solid var(--border);
    background: var(--surface-2);
    cursor: pointer;
    font-size: 0.85rem;
  }
  .segmented button.on {
    border-color: var(--accent);
    background: color-mix(in srgb, var(--accent) 22%, var(--surface-2));
  }
  .swatches {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    align-items: center;
  }
  .swatch {
    width: 24px;
    height: 24px;
    border-radius: 50%;
    border: 2px solid var(--border);
    cursor: pointer;
  }
  .swatch.active {
    border-color: var(--text);
    box-shadow: 0 0 0 2px var(--bg);
  }
  .swatches input[type='color'],
  .row input[type='color'] {
    width: 36px;
    height: 28px;
    padding: 2px;
  }
  .row {
    display: flex;
    gap: 10px;
    align-items: center;
  }
  .check {
    display: flex;
    gap: 6px;
    align-items: center;
    font-size: 0.85rem;
  }
  .hint {
    font-size: 0.8rem;
    margin: 0;
  }
</style>
