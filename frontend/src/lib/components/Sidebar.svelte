<script lang="ts">
  import { store } from '../state/game.svelte'
  import Chat from './Chat.svelte'
  import PageSettings from './PageSettings.svelte'
  import PlayersPanel from './PlayersPanel.svelte'
  import Settings from './Settings.svelte'

  type Tab = 'chat' | 'players' | 'page' | 'settings'
  let {
    tab = $bindable('chat'),
    onToggleTracker,
    onLeave,
  }: { tab?: Tab; onToggleTracker: () => void; onLeave: () => void } = $props()

  const online = $derived(store.players.filter((p) => p.online).length)
</script>

<aside class="sidebar">
  <nav class="tabs">
    <button class:active={tab === 'chat'} onclick={() => (tab = 'chat')}>💬 Chat</button>
    <button class:active={tab === 'players'} onclick={() => (tab = 'players')}>👥 {online}</button>
    {#if store.isGm}
      <button class:active={tab === 'page'} onclick={() => (tab = 'page')} title="Page settings">🗺 Page</button>
    {/if}
    <button class:active={tab === 'settings'} onclick={() => (tab = 'settings')} title="My Settings" aria-label="My Settings">⚙</button>
    <button class="tracker" onclick={onToggleTracker} title="Turn Order">⚔</button>
  </nav>
  <div class="content">
    {#if tab === 'chat'}
      <Chat />
    {:else if tab === 'players'}
      <PlayersPanel />
    {:else if tab === 'page' && store.isGm}
      <PageSettings />
    {:else if tab === 'settings'}
      <Settings {onLeave} />
    {/if}
  </div>
</aside>

<style>
  .sidebar {
    width: var(--sidebar-w);
    display: flex;
    flex-direction: column;
    background: var(--surface);
    border-left: 1px solid var(--border);
    min-height: 0;
  }
  .tabs {
    display: flex;
    gap: 2px;
    padding: 6px 6px 0;
    border-bottom: 1px solid var(--border);
  }
  .tabs button {
    border: none;
    background: none;
    padding: 8px 10px;
    cursor: pointer;
    color: var(--text-muted);
    border-bottom: 2px solid transparent;
  }
  .tabs button.active {
    color: var(--text);
    border-bottom-color: var(--accent);
  }
  .tracker {
    margin-left: auto;
    font-size: 1rem;
  }
  .content {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    overflow-y: auto;
  }
  @media (max-width: 900px) {
    .sidebar {
      width: 280px;
    }
  }
</style>
