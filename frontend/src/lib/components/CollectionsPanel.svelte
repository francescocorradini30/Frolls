<script lang="ts">
  import type { Card, Deck, RollableTable, TableItem } from '../net/protocol'
  import { store } from '../state/game.svelte'
  import { baseName, pickFile, pickFiles, uploadImage } from '../util/upload'

  // --- Rollable tables ---
  const tables = $derived([...store.tables].sort((a, b) => a.name.localeCompare(b.name)))
  // Table being edited: a draft, saved with one message.
  let tableDraft = $state<{ id: string; name: string; show_players: boolean; items: TableItem[] } | null>(null)
  let uploading = $state(false)

  function newTable() {
    const n = store.tables.length + 1
    store.createTable(`table-${n}`)
  }

  function editTable(t: RollableTable) {
    tableDraft = { id: t.id, name: t.name, show_players: t.show_players, items: t.items.map((i) => ({ ...i })) }
  }

  function saveTable() {
    if (!tableDraft) return
    const { id, name, show_players, items } = $state.snapshot(tableDraft)
    store.updateTable(id, {
      name: name.trim(),
      show_players,
      items: items
        .filter((i) => i.name.trim())
        .map((i) => ({ ...i, name: i.name.trim(), weight: Math.max(0, Math.round(Number(i.weight) || 0)) })),
    })
    tableDraft = null
  }

  async function itemImage(item: TableItem) {
    const file = await pickFile()
    if (!file) return
    uploading = true
    try {
      item.image = await uploadImage(file)
      if (!item.name.trim()) item.name = baseName(file)
    } catch (e) {
      store.toast((e as Error).message)
    } finally {
      uploading = false
    }
  }

  /** One item per picture, named after the file. */
  async function itemsFromImages() {
    if (!tableDraft) return
    const files = await pickFiles()
    uploading = true
    try {
      for (const f of files) {
        tableDraft.items.push({ id: crypto.randomUUID(), name: baseName(f), weight: 1, image: await uploadImage(f) })
      }
    } catch (e) {
      store.toast((e as Error).message)
    } finally {
      uploading = false
    }
  }

  function rollTable(t: RollableTable) {
    store.sendChat(`/r 1t[${t.name}]`)
  }

  // --- Card decks ---
  const decks = $derived([...store.decks].sort((a, b) => a.name.localeCompare(b.name)))
  let deckDraft = $state<{ id: string; name: string; back: string | null; cards: Card[] } | null>(null)
  let dealTo = $state<Record<string, string>>({})
  const others = $derived(store.players.filter((p) => !p.is_gm))

  function newDeck() {
    store.createDeck(`Deck ${store.decks.length + 1}`)
  }

  function editDeck(d: Deck) {
    deckDraft = { id: d.id, name: d.name, back: d.back, cards: (d.cards ?? []).map((c) => ({ ...c })) }
  }

  function saveDeck() {
    if (!deckDraft) return
    const { id, name, back, cards } = $state.snapshot(deckDraft)
    store.updateDeck(id, { name: name.trim() || 'Deck', back, cards })
    deckDraft = null
  }

  async function cardsFromImages() {
    if (!deckDraft) return
    const files = await pickFiles()
    uploading = true
    try {
      for (const f of files) {
        deckDraft.cards.push({ id: crypto.randomUUID(), name: baseName(f), image: await uploadImage(f) })
      }
    } catch (e) {
      store.toast((e as Error).message)
    } finally {
      uploading = false
    }
  }

  async function deckBack() {
    if (!deckDraft) return
    const file = await pickFile()
    if (!file) return
    uploading = true
    try {
      deckDraft.back = await uploadImage(file)
    } catch (e) {
      store.toast((e as Error).message)
    } finally {
      uploading = false
    }
  }

  function playerName(id: string): string {
    return store.players.find((p) => p.id === id)?.name ?? '?'
  }

  function dragTable(e: DragEvent, t: RollableTable) {
    e.dataTransfer?.setData('application/x-frolls-table', t.id)
  }
</script>

<div class="collections">
  <section aria-labelledby="tables-h">
    <header>
      <h3 id="tables-h">Rollable tables</h3>
      {#if store.isGm}<button class="btn small primary" onclick={newTable}>+ Table</button>{/if}
    </header>
    <p class="hint muted">
      Roll with <code>1t[name]</code> in chat, also inline: <code>[[1t[name]]]</code>.
      {#if store.isGm}Drag a table onto the map for a multi-sided token with its pictures.{/if}
    </p>
    <ul>
      {#each tables as t (t.id)}
        <li>
          {#if tableDraft?.id === t.id}
            <div class="edit">
              <input bind:value={tableDraft.name} maxlength="60" aria-label="Table name" />
              <label class="check"><input type="checkbox" bind:checked={tableDraft.show_players} /> Players can see and roll it</label>
              <div class="items">
                <div class="item head muted"><span></span><span>Item</span><span>Weight</span><span></span></div>
                {#each tableDraft.items as item, i (item.id)}
                  <div class="item">
                    <button
                      class="thumb"
                      title={item.image ? 'Change picture' : 'Add a picture'}
                      aria-label={`Picture of item ${i + 1}`}
                      style:background-image={item.image ? `url(${item.image})` : 'none'}
                      onclick={() => itemImage(item)}>{item.image ? '' : '+'}</button
                    >
                    <input bind:value={item.name} maxlength="200" aria-label={`Item ${i + 1} name`} />
                    <input type="number" min="0" max="1000" bind:value={item.weight} aria-label={`Item ${i + 1} weight`} />
                    <button class="mini" aria-label={`Remove item ${i + 1}`} onclick={() => tableDraft?.items.splice(i, 1)}>✕</button>
                  </div>
                {/each}
              </div>
              <div class="row">
                <button class="btn small" onclick={() => tableDraft?.items.push({ id: crypto.randomUUID(), name: '', weight: 1, image: null })}>+ Item</button>
                <button class="btn small" disabled={uploading} onclick={itemsFromImages}>{uploading ? 'Uploading…' : '+ Items from pictures'}</button>
              </div>
              <div class="row">
                <button class="btn small danger" onclick={() => (store.deleteTable(t.id), (tableDraft = null))}>Delete</button>
                <span class="spacer"></span>
                <button class="btn small" onclick={() => (tableDraft = null)}>Cancel</button>
                <button class="btn small primary" onclick={saveTable}>Save</button>
              </div>
            </div>
          {:else}
            <div class="row" draggable={store.isGm} ondragstart={(e) => dragTable(e, t)} role="listitem">
              <button class="btn small run" title={`/r 1t[${t.name}]`} onclick={() => rollTable(t)}>🎲 {t.name}</button>
              <span class="muted small">{t.items.length} item{t.items.length === 1 ? '' : 's'}</span>
              {#if store.isGm && !t.show_players}<span class="badge" title="Hidden from players">GM</span>{/if}
              <span class="spacer"></span>
              {#if store.isGm}<button class="mini" aria-label={`Edit ${t.name}`} onclick={() => editTable(t)}>✎</button>{/if}
            </div>
          {/if}
        </li>
      {:else}
        <li class="muted empty">No tables{store.isGm ? ' yet' : ''}.</li>
      {/each}
    </ul>
  </section>

  <section aria-labelledby="decks-h">
    <header>
      <h3 id="decks-h">Card decks</h3>
      {#if store.isGm}<button class="btn small primary" onclick={newDeck}>+ Deck</button>{/if}
    </header>
    <ul>
      {#each decks as d (d.id)}
        <li class="deck">
          {#if deckDraft?.id === d.id}
            <div class="edit">
              <input bind:value={deckDraft.name} maxlength="60" aria-label="Deck name" />
              <div class="row">
                <button class="card-tile back" style:background-image={deckDraft.back ? `url(${deckDraft.back})` : 'none'}
                  onclick={deckBack} title="Card back" aria-label="Card back">{deckDraft.back ? '' : 'Back'}</button>
                <span class="muted small">The back is shared by every card and shown when a card is face down.</span>
              </div>
              <div class="cards">
                {#each deckDraft.cards as card, i (card.id)}
                  <div class="card-edit">
                    <div class="card-tile" style:background-image={card.image ? `url(${card.image})` : 'none'}>
                      {card.image ? '' : card.name}
                    </div>
                    <input bind:value={card.name} maxlength="120" aria-label={`Card ${i + 1} name`} />
                    <button class="mini" aria-label={`Remove card ${i + 1}`} onclick={() => deckDraft?.cards.splice(i, 1)}>✕</button>
                  </div>
                {/each}
              </div>
              <div class="row">
                <button class="btn small" disabled={uploading} onclick={cardsFromImages}>{uploading ? 'Uploading…' : '+ Cards from pictures'}</button>
                <button class="btn small" onclick={() => deckDraft?.cards.push({ id: crypto.randomUUID(), name: `Card ${(deckDraft?.cards.length ?? 0) + 1}`, image: null })}>+ Text card</button>
              </div>
              <div class="row">
                <button class="btn small danger" onclick={() => (store.deleteDeck(d.id), (deckDraft = null))}>Delete</button>
                <span class="spacer"></span>
                <button class="btn small" onclick={() => (deckDraft = null)}>Cancel</button>
                <button class="btn small primary" onclick={saveDeck}>Save</button>
              </div>
            </div>
          {:else}
            <div class="row">
              <strong>🂠 {d.name}</strong>
              {#if store.isGm && !d.settings.show_players}<span class="badge" title="Hidden from players">GM</span>{/if}
              <span class="spacer"></span>
              {#if store.isGm}<button class="mini" aria-label={`Edit ${d.name}`} onclick={() => editDeck(d)}>✎</button>{/if}
            </div>
            <div class="counts muted small">
              <span title="Cards in the pile">{d.pile_count} in the deck</span>
              <span title="Cards on the map">{d.table_count} on the table</span>
              <span title="Discarded cards">{d.discard_count} discarded</span>
            </div>
            {#if Object.keys(d.hand_counts).length}
              <div class="counts muted small">
                {#each Object.entries(d.hand_counts) as [pid, n] (pid)}<span>{playerName(pid)}: {n} in hand</span>{/each}
              </div>
            {/if}
            <div class="row wrap">
              {#if store.isGm || d.settings.players_draw}
                <button class="btn small" disabled={!d.pile_count} onclick={() => store.deckAction(d.id, 'draw')}>Draw</button>
              {/if}
              {#if store.isGm}
                <select bind:value={dealTo[d.id]} aria-label={`Deal from ${d.name} to`}>
                  <option value={undefined}>Deal to…</option>
                  {#each others as pl (pl.id)}<option value={pl.id}>{pl.name}</option>{/each}
                </select>
                <button class="btn small" disabled={!dealTo[d.id] || !d.pile_count}
                  onclick={() => store.deckAction(d.id, 'draw', { player_id: dealTo[d.id] })}>Deal</button>
                <button class="btn small" disabled={!d.pile_count} title="Top card of the deck, face up in the middle of the view"
                  onclick={() => store.deckAction(d.id, 'play', { x: store.viewCenter().x, y: store.viewCenter().y })}>To table</button>
                <button class="btn small" title="Put the discarded cards back and shuffle" onclick={() => store.deckAction(d.id, 'shuffle')}>Shuffle</button>
                <button class="btn small" title="Every card back into the deck, from hands and the table, then shuffle"
                  onclick={() => store.deckAction(d.id, 'recall')}>Recall</button>
              {/if}
            </div>
            {#if store.isGm}
              <div class="row wrap small">
                <label class="check"><input type="checkbox" checked={d.settings.show_players}
                  onchange={(e) => store.updateDeck(d.id, { settings: { show_players: e.currentTarget.checked } })} /> Players see it</label>
                <label class="check"><input type="checkbox" checked={d.settings.players_draw}
                  onchange={(e) => store.updateDeck(d.id, { settings: { players_draw: e.currentTarget.checked } })} /> Players draw</label>
              </div>
            {/if}
          {/if}
        </li>
      {:else}
        <li class="muted empty">No decks{store.isGm ? ' yet' : ''}.</li>
      {/each}
    </ul>
  </section>
</div>

<style>
  .collections {
    display: flex;
    flex-direction: column;
    gap: 16px;
    padding: 8px;
  }
  section {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  h3 {
    margin: 0;
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--text-muted);
  }
  .hint {
    font-size: 0.75rem;
    margin: 0 2px;
  }
  code {
    font-family: ui-monospace, monospace;
    background: var(--bg);
    padding: 0 3px;
    border-radius: 3px;
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  li {
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 6px;
    background: var(--surface-2);
  }
  li.empty {
    border-style: dashed;
    background: none;
    font-size: 0.85rem;
  }
  .deck {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .wrap {
    flex-wrap: wrap;
  }
  .spacer {
    flex: 1;
  }
  .small {
    font-size: 0.78rem;
  }
  .counts {
    display: flex;
    flex-wrap: wrap;
    gap: 2px 10px;
  }
  .run {
    max-width: 70%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .mini {
    border: none;
    background: none;
    cursor: pointer;
    color: var(--text-muted);
  }
  .edit {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .check {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 0.82rem;
  }
  .items {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .item {
    display: grid;
    grid-template-columns: 30px 1fr 58px 22px;
    gap: 4px;
    align-items: center;
  }
  .item.head {
    font-size: 0.72rem;
  }
  .thumb {
    width: 30px;
    height: 30px;
    padding: 0;
    border: 1px dashed var(--border);
    border-radius: 5px;
    background: var(--surface-3) center / cover no-repeat;
    cursor: pointer;
  }
  .cards {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(78px, 1fr));
    gap: 6px;
  }
  .card-edit {
    display: grid;
    grid-template-columns: 1fr 18px;
    gap: 2px;
  }
  .card-edit .card-tile {
    grid-column: 1 / -1;
  }
  .card-edit input {
    min-width: 0;
    font-size: 0.75rem;
  }
  .card-tile {
    aspect-ratio: 5 / 7;
    width: 100%;
    border: 1px solid var(--border);
    border-radius: 6px;
    background: var(--surface-3) center / cover no-repeat;
    display: grid;
    place-items: center;
    font-size: 0.7rem;
    padding: 4px;
    overflow: hidden;
    overflow-wrap: anywhere;
  }
  .card-tile.back {
    width: 46px;
    flex-shrink: 0;
    cursor: pointer;
  }
  select {
    max-width: 110px;
    padding: 3px 6px;
    font-size: 0.8rem;
  }
</style>
