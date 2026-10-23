<script lang="ts">
  import type { Layer } from '../net/protocol'
  import { store } from '../state/game.svelte'

  let {
    x,
    y,
    objectId,
    onEdit,
    onDuplicate,
    onClose,
  }: {
    x: number
    y: number
    objectId: string | null
    onEdit: (id: string) => void
    onDuplicate: () => void
    onClose: () => void
  } = $props()

  const ids = $derived(objectId ? store.selection : [])
  const first = $derived(objectId ? store.objects.get(objectId) : undefined)
  const allAreas = $derived(ids.every((id) => store.objects.get(id)?.kind === 'template'))
  const anyToken = $derived(ids.some((id) => store.objects.get(id)?.kind === 'token'))
  // Multi-sided tokens among the selection I control (cards included: face up / face down).
  const sided = $derived(
    ids.filter((id) => {
      const o = store.objects.get(id)
      return o && store.controls(o) && (o.props.sides?.length ?? 0) >= 2
    }),
  )
  const cards = $derived(ids.filter((id) => store.objects.get(id)?.props.card && sided.includes(id)))
  const sides = $derived<string[]>(sided.length === 1 && !cards.length ? (first?.props.sides ?? []) : [])

  /** Cards go back into my hand, deck by deck. */
  function takeCards() {
    const byDeck = new Map<string, string[]>()
    for (const id of cards) {
      const deck = store.objects.get(id)?.props.card?.deck_id
      if (deck) byDeck.set(deck, [...(byDeck.get(deck) ?? []), id])
    }
    for (const [deck, objectIds] of byDeck) store.deckAction(deck, 'take', { object_ids: objectIds })
  }

  function flip() {
    for (const id of cards) {
      const o = store.objects.get(id)
      if (o) store.tokenSide([id], o.props.side === 1 ? 0 : 1)
    }
  }

  // Lock: no dragging, resizing or rotating (by me or anyone) until unlocked.
  const lockable = $derived(
    ids.filter((id) => {
      const o = store.objects.get(id)
      return o && store.controls(o) && o.kind !== 'template'
    }),
  )
  const locked = $derived(!!first?.props.locked)

  function toggleLock() {
    store.updateObjects(lockable.map((id) => ({ id, props: { locked: locked ? null : true } })))
  }

  const deletable = $derived(ids.some((id) => {
    const o = store.objects.get(id)
    return o && store.canDelete(o)
  }))

  function act(fn: () => void) {
    fn()
    onClose()
  }

  function moveTo(layer: Layer) {
    store.updateObjects(ids.map((id) => ({ id, layer })))
  }

  function toggleName() {
    const show = first?.props.show_name === false
    store.updateObjects(ids.map((id) => ({ id, props: { show_name: show } })))
  }

  // Keep the menu on screen, measured on its real size: it opens up / to the left of the
  // cursor when it does not fit below / to the right, and scrolls if taller than the window.
  const MARGIN = 8
  let width = $state(0)
  let height = $state(0)
  let viewW = $state(window.innerWidth)
  let viewH = $state(window.innerHeight)
  const left = $derived(
    Math.max(MARGIN, x + width > viewW - MARGIN ? Math.min(x - width, viewW - MARGIN - width) : x),
  )
  const top = $derived(
    Math.max(MARGIN, y + height > viewH - MARGIN ? Math.min(y - height, viewH - MARGIN - height) : y),
  )
</script>

<svelte:window
  bind:innerWidth={viewW}
  bind:innerHeight={viewH}
  onpointerdown={onClose}
  onkeydown={(e) => e.key === 'Escape' && onClose()}
/>

<div
  class="menu panel"
  role="menu"
  tabindex="-1"
  style:left="{left}px"
  style:top="{top}px"
  style:max-height="{viewH - 2 * MARGIN}px"
  bind:offsetWidth={width}
  bind:offsetHeight={height}
  onpointerdown={(e) => e.stopPropagation()}
>
  {#if first}
    {#if ids.length === 1 && (first.kind === 'token' || first.kind === 'image' || first.kind === 'pin')}
      <button onclick={() => act(() => onEdit(first.id))}>Edit…</button>
    {/if}
    {#if anyToken}
      <button onclick={() => act(() => store.addToTurnOrder(ids))}>Add to Turn Order</button>
      <button onclick={() => act(toggleName)}>{first.props.show_name === false ? 'Show' : 'Hide'} name</button>
    {/if}
    {#if cards.length}
      <hr />
      <button onclick={() => act(flip)}>Flip card{cards.length > 1 ? 's' : ''}</button>
      <button onclick={() => act(takeCards)}>Take into my hand</button>
    {:else if sided.length}
      <hr />
      <span class="label">Multi-sided</span>
      <button onclick={() => act(() => store.tokenSide(sided, null))}>🎲 Random side</button>
      {#if sides.length}
        <div class="sides">
          {#each sides as side, i (i)}
            <button
              class="side"
              class:current={first?.props.side === i}
              title={`Side ${i + 1}`}
              aria-label={`Side ${i + 1}`}
              style:background-image={side ? `url(${side})` : 'none'}
              onclick={() => act(() => store.tokenSide(sided, i))}
            >{side ? '' : i + 1}</button>
          {/each}
        </div>
      {/if}
    {/if}
    {#if lockable.length}
      <button onclick={() => act(toggleLock)}>{locked ? '🔓 Unlock' : '🔒 Lock'}</button>
    {/if}
    {#if !allAreas}
      <hr />
      <button onclick={() => act(() => store.send({ type: 'obj.order', ids, to: 'front' }))}>To Front</button>
      <button onclick={() => act(() => store.send({ type: 'obj.order', ids, to: 'back' }))}>To Back</button>
    {/if}
    {#if store.isGm}
      <hr />
      <span class="label">Move to layer</span>
      <button disabled={first.layer === 'map'} onclick={() => act(() => moveTo('map'))}>🗺 Map</button>
      <button disabled={first.layer === 'objects'} onclick={() => act(() => moveTo('objects'))}>♟ Objects & Tokens</button>
      <button disabled={first.layer === 'gm'} onclick={() => act(() => moveTo('gm'))}>👁 GM</button>
      <hr />
      <button onclick={() => act(onDuplicate)}>Duplicate (Ctrl+D)</button>
    {/if}
    {#if deletable}
      <button class="danger" onclick={() => act(() => store.deleteObjects(ids))}>Delete (Del)</button>
    {/if}
  {:else}
    <button onclick={() => act(() => (store.tool = 'select'))}>Select tool</button>
    <button onclick={() => act(() => (store.tool = 'ruler'))}>Ruler</button>
    <p class="muted hint">Hold down on an empty spot to ping{store.isGm ? ' (Shift: pull everyone’s view there)' : ''}.</p>
  {/if}
</div>

<style>
  .menu {
    position: fixed;
    z-index: 90;
    min-width: 210px;
    display: flex;
    flex-direction: column;
    padding: 4px;
    overflow-y: auto;
  }
  button {
    text-align: left;
    padding: 7px 10px;
    border: none;
    border-radius: 5px;
    background: none;
    cursor: pointer;
  }
  button:hover:not(:disabled) {
    background: var(--surface-3);
  }
  button:disabled {
    opacity: 0.4;
    cursor: default;
  }
  .danger {
    color: var(--danger);
  }
  hr:first-child {
    display: none;
  }
  hr {
    border: none;
    border-top: 1px solid var(--border);
    margin: 4px 0;
  }
  .sides {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    padding: 2px 10px 4px;
    max-width: 220px;
  }
  .side {
    width: 34px;
    height: 34px;
    padding: 0;
    text-align: center;
    border: 1px solid var(--border);
    background: var(--surface-3) center / contain no-repeat;
  }
  .side.current {
    border-color: var(--accent);
  }
  .label {
    font-size: 0.72rem;
    color: var(--text-muted);
    padding: 2px 10px;
    text-transform: uppercase;
  }
  .hint {
    font-size: 0.75rem;
    padding: 4px 10px;
    margin: 0;
    max-width: 220px;
  }
</style>
