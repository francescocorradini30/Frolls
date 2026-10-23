<script lang="ts">
  import CharacterSheet from './lib/components/CharacterSheet.svelte'
  import JoinDialog from './lib/components/JoinDialog.svelte'
  import MapView from './lib/components/MapView.svelte'
  import QueryDialog from './lib/components/QueryDialog.svelte'
  import EffectDialog from './lib/components/EffectDialog.svelte'
  import Sidebar from './lib/components/Sidebar.svelte'
  import Toasts from './lib/components/Toasts.svelte'
  import Toolbar from './lib/components/Toolbar.svelte'
  import TopBar from './lib/components/TopBar.svelte'
  import TurnTracker from './lib/components/TurnTracker.svelte'
  import { store } from './lib/state/game.svelte'
  import { clearIdentity, loadIdentity, saveIdentity, type Identity } from './lib/state/identity'

  let identity = $state<Identity | null>(loadIdentity())
  let zoom = $state(1)
  let sidebarTab = $state<'chat' | 'journal' | 'compendium' | 'macros' | 'players' | 'page' | 'history' | 'settings'>('chat')
  let trackerOpen = $state(false)
  let map: MapView | undefined = $state()
  const openCharacter = $derived(store.character(store.openCharacterId))

  $effect(() => {
    if (identity) store.connect(identity)
    return () => store.disconnect()
  })

  // Open the tracker for everyone when combat starts.
  let lastTurnCount = 0
  $effect(() => {
    const n = store.game?.turn_order.length ?? 0
    if (n > 0 && lastTurnCount === 0) trackerOpen = true
    lastTurnCount = n
  })

  function join(id: Identity) {
    saveIdentity(id)
    identity = id
  }

  function blockBrowserMenu(e: MouseEvent) {
    const el = e.target as HTMLElement
    if (el.closest('input, textarea, [contenteditable="true"], .sidebar')) return
    e.preventDefault()
  }

  function leave() {
    clearIdentity()
    identity = null
  }
</script>

{#if !identity}
  <JoinDialog onJoin={join} />
{:else}
  <div class="app">
    <TopBar onLeave={leave} onPageSettings={() => (sidebarTab = 'page')} />
    <!-- The browser menu never opens over the map or the toolbar: right click is ours there.
         Text fields keep it (paste, spelling); the sidebar keeps it too. -->
    <div class="main" role="presentation" oncontextmenu={blockBrowserMenu}>
      <Toolbar
        {zoom}
        onZoom={(f) => map?.zoomBy(f)}
        onFit={() => map?.fit()}
        onAddToken={() => map?.addToken()}
        onUploadImage={() => map?.uploadAndPlace()}
      />
      <MapView bind:this={map} bind:zoom />
      <Sidebar bind:tab={sidebarTab} onToggleTracker={() => (trackerOpen = !trackerOpen)} onLeave={leave} />
    </div>
  </div>
  {#if trackerOpen}
    <TurnTracker onClose={() => (trackerOpen = false)} />
  {/if}
  {#if openCharacter}
    {#key openCharacter.id}
      <CharacterSheet character={openCharacter} onClose={() => (store.openCharacterId = null)} />
    {/key}
  {/if}
  {#if store.effectTargets}
    <EffectDialog targets={store.effectTargets} onClose={() => (store.effectTargets = null)} />
  {/if}
  {#if store.queryPrompt}
    {#key store.queryPrompt}
      <QueryDialog pending={store.queryPrompt} />
    {/key}
  {/if}
  <Toasts />
{/if}

<style>
  .app {
    display: flex;
    flex-direction: column;
    height: 100%;
  }
  .main {
    flex: 1;
    display: flex;
    min-height: 0;
  }
</style>
