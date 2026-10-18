<script lang="ts">
  import { store } from '../state/game.svelte'

  let { onClose }: { onClose: () => void } = $props()

  const order = $derived(store.game?.turn_order ?? [])
  const round = $derived(store.game?.settings.round ?? 0)

  function canEdit(objectId: string | null): boolean {
    if (store.isGm) return true
    const obj = objectId ? store.objects.get(objectId) : undefined
    void store.objectsVersion
    return !!obj && store.controls(obj)
  }

  function setValue(id: string, value: string) {
    store.send({ type: 'turn.update', id, value: value.trim() || '0' })
  }

  function addCustom() {
    const name = prompt('Nome della voce (es. "Fine round", "Trappola")')?.trim()
    if (name) store.send({ type: 'turn.add', entry: { id: crypto.randomUUID(), object_id: null, name, value: '0' } })
  }

  function focusToken(objectId: string | null) {
    const obj = objectId ? store.objects.get(objectId) : undefined
    if (obj) {
      store.focus(obj.x, obj.y)
      if (store.controls(obj)) store.setSelection([obj.id])
    }
  }

  // Drag to reorder (GM).
  let dragFrom = $state<number | null>(null)
  function drop(to: number) {
    if (dragFrom === null || dragFrom === to) return
    const next = [...order]
    const [moved] = next.splice(dragFrom, 1)
    next.splice(to, 0, moved)
    store.send({ type: 'turn.set', order: next })
    dragFrom = null
  }

  // Simple window drag.
  let pos = $state({ x: 80, y: 80 })
  function startMove(e: PointerEvent) {
    const sx = e.clientX - pos.x
    const sy = e.clientY - pos.y
    const move = (ev: PointerEvent) => (pos = { x: ev.clientX - sx, y: Math.max(0, ev.clientY - sy) })
    const up = () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
  }
</script>

<div class="tracker panel" style:left="{pos.x}px" style:top="{pos.y}px">
  <header role="group" aria-label="Trascina per spostare il tracker" onpointerdown={startMove}>
    <strong>Iniziativa</strong>
    <span class="round">Round {round}</span>
    <button class="icon-btn" aria-label="Chiudi" onpointerdown={(e) => e.stopPropagation()} onclick={onClose}>✕</button>
  </header>

  <ol>
    {#each order as entry, i (entry.id)}
      {@const editable = canEdit(entry.object_id)}
      <li
        class:current={i === 0}
        draggable={store.isGm}
        ondragstart={() => (dragFrom = i)}
        ondragover={(e) => e.preventDefault()}
        ondrop={() => drop(i)}
      >
        <button class="name" onclick={() => focusToken(entry.object_id)} title="Mostra sulla mappa">
          {entry.name || 'Senza nome'}
        </button>
        <input
          value={entry.value}
          disabled={!editable}
          aria-label="Valore iniziativa"
          onchange={(e) => setValue(entry.id, e.currentTarget.value)}
        />
        {#if editable}
          <button class="icon-btn" aria-label="Rimuovi" onclick={() => store.send({ type: 'turn.remove', id: entry.id })}>✕</button>
        {/if}
      </li>
    {:else}
      <li class="empty muted">Seleziona dei token e premi "Aggiungi selezionati".</li>
    {/each}
  </ol>

  <footer>
    <button class="btn small" onclick={() => store.addToTurnOrder(store.selection)} disabled={!store.selection.length}>
      Aggiungi selezionati
    </button>
    {#if store.isGm}
      <button class="btn small" onclick={() => store.send({ type: 'turn.sort' })} title="Ordina dal più alto">⇅ Ordina</button>
      <button class="btn small" onclick={addCustom}>＋ Voce</button>
      <button
        class="btn small danger"
        onclick={() => confirm('Svuotare il tracker?') && store.send({ type: 'turn.set', order: [], round: 0 })}
        >Svuota</button
      >
    {/if}
    <button class="btn primary small next" onclick={() => store.send({ type: 'turn.next' })} disabled={!order.length}>
      Turno successivo ▶
    </button>
  </footer>
</div>

<style>
  .tracker {
    position: fixed;
    z-index: 40;
    width: 300px;
    display: flex;
    flex-direction: column;
    max-height: 70vh;
  }
  header {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 10px;
    border-bottom: 1px solid var(--border);
    cursor: move;
    user-select: none;
  }
  .round {
    margin-left: auto;
    color: var(--text-muted);
    font-size: 0.8rem;
  }
  ol {
    list-style: none;
    margin: 0;
    padding: 4px;
    overflow-y: auto;
  }
  li {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px 6px;
    border-radius: 6px;
  }
  li.current {
    background: color-mix(in srgb, var(--accent) 22%, transparent);
    outline: 1px solid var(--accent);
  }
  .name {
    flex: 1;
    text-align: left;
    border: none;
    background: none;
    cursor: pointer;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    padding: 4px 2px;
  }
  input {
    width: 56px;
    text-align: center;
    padding: 4px;
  }
  .empty {
    padding: 12px;
    font-size: 0.85rem;
  }
  footer {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    padding: 8px;
    border-top: 1px solid var(--border);
  }
  .next {
    margin-left: auto;
  }
</style>
