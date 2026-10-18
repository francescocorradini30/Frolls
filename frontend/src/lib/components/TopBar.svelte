<script lang="ts">
  import { store } from '../state/game.svelte'

  let { onLeave, onPageSettings }: { onLeave: () => void; onPageSettings: () => void } = $props()

  const statusLabel = { connecting: 'Connecting…', online: 'Online', offline: 'Offline' }

  let menuFor = $state<string | null>(null)

  function playersOn(pageId: string) {
    const game = store.game
    if (!game) return []
    return store.players.filter(
      (p) => !p.is_gm && p.online && (game.player_page_overrides[p.id] ?? game.player_page_id) === pageId,
    )
  }

  function rename(id: string, current: string) {
    menuFor = null
    const name = prompt('Page name', current)?.trim()
    if (name) store.send({ type: 'page.update', id, patch: { name } })
  }

  function remove(id: string, name: string) {
    menuFor = null
    if (confirm(`Delete page "${name}" and all its contents?`)) {
      store.send({ type: 'page.delete', id })
    }
  }
</script>

<svelte:window onclick={() => (menuFor = null)} />

<header class="topbar">
  <span class="brand text-gradient">Frolls</span>

  {#if store.isGm}
    <nav class="pages" aria-label="Pages">
      {#each store.pages as pg (pg.id)}
        {@const here = playersOn(pg.id)}
        <div class="tab" class:active={store.page?.id === pg.id}>
          <button class="tab-main" onclick={() => store.viewPage(pg.id)} title={pg.name}>
            {#if store.game?.player_page_id === pg.id}<span class="flag" title="Players page">⚑</span>{/if}
            <span class="tab-name">{pg.name}</span>
            {#if here.length}
              <span class="dots" title={here.map((p) => p.name).join(', ')}>
                {#each here.slice(0, 4) as p (p.id)}<i style:background={p.color}></i>{/each}
                {#if here.length > 4}<small>+{here.length - 4}</small>{/if}
              </span>
            {/if}
          </button>
          <button
            class="tab-menu"
            aria-label="Page actions"
            onclick={(e) => {
              e.stopPropagation()
              menuFor = menuFor === pg.id ? null : pg.id
            }}>▾</button
          >
          {#if menuFor === pg.id}
            <div class="menu panel" role="menu">
              <button onclick={() => store.send({ type: 'game.player_page', page_id: pg.id })}>
                Move all players here
              </button>
              {#each store.players.filter((p) => !p.is_gm) as p (p.id)}
                <button onclick={() => store.send({ type: 'game.player_page', page_id: pg.id, player_id: p.id })}>
                  Move only {p.name} here
                </button>
              {/each}
              <hr />
              <button onclick={() => rename(pg.id, pg.name)}>Rename</button>
              <button
                onclick={() => {
                  store.viewPage(pg.id)
                  onPageSettings()
                }}>Page settings</button
              >
              <button onclick={() => store.send({ type: 'page.duplicate', id: pg.id })}>Duplicate</button>
              <button class="danger" onclick={() => remove(pg.id, pg.name)}>Delete</button>
            </div>
          {/if}
        </div>
      {/each}
      <button class="icon-btn add" title="New page" onclick={() => store.send({ type: 'page.create' })}>＋</button>
    </nav>
  {:else}
    <span class="page-name">{store.page?.name ?? ''}</span>
  {/if}

  <div class="right">
    <span class="status" data-status={store.status}>{statusLabel[store.status]}</span>
    {#if store.me}
      <span class="me">
        <i style:background={store.me.color}></i>
        {store.me.name}
        {#if store.me.is_gm}<em class="badge">GM</em>{/if}
      </span>
    {/if}
    <button class="btn small" onclick={onLeave}>Leave</button>
  </div>
</header>

<style>
  .topbar {
    display: flex;
    align-items: center;
    gap: 12px;
    height: var(--topbar-h);
    padding: 0 12px;
    background: var(--gradient-surface);
    border-bottom: 1px solid var(--border);
    min-width: 0;
    position: relative;
  }
  /* Signature gradient line under the bar. */
  .topbar::after {
    content: '';
    position: absolute;
    left: 0;
    right: 0;
    bottom: -1px;
    height: 2px;
    background: var(--gradient-accent);
    opacity: 0.7;
    pointer-events: none;
  }
  .brand {
    font-weight: 800;
    font-size: 1.2rem;
  }
  .pages {
    display: flex;
    align-items: center;
    gap: 4px;
    overflow-x: auto;
    min-width: 0;
    flex: 1;
    scrollbar-width: thin;
  }
  .tab {
    position: relative;
    display: flex;
    align-items: stretch;
    border: 1px solid var(--border);
    border-radius: 6px;
    background: var(--surface-2);
    flex-shrink: 0;
  }
  .tab.active {
    border-color: var(--accent);
    background: color-mix(in srgb, var(--accent) 16%, var(--surface-2));
  }
  .tab button {
    border: none;
    background: none;
    cursor: pointer;
    padding: 5px 8px;
  }
  .tab-main {
    display: flex;
    align-items: center;
    gap: 6px;
    max-width: 200px;
  }
  .tab-name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .tab-menu {
    color: var(--text-muted);
    border-left: 1px solid var(--border) !important;
  }
  .flag {
    color: var(--accent);
  }
  .dots {
    display: flex;
    align-items: center;
    gap: 2px;
  }
  .dots small {
    font-size: 0.7rem;
    color: var(--text-muted);
  }
  .dots i,
  .me i {
    display: inline-block;
    width: 9px;
    height: 9px;
    border-radius: 50%;
  }
  .menu {
    position: absolute;
    top: calc(100% + 4px);
    left: 0;
    z-index: 50;
    display: flex;
    flex-direction: column;
    min-width: 220px;
    padding: 4px;
  }
  .menu button {
    text-align: left;
    padding: 7px 10px;
    border-radius: 5px;
  }
  .menu button:hover {
    background: var(--surface-3);
  }
  .menu hr {
    width: 100%;
    border: none;
    border-top: 1px solid var(--border);
    margin: 4px 0;
  }
  .danger {
    color: var(--danger);
  }
  .add {
    flex-shrink: 0;
  }
  .page-name {
    flex: 1;
    color: var(--text-muted);
  }
  .right {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-left: auto;
    flex-shrink: 0;
  }
  .status {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 0.8rem;
    color: var(--text-muted);
  }
  .status::before {
    content: '';
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--status-color, var(--connecting));
  }
  .status[data-status='online'] {
    --status-color: var(--online);
  }
  .status[data-status='offline'] {
    --status-color: var(--offline);
  }
  .me {
    display: flex;
    align-items: center;
    gap: 6px;
    font-weight: 600;
  }
  @media (max-width: 700px) {
    .status,
    .me {
      display: none;
    }
  }
</style>
