<script lang="ts">
  import type { Layer } from '../net/protocol'
  import { store, type Tool } from '../state/game.svelte'

  let {
    zoom,
    onZoom,
    onFit,
    onAddToken,
    onUploadImage,
  }: {
    zoom: number
    onZoom: (factor: number) => void
    onFit: () => void
    onAddToken: () => void
    onUploadImage: () => void
  } = $props()

  const TOOLS: { id: Tool; icon: string; label: string; key?: string }[] = [
    { id: 'select', icon: '➤', label: 'Select and move', key: 'V' },
    { id: 'pan', icon: '✋', label: 'Pan the map (or hold Space)', key: 'H' },
    { id: 'ruler', icon: '📏', label: 'Ruler', key: 'R' },
  ]
  const DRAW: { id: Tool; icon: string; label: string }[] = [
    { id: 'draw-free', icon: '✎', label: 'Freehand (D)' },
    { id: 'draw-line', icon: '╱', label: 'Line' },
    { id: 'draw-rect', icon: '▭', label: 'Rectangle' },
    { id: 'draw-ellipse', icon: '◯', label: 'Ellipse' },
    { id: 'draw-polygon', icon: '⬠', label: 'Polygon (click to add points, double-click to close)' },
    { id: 'text', icon: 'T', label: 'Text (T)' },
  ]
  const TEMPLATES: { id: Tool; icon: string; label: string }[] = [
    { id: 'template-circle', icon: '◎', label: 'Area: sphere/circle' },
    { id: 'template-cone', icon: '◢', label: 'Area: cone' },
    { id: 'template-line', icon: '━', label: 'Area: line' },
    { id: 'template-square', icon: '▣', label: 'Area: cube' },
  ]
  const LAYERS: { id: Layer; icon: string; label: string }[] = [
    { id: 'map', icon: '🗺', label: 'Map layer (backgrounds and scenery)' },
    { id: 'objects', icon: '♟', label: 'Objects & Tokens layer' },
    { id: 'gm', icon: '👁', label: 'GM layer (hidden from players)' },
  ]

  let open = $state<'draw' | 'template' | null>(null)

  const drawActive = $derived(DRAW.find((t) => t.id === store.tool))
  const templateActive = $derived(TEMPLATES.find((t) => t.id === store.tool))
</script>

<svelte:window onclick={() => (open = null)} />

<aside class="toolbar" aria-label="Tools">
  {#each TOOLS as t (t.id)}
    <button
      class="tool"
      class:active={store.tool === t.id}
      title={`${t.label}${t.key ? ` (${t.key})` : ''}`}
      onclick={() => (store.tool = t.id)}>{t.icon}</button
    >
  {/each}

  <div class="group">
    <button
      class="tool"
      class:active={!!drawActive}
      title="Drawing"
      onclick={(e) => {
        e.stopPropagation()
        open = open === 'draw' ? null : 'draw'
      }}>{drawActive?.icon ?? '✎'}</button
    >
    {#if open === 'draw'}
      <div class="flyout panel">
        {#each DRAW as t (t.id)}
          <button class="tool" class:active={store.tool === t.id} title={t.label} onclick={() => (store.tool = t.id)}
            >{t.icon}</button
          >
        {/each}
        <div class="style" role="presentation" onclick={(e) => e.stopPropagation()}>
          <label title="Stroke color"><input type="color" bind:value={store.drawStyle.stroke} /></label>
          <label title="Stroke width">
            <input type="range" min="1" max="24" bind:value={store.drawStyle.strokeWidth} />
          </label>
          <label class="fill" title="Fill">
            <input
              type="checkbox"
              checked={store.drawStyle.fill !== null}
              onchange={(e) => (store.drawStyle.fill = e.currentTarget.checked ? store.drawStyle.stroke : null)}
            />
            fill
          </label>
          <label title="Text size">
            <input type="number" min="8" max="200" bind:value={store.drawStyle.fontSize} />
          </label>
        </div>
      </div>
    {/if}
  </div>

  <div class="group">
    <button
      class="tool"
      class:active={!!templateActive}
      title="Spell areas"
      onclick={(e) => {
        e.stopPropagation()
        open = open === 'template' ? null : 'template'
      }}>{templateActive?.icon ?? '◎'}</button
    >
    {#if open === 'template'}
      <div class="flyout panel">
        {#each TEMPLATES as t (t.id)}
          <button class="tool" class:active={store.tool === t.id} title={t.label} onclick={() => (store.tool = t.id)}
            >{t.icon}</button
          >
        {/each}
      </div>
    {/if}
  </div>

  {#if store.isGm}
    <hr />
    {#each LAYERS as l (l.id)}
      <button class="tool layer" class:active={store.layer === l.id} title={l.label} onclick={() => (store.layer = l.id)}
        >{l.icon}</button
      >
    {/each}
    <hr />
    <button class="tool" title="New token" onclick={onAddToken}>⊕</button>
    <button class="tool" title="Upload image (token or map, depending on the layer)" onclick={onUploadImage}>🖼</button>
  {/if}

  <div class="spacer"></div>
  <button class="tool" title="Zoom in" onclick={() => onZoom(1.25)}>＋</button>
  <button class="zoom" title="Fit page to screen" onclick={onFit}>{Math.round(zoom * 100)}%</button>
  <button class="tool" title="Zoom out" onclick={() => onZoom(0.8)}>－</button>
</aside>

<style>
  .toolbar {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
    width: var(--toolbar-w);
    padding: 8px 0;
    background: var(--surface);
    border-right: 1px solid var(--border);
    overflow-y: auto;
    overflow-x: visible;
  }
  .tool {
    width: 38px;
    height: 38px;
    flex-shrink: 0;
    border-radius: 8px;
    border: 1px solid transparent;
    background: transparent;
    cursor: pointer;
    font-size: 17px;
    color: var(--text);
  }
  .tool:hover {
    background: var(--surface-3);
  }
  .tool.active {
    background: color-mix(in srgb, var(--accent) 22%, transparent);
    border-color: var(--accent);
  }
  .layer.active {
    background: color-mix(in srgb, var(--gm) 22%, transparent);
    border-color: var(--gm);
  }
  .group {
    position: relative;
  }
  .flyout {
    position: fixed;
    margin-left: 46px;
    margin-top: -40px;
    z-index: 60;
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    padding: 6px;
    width: 220px;
  }
  .style {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    align-items: center;
    width: 100%;
    padding-top: 6px;
    border-top: 1px solid var(--border);
  }
  .style input[type='color'] {
    width: 30px;
    height: 26px;
    padding: 0;
    border: none;
  }
  .style input[type='range'] {
    width: 90px;
  }
  .style input[type='number'] {
    width: 60px;
  }
  .fill {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 0.8rem;
  }
  hr {
    width: 60%;
    border: none;
    border-top: 1px solid var(--border);
    margin: 4px 0;
  }
  .spacer {
    flex: 1;
  }
  .zoom {
    border: none;
    background: none;
    color: var(--text-muted);
    font-size: 0.75rem;
    cursor: pointer;
    padding: 2px;
  }
</style>
