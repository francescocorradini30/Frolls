<script lang="ts">
  import type { CompendiumKind } from '../net/protocol'
  import { store } from '../state/game.svelte'

  const CRS = ['0', '1/8', '1/4', '1/2', ...Array.from({ length: 30 }, (_, i) => String(i + 1))]

  let kind = $state<CompendiumKind>('monster')
  let query = $state('')
  let cr = $state('')
  let level = $state('')
  let addTo = $state('')
  let timer: ReturnType<typeof setTimeout> | undefined

  // Search on the server as you type (a short pause first).
  $effect(() => {
    const args = [kind, query, cr, level] as const
    clearTimeout(timer)
    timer = setTimeout(() => {
      store.searchCompendium(args[0], args[1], args[0] === 'monster' && args[2] ? args[2] : null,
        args[0] === 'spell' && args[3] !== '' ? Number(args[3]) : null)
    }, 180)
  })

  const entry = $derived(store.compendiumEntry)
  // Characters with a 5e sheet I may change: where a spell can go.
  const sheets = $derived(store.characters.filter((c) => c.sheet && store.canEditCharacter(c)))

  function choose(k: CompendiumKind) {
    kind = k
    store.compendiumEntry = null
  }

  function drag(e: DragEvent, key: string) {
    e.dataTransfer?.setData('application/x-frolls-monster', key)
    e.dataTransfer!.effectAllowed = 'copy'
  }

  const mod = (score: number) => {
    const m = Math.floor((score - 10) / 2)
    return m >= 0 ? `+${m}` : `${m}`
  }
</script>

<div class="compendium">
  <div class="seg" role="tablist">
    <button class:on={kind === 'monster'} role="tab" aria-selected={kind === 'monster'} onclick={() => choose('monster')}>Monsters</button>
    <button class:on={kind === 'spell'} role="tab" aria-selected={kind === 'spell'} onclick={() => choose('spell')}>Spells</button>
  </div>

  {#if entry}
    <div class="entry">
      <button class="link" onclick={() => (store.compendiumEntry = null)}>← results</button>
      <h3>{entry.name}</h3>
      {#if entry.sheet}
        {@const s = entry.sheet}
        <p class="muted">{entry.size} {entry.type} · CR {entry.cr}</p>
        <div class="line">AC <b>{s.ac}</b> · HP <b>{s.hp.max}</b> · Speed <b>{s.speed} ft</b></div>
        <div class="scores">
          {#each Object.entries(s.abilities) as [k, v] (k)}<span><small>{k.toUpperCase()}</small>{v} ({mod(v)})</span>{/each}
        </div>
        <p class="text">{s.features}</p>
        {#if store.isGm}
          <div class="row">
            <button class="btn small primary" onclick={() => store.send({ type: 'compendium.add_monster', key: entry.key })}>Add to journal</button>
            <span class="drag-hint muted" draggable="true" ondragstart={(e) => drag(e, entry.key)} role="button" tabindex="0">⠿ drag onto the map</span>
          </div>
        {/if}
      {:else if entry.spell}
        {@const sp = entry.spell}
        <p class="muted">{sp.level === 0 ? 'Cantrip' : `Level ${sp.level}`} · {entry.school}{sp.concentration ? ' · concentration' : ''}{sp.ritual ? ' · ritual' : ''}</p>
        {#if entry.classes?.length}<p class="muted small">{entry.classes.join(', ')}</p>{/if}
        <p class="text">{sp.description}</p>
        {#if sheets.length}
          <div class="row">
            <select bind:value={addTo} aria-label="Add the spell to">
              <option value="">Add to…</option>
              {#each sheets as c (c.id)}<option value={c.id}>{c.name}</option>{/each}
            </select>
            <button class="btn small primary" disabled={!addTo}
              onclick={() => store.send({ type: 'compendium.add_spell', key: entry.key, character_id: addTo })}>Add spell</button>
          </div>
        {/if}
      {/if}
    </div>
  {:else}
    <div class="filters">
      <input type="search" placeholder={kind === 'monster' ? 'Search monsters' : 'Search spells'} bind:value={query}
        aria-label="Search the compendium" />
      {#if kind === 'monster'}
        <select bind:value={cr} aria-label="Challenge rating">
          <option value="">Any CR</option>
          {#each CRS as c (c)}<option value={c}>CR {c}</option>{/each}
        </select>
      {:else}
        <select bind:value={level} aria-label="Spell level">
          <option value="">Any level</option>
          <option value="0">Cantrip</option>
          {#each [1, 2, 3, 4, 5, 6, 7, 8, 9] as l (l)}<option value={String(l)}>Level {l}</option>{/each}
        </select>
      {/if}
    </div>
    <ul class="results">
      {#each store.compendiumResults as item (item.key)}
        <li>
          <button class="result" draggable={kind === 'monster' && store.isGm} ondragstart={(e) => drag(e, item.key)}
            onclick={() => store.openCompendium(kind, item.key)}
            title={kind === 'monster' && store.isGm ? 'Open · drag onto the map to place it' : 'Open'}>
            <span class="name">{item.name}</span>
            <small class="muted">{kind === 'monster' ? `CR ${item.cr} · ${item.type}` : item.level === 0 ? 'cantrip' : `level ${item.level}`}</small>
          </button>
        </li>
      {:else}
        <li class="muted empty">Nothing found.</li>
      {/each}
    </ul>
  {/if}

  <p class="attribution muted">
    Includes material from the System Reference Document 5.2 by Wizards of the Coast LLC, licensed CC-BY-4.0
    (creativecommons.org/licenses/by/4.0). Data structured by Open5e.
  </p>
</div>

<style>
  .compendium {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 8px;
  }
  .seg {
    display: flex;
    border: 1px solid var(--border);
    border-radius: 8px;
    overflow: hidden;
  }
  .seg button {
    flex: 1;
    border: none;
    background: none;
    color: var(--text-muted);
    padding: 5px;
    cursor: pointer;
  }
  .seg button.on {
    background: var(--gradient-accent);
    color: var(--accent-contrast);
    font-weight: 700;
  }
  .filters {
    display: flex;
    gap: 6px;
  }
  .filters input {
    flex: 1;
    min-width: 0;
  }
  .filters select {
    width: 110px;
  }
  .results {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  .result {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 8px;
    width: 100%;
    padding: 5px 6px;
    border: none;
    border-radius: 6px;
    background: none;
    color: var(--text);
    text-align: left;
    cursor: pointer;
  }
  .result:hover {
    background: var(--surface-2);
  }
  .name {
    font-weight: 600;
  }
  .empty {
    padding: 8px;
    font-size: 0.8rem;
  }
  .entry {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .entry h3 {
    margin: 0;
  }
  .entry p {
    margin: 0;
  }
  .small {
    font-size: 0.75rem;
  }
  .line {
    font-size: 0.85rem;
  }
  .scores {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 4px;
    font-size: 0.8rem;
  }
  .scores span {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 3px;
    border: 1px solid var(--border);
    border-radius: 6px;
  }
  .scores small {
    color: var(--text-muted);
    font-size: 0.65rem;
  }
  .text {
    white-space: pre-wrap;
    font-size: 0.82rem;
    line-height: 1.45;
  }
  .row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
  }
  .drag-hint {
    cursor: grab;
    font-size: 0.8rem;
  }
  .link {
    align-self: flex-start;
    border: none;
    background: none;
    padding: 0;
    color: var(--accent-3);
    cursor: pointer;
  }
  .attribution {
    margin: 6px 0 0;
    font-size: 0.65rem;
    line-height: 1.35;
  }
</style>
