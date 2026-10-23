<script lang="ts">
  import type { TurnAction, TurnEntry } from '../net/protocol'
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

  const ACTIONS: [TurnAction, string][] = [
    ['action', 'Action'],
    ['bonus_action', 'Bonus'],
    ['reaction', 'Reaction'],
  ]
  const fighting = $derived(round > 0 && order.length > 0)
  const myTurn = $derived(order.length > 0 && canEdit(order[0].object_id))

  /** Movement this turn against the speed on the sheet, in the game's units. */
  function movement(entry: TurnEntry): string | null {
    void store.objectsVersion
    const obj = entry.object_id ? store.objects.get(entry.object_id) : undefined
    const speed = store.character(obj?.props.represents)?.sheet?.speed
    const moved = entry.moved ?? 0
    if (speed === undefined && !moved) return null
    const metric = store.measurement === 'metric'
    const show = (ft: number) => (metric ? `${Math.round((ft / 5) * 1.5 * 10) / 10}` : `${ft}`)
    return `${show(moved)}${speed !== undefined ? ` / ${show(speed)}` : ''} ${metric ? 'm' : 'ft'}`
  }

  function setValue(id: string, value: string) {
    store.send({ type: 'turn.update', id, value: value.trim() || '0' })
  }

  function addCustom() {
    const name = prompt('Entry name (e.g. "End of round", "Trap")')?.trim()
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
  <header role="group" aria-label="Drag to move the tracker" onpointerdown={startMove}>
    <strong>Turn Order</strong>
    <span class="round">Round {round}</span>
    <button class="icon-btn" aria-label="Close" onpointerdown={(e) => e.stopPropagation()} onclick={onClose}>✕</button>
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
        <button class="name" onclick={() => focusToken(entry.object_id)} title="Show on map">
          {entry.name || 'Unnamed'}
        </button>
        <input
          value={entry.value}
          disabled={!editable}
          aria-label="Initiative value"
          onchange={(e) => setValue(entry.id, e.currentTarget.value)}
        />
        {#if editable}
          <button class="icon-btn" aria-label="Remove" onclick={() => store.send({ type: 'turn.remove', id: entry.id })}>✕</button>
        {/if}
      </li>
      {#if i === 0 && fighting}
        {@const move = movement(entry)}
        <li class="economy" aria-label="This turn">
          {#each ACTIONS as [what, text] (what)}
            {@const used = !!entry.used?.[what]}
            <button
              class="chip"
              class:used
              disabled={!editable}
              title={used ? `${text} used: click to give it back` : `${text} available: click when used`}
              onclick={() => store.turnUse(entry.id, what, !used)}>{text}</button
            >
          {/each}
          {#if move}<span class="move" title="Movement this turn">🦶 {move}</span>{/if}
        </li>
      {/if}
    {:else}
      <li class="empty muted">Select some tokens and press "Add selected".</li>
    {/each}
  </ol>

  <footer>
    <button class="btn small" onclick={() => store.addToTurnOrder(store.selection)} disabled={!store.selection.length}>
      Add selected
    </button>
    {#if store.isGm}
      <button
        class="btn small"
        onclick={() => store.rollInitiative(store.selection)}
        disabled={!store.selection.length}
        title="Roll initiative for the selected tokens: monsters of the same kind share a roll">🎲 Initiative</button
      >
      <button class="btn small" onclick={() => store.send({ type: 'turn.sort' })} title="Sort highest first">⇅ Sort</button>
      <button class="btn small" onclick={addCustom}>＋ Entry</button>
      <button
        class="btn small danger"
        onclick={() => confirm('Clear the turn order?') && store.send({ type: 'turn.set', order: [], round: 0 })}
        >Clear</button
      >
    {/if}
    <button
      class="btn primary small next"
      onclick={() => store.send({ type: 'turn.next' })}
      disabled={!order.length || !myTurn}
      title={store.isGm ? 'Next turn' : 'End your turn'}
    >
      {store.isGm ? 'Next turn ▶' : 'End turn ▶'}
    </button>
  </footer>
</div>

<style>
  .economy {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 4px;
    padding: 4px 8px 8px;
  }
  .chip {
    border: 1px solid var(--success);
    background: color-mix(in srgb, var(--success) 15%, transparent);
    color: var(--text);
    border-radius: 999px;
    padding: 1px 8px;
    font-size: 0.72rem;
    cursor: pointer;
  }
  .chip.used {
    border-color: var(--border);
    background: none;
    color: var(--text-muted);
    text-decoration: line-through;
  }
  .chip:disabled {
    cursor: default;
  }
  .move {
    margin-left: auto;
    font-size: 0.75rem;
    color: var(--text-muted);
  }
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
