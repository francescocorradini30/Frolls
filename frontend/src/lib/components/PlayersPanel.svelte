<script lang="ts">
  import { store } from '../state/game.svelte'

  const sorted = $derived(
    [...store.players].sort((a, b) => Number(b.online) - Number(a.online) || a.name.localeCompare(b.name)),
  )

  function pageName(playerId: string): string {
    const game = store.game
    if (!game) return ''
    const pageId = game.player_page_overrides[playerId] ?? game.player_page_id
    return store.pages.find((p) => p.id === pageId)?.name ?? ''
  }
</script>

<ul class="players">
  {#each sorted as p (p.id)}
    <li class:offline={!p.online}>
      <i style:background={p.color}></i>
      <span class="name">{p.name}{p.id === store.me?.id ? ' (you)' : ''}</span>
      {#if p.is_gm}<em class="badge">GM</em>{/if}
      {#if store.isGm && !p.is_gm}<span class="page muted" title="Current page">{pageName(p.id)}</span>{/if}
      <span class="state muted">{p.online ? 'online' : 'offline'}</span>
    </li>
  {/each}
</ul>

<style>
  .players {
    list-style: none;
    margin: 0;
    padding: 8px;
  }
  li {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px;
    border-radius: 6px;
  }
  li:hover {
    background: var(--surface-2);
  }
  li.offline {
    opacity: 0.55;
  }
  i {
    width: 12px;
    height: 12px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .name {
    font-weight: 600;
  }
  .page {
    font-size: 0.75rem;
    margin-left: auto;
  }
  .state {
    font-size: 0.75rem;
    margin-left: auto;
  }
  .page + .state {
    margin-left: 6px;
  }
</style>
