<script lang="ts">
  import type { Card, Deck } from '../net/protocol'
  import { store } from '../state/game.svelte'

  const hands = $derived(store.decks.filter((d) => d.hand.length))
  let open = $state<{ deck: Deck; card: Card } | null>(null)
  let collapsed = $state(false)

  function play(faceDown: boolean) {
    if (!open) return
    // A card played with a click lands in the middle of the view.
    const at = store.viewCenter()
    store.deckAction(open.deck.id, 'play', { card_ids: [open.card.id], x: at.x, y: at.y, face_down: faceDown })
    open = null
  }

  function discard() {
    if (!open) return
    store.deckAction(open.deck.id, 'discard', { card_ids: [open.card.id] })
    open = null
  }

  function drag(e: DragEvent, deck: Deck, card: Card) {
    // Alt while dragging: played face down.
    const data = JSON.stringify({ deck_id: deck.id, card_id: card.id, face_down: e.altKey })
    e.dataTransfer?.setData('application/x-frolls-card', data)
    if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move'
    open = null
  }
</script>

<svelte:window onpointerdown={() => (open = null)} />

{#if hands.length}
  <section class="hand" aria-label="My hand" onpointerdown={(e) => e.stopPropagation()}>
    <header>
      <button class="title" onclick={() => (collapsed = !collapsed)} aria-expanded={!collapsed}>
        🂠 My hand <span class="muted">{hands.reduce((n, d) => n + d.hand.length, 0)}</span>
      </button>
    </header>
    {#if !collapsed}
      {#each hands as deck (deck.id)}
        <div class="deck">
          {#if hands.length > 1}<span class="deck-name">{deck.name}</span>{/if}
          <div class="cards">
            {#each deck.hand as card (card.id)}
              <button
                class="card"
                class:active={open?.card.id === card.id}
                draggable="true"
                title={`${card.name || 'Card'}: drag onto the map to play it (Alt: face down), or click`}
                aria-label={card.name || 'Card'}
                style:background-image={card.image ? `url(${card.image})` : 'none'}
                ondragstart={(e) => drag(e, deck, card)}
                onclick={() => (open = open?.card.id === card.id ? null : { deck, card })}
              >
                {#if !card.image}<span>{card.name || 'Card'}</span>{/if}
              </button>
            {/each}
          </div>
        </div>
      {/each}
      {#if open}
        <div class="actions">
          <strong>{open.card.name || 'Card'}</strong>
          <button class="btn small primary" onclick={() => play(false)}>Play face up</button>
          <button class="btn small" onclick={() => play(true)}>Play face down</button>
          <button class="btn small" onclick={discard}>Discard</button>
        </div>
      {/if}
    {/if}
  </section>
{/if}

<style>
  .hand {
    position: absolute;
    right: 12px;
    bottom: 12px;
    z-index: 20;
    max-width: min(46%, 520px);
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 6px 8px 8px;
    border-radius: 10px;
    background: var(--gradient-surface);
    border: 1px solid var(--border);
    box-shadow: var(--shadow);
  }
  .title {
    border: none;
    background: none;
    padding: 0;
    cursor: pointer;
    font-weight: 700;
    font-size: 0.85rem;
  }
  .deck-name {
    font-size: 0.72rem;
    color: var(--text-muted);
    text-transform: uppercase;
  }
  .cards {
    display: flex;
    gap: 6px;
    overflow-x: auto;
    padding-bottom: 2px;
  }
  .card {
    flex-shrink: 0;
    width: 56px;
    height: 78px;
    padding: 4px;
    border-radius: 6px;
    border: 1px solid var(--border);
    background: var(--surface-3) center / cover no-repeat;
    cursor: grab;
    display: grid;
    place-items: center;
    font-size: 0.7rem;
    overflow: hidden;
    overflow-wrap: anywhere;
    transition: transform 0.12s;
  }
  .card:hover,
  .card.active {
    transform: translateY(-4px);
    border-color: var(--accent);
  }
  .actions {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
    font-size: 0.85rem;
  }
</style>
