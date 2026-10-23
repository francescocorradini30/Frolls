<script lang="ts">
  import { onMount } from 'svelte'
  import { store } from '../state/game.svelte'

  onMount(() => store.requestHistory())

  const events = $derived(store.history ? [...store.history].reverse() : null)

  function time(iso: string): string {
    return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }

  function author(id: string | null): string {
    return id ? store.playerName(id) : 'system'
  }

  function color(id: string | null): string | undefined {
    return store.players.find((p) => p.id === id)?.color
  }
</script>

<div class="history">
  <p class="hint muted">Every change to the game, newest first. Map changes can be reverted, whoever made them.</p>
  {#if events === null}
    <p class="muted empty">Loading…</p>
  {:else if events.length === 0}
    <p class="muted empty">No changes yet.</p>
  {:else}
    <ol>
      {#each events as e (e.seq)}
        <li class:reverted={e.reverted}>
          <i style:background={color(e.player_id)}></i>
          <div class="text">
            <span class="who">{author(e.player_id)}</span>
            <span class="what">{e.summary}</span>
            <span class="when muted">#{e.seq} · {time(e.created_at)}</span>
          </div>
          {#if e.reverted}
            <span class="badge">reverted</span>
          {:else if e.revertible}
            <button class="btn" title="Undo this change" onclick={() => store.revert(e.seq)}>Revert</button>
          {/if}
        </li>
      {/each}
    </ol>
  {/if}
</div>

<style>
  .history {
    padding: 8px;
  }
  .hint {
    font-size: 0.75rem;
    margin: 4px 8px 8px;
  }
  .empty {
    margin: 8px;
  }
  ol {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  li {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 8px;
    border-radius: 6px;
  }
  li:hover {
    background: var(--surface-2);
  }
  li.reverted .what {
    text-decoration: line-through;
    color: var(--text-muted);
  }
  i {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    flex-shrink: 0;
    background: var(--border);
  }
  .text {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-wrap: wrap;
    column-gap: 6px;
    font-size: 0.85rem;
  }
  .who {
    font-weight: 600;
  }
  .what {
    overflow-wrap: anywhere;
  }
  .when {
    width: 100%;
    font-size: 0.7rem;
  }
  .btn {
    font-size: 0.75rem;
    padding: 2px 8px;
  }
</style>
