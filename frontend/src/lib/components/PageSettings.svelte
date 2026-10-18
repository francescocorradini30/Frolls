<script lang="ts">
  import type { Page } from '../net/protocol'
  import { store } from '../state/game.svelte'

  const page = $derived(store.page)
  // Slider position while dragging; saved (and broadcast) only on release.
  let opacityDrag = $state<number | null>(null)
  // Units offered for the page scale, from the game measurement system.
  const units = $derived(store.measurement === 'metric' ? ['m', 'km'] : ['ft', 'mi'])

  function patch(values: Partial<Page>) {
    if (page) store.send({ type: 'page.update', id: page.id, patch: values })
  }

  function num(e: Event & { currentTarget: HTMLInputElement }, min: number, max: number): number | null {
    const v = Number(e.currentTarget.value)
    return Number.isFinite(v) && v >= min && v <= max ? v : null
  }
</script>

{#if page}
  <form class="settings" onsubmit={(e) => e.preventDefault()}>
    <label class="field">
      <span>Name</span>
      <input value={page.name} maxlength="120" onchange={(e) => e.currentTarget.value.trim() && patch({ name: e.currentTarget.value.trim() })} />
    </label>

    <div class="grid2">
      <label class="field">
        <span>Width (cells)</span>
        <input type="number" min="1" max="500" value={page.width} onchange={(e) => { const v = num(e, 1, 500); if (v) patch({ width: Math.round(v) }) }} />
      </label>
      <label class="field">
        <span>Height (cells)</span>
        <input type="number" min="1" max="500" value={page.height} onchange={(e) => { const v = num(e, 1, 500); if (v) patch({ height: Math.round(v) }) }} />
      </label>
    </div>

    <label class="field">
      <span>Background</span>
      <input type="color" value={page.background_color} onchange={(e) => patch({ background_color: e.currentTarget.value })} />
    </label>

    <h4>Grid</h4>
    <label class="field">
      <span>Type</span>
      <select value={page.grid_type} onchange={(e) => patch({ grid_type: e.currentTarget.value as Page['grid_type'] })}>
        <option value="square">Square</option>
        <option value="hex_h">Hex (rows)</option>
        <option value="hex_v">Hex (columns)</option>
        <option value="none">None</option>
      </select>
    </label>
    <div class="grid2">
      <label class="field">
        <span>Cell (px)</span>
        <input type="number" min="10" max="500" value={page.grid_size} onchange={(e) => { const v = num(e, 10, 500); if (v) patch({ grid_size: Math.round(v) }) }} />
      </label>
      <label class="field">
        <span>Color</span>
        <input type="color" value={page.grid_color.slice(0, 7)} onchange={(e) => patch({ grid_color: e.currentTarget.value })} />
      </label>
    </div>
    <label class="field">
      <span>Grid opacity: {Math.round((opacityDrag ?? page.grid_opacity) * 100)}%</span>
      <input
        type="range"
        min="0"
        max="1"
        step="0.05"
        value={page.grid_opacity}
        oninput={(e) => (opacityDrag = Number(e.currentTarget.value))}
        onchange={(e) => {
          opacityDrag = null
          patch({ grid_opacity: Number(e.currentTarget.value) })
        }}
      />
    </label>
    <label class="check">
      <input type="checkbox" checked={page.snap} onchange={(e) => patch({ snap: e.currentTarget.checked })} />
      Snap to grid (hold Alt to disable on the fly)
    </label>

    <h4>Measurement</h4>
    <div class="grid2">
      <label class="field">
        <span>1 cell =</span>
        <input type="number" min="0.1" step="any" value={page.scale_number} onchange={(e) => { const v = num(e, 0.1, 10000); if (v) patch({ scale_number: v }) }} />
      </label>
      <label class="field">
        <span>Unit</span>
        <select value={page.scale_unit} onchange={(e) => patch({ scale_unit: e.currentTarget.value })}>
          {#each units.includes(page.scale_unit) ? units : [...units, page.scale_unit] as u (u)}
            <option value={u}>{u}</option>
          {/each}
        </select>
      </label>
    </div>
    <label class="field">
      <span>Diagonals</span>
      <select value={page.diagonal_rule} onchange={(e) => patch({ diagonal_rule: e.currentTarget.value as Page['diagonal_rule'] })}>
        <option value="5e">5e: every diagonal = 1 cell</option>
        <option value="pf">Alternating 1/2 (Pathfinder, 3.5)</option>
        <option value="euclid">Euclidean (true distance)</option>
        <option value="manhattan">Manhattan (no diagonals)</option>
      </select>
    </label>
  </form>
{/if}

<style>
  input[type='color'] {
    height: 34px;
    padding: 2px;
  }
</style>
