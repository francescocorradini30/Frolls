<script lang="ts">
  import type { Page } from '../net/protocol'
  import { store } from '../state/game.svelte'

  const page = $derived(store.page)

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
      <span>Nome</span>
      <input value={page.name} maxlength="120" onchange={(e) => e.currentTarget.value.trim() && patch({ name: e.currentTarget.value.trim() })} />
    </label>

    <div class="grid2">
      <label class="field">
        <span>Larghezza (celle)</span>
        <input type="number" min="1" max="500" value={page.width} onchange={(e) => { const v = num(e, 1, 500); if (v) patch({ width: Math.round(v) }) }} />
      </label>
      <label class="field">
        <span>Altezza (celle)</span>
        <input type="number" min="1" max="500" value={page.height} onchange={(e) => { const v = num(e, 1, 500); if (v) patch({ height: Math.round(v) }) }} />
      </label>
    </div>

    <label class="field">
      <span>Sfondo</span>
      <input type="color" value={page.background_color} onchange={(e) => patch({ background_color: e.currentTarget.value })} />
    </label>

    <h4>Griglia</h4>
    <label class="field">
      <span>Tipo</span>
      <select value={page.grid_type} onchange={(e) => patch({ grid_type: e.currentTarget.value as Page['grid_type'] })}>
        <option value="square">Quadrata</option>
        <option value="hex_h">Esagonale (righe)</option>
        <option value="hex_v">Esagonale (colonne)</option>
        <option value="none">Nessuna</option>
      </select>
    </label>
    <div class="grid2">
      <label class="field">
        <span>Cella (px)</span>
        <input type="number" min="10" max="500" value={page.grid_size} onchange={(e) => { const v = num(e, 10, 500); if (v) patch({ grid_size: Math.round(v) }) }} />
      </label>
      <label class="field">
        <span>Colore</span>
        <input type="color" value={page.grid_color.slice(0, 7)} onchange={(e) => patch({ grid_color: e.currentTarget.value })} />
      </label>
    </div>
    <label class="field">
      <span>Opacità griglia: {Math.round(page.grid_opacity * 100)}%</span>
      <input type="range" min="0" max="1" step="0.05" value={page.grid_opacity} onchange={(e) => patch({ grid_opacity: Number(e.currentTarget.value) })} />
    </label>
    <label class="check">
      <input type="checkbox" checked={page.snap} onchange={(e) => patch({ snap: e.currentTarget.checked })} />
      Aggancia alla griglia (tieni Alt per disattivarlo al volo)
    </label>

    <h4>Misure</h4>
    <div class="grid2">
      <label class="field">
        <span>1 cella =</span>
        <input type="number" min="0.1" step="0.5" value={page.scale_number} onchange={(e) => { const v = num(e, 0.1, 10000); if (v) patch({ scale_number: v }) }} />
      </label>
      <label class="field">
        <span>Unità</span>
        <input value={page.scale_unit} maxlength="12" onchange={(e) => e.currentTarget.value.trim() && patch({ scale_unit: e.currentTarget.value.trim() })} />
      </label>
    </div>
    <label class="field">
      <span>Diagonali</span>
      <select value={page.diagonal_rule} onchange={(e) => patch({ diagonal_rule: e.currentTarget.value as Page['diagonal_rule'] })}>
        <option value="5e">5e: ogni diagonale = 1 cella</option>
        <option value="pf">Alternata 1/2 (Pathfinder, 3.5)</option>
        <option value="euclid">Euclidea (distanza reale)</option>
        <option value="manhattan">Manhattan (no diagonali)</option>
      </select>
    </label>
  </form>
{/if}

<style>
  .settings {
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding: 12px;
    overflow-y: auto;
  }
  .grid2 {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }
  h4 {
    margin: 8px 0 0;
    font-size: 0.85rem;
    color: var(--accent);
  }
  .check {
    display: flex;
    gap: 8px;
    align-items: center;
    font-size: 0.85rem;
  }
  input[type='color'] {
    height: 34px;
    padding: 2px;
  }
</style>
