<script lang="ts">
  import { store } from '../state/game.svelte'
  import Chat from './Chat.svelte'
  import HistoryPanel from './HistoryPanel.svelte'
  import JournalPanel from './JournalPanel.svelte'
  import MacrosPanel from './MacrosPanel.svelte'
  import CompendiumPanel from './CompendiumPanel.svelte'
  import CollectionsPanel from './CollectionsPanel.svelte'
  import ArtLibraryPanel from './ArtLibraryPanel.svelte'
  import PageSettings from './PageSettings.svelte'
  import PlayersPanel from './PlayersPanel.svelte'
  import Settings from './Settings.svelte'

  type Tab =
    | 'chat'
    | 'journal'
    | 'compendium'
    | 'macros'
    | 'collections'
    | 'library'
    | 'players'
    | 'page'
    | 'history'
    | 'settings'
  let {
    tab = $bindable('chat'),
    onToggleTracker,
    onLeave,
  }: { tab?: Tab; onToggleTracker: () => void; onLeave: () => void } = $props()

  const online = $derived(store.players.filter((p) => p.online).length)
</script>

<aside class="sidebar">
  <nav class="tabs">
    <button class:active={tab === 'chat'} onclick={() => (tab = 'chat')} title="Chat" aria-label="Chat">💬</button>
    <button class:active={tab === 'journal'} onclick={() => (tab = 'journal')} title="Journal" aria-label="Journal">📖</button>
    <button class:active={tab === 'compendium'} onclick={() => (tab = 'compendium')} title="Compendium" aria-label="Compendium">📚</button>
    <button class:active={tab === 'macros'} onclick={() => (tab = 'macros')} title="Macros" aria-label="Macros">⚡</button>
    <button class:active={tab === 'collections'} onclick={() => (tab = 'collections')} title="Tables and card decks" aria-label="Collections">🎴</button>
    <button class:active={tab === 'library'} onclick={() => (tab = 'library')} title="Art library" aria-label="Art library">🖼</button>
    <button class:active={tab === 'players'} onclick={() => (tab = 'players')}>👥 {online}</button>
    {#if store.isGm}
      <button class:active={tab === 'page'} onclick={() => (tab = 'page')} title="Page settings" aria-label="Page">🗺</button>
      <button class:active={tab === 'history'} onclick={() => (tab = 'history')} title="History" aria-label="History"
        >🕘</button
      >
    {/if}
    <button class:active={tab === 'settings'} onclick={() => (tab = 'settings')} title="My Settings" aria-label="My Settings">⚙</button>
    <button class="tracker" onclick={onToggleTracker} title="Turn Order">⚔</button>
  </nav>
  <div class="content">
    {#if tab === 'chat'}
      <Chat />
    {:else if tab === 'journal'}
      <JournalPanel />
    {:else if tab === 'compendium'}
      <CompendiumPanel />
    {:else if tab === 'macros'}
      <MacrosPanel />
    {:else if tab === 'collections'}
      <CollectionsPanel />
    {:else if tab === 'library'}
      <ArtLibraryPanel />
    {:else if tab === 'players'}
      <PlayersPanel />
    {:else if tab === 'page' && store.isGm}
      <PageSettings />
    {:else if tab === 'history' && store.isGm}
      <HistoryPanel />
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
    flex-wrap: wrap;
    gap: 2px;
    padding: 6px 6px 0;
    border-bottom: 1px solid var(--border);
  }
  .tabs button {
    border: none;
    background: none;
    padding: 8px 8px;
    white-space: nowrap;
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
