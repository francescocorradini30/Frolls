<script lang="ts">
  import { store } from '../state/game.svelte'

  // My macros marked for the bar.
  const macros = $derived(store.macros.filter((m) => m.in_bar).sort((a, b) => a.name.localeCompare(b.name)))

  // Token actions of the character the selected token represents.
  const selected = $derived.by(() => {
    void store.objectsVersion
    if (store.selection.length !== 1) return null
    const obj = store.objects.get(store.selection[0])
    const character = obj?.kind === 'token' ? store.character(obj.props.represents) : undefined
    return obj && character ? { tokenId: obj.id, character } : null
  })
  const actions = $derived(selected ? selected.character.abilities.filter((a) => a.token_action) : [])
</script>

{#if macros.length || actions.length}
  <div class="quickbar" role="toolbar" aria-label="Quick bar">
    {#each macros as m (m.id)}
      <button class="btn small" title={m.action} onclick={() => store.sendChat(m.action)}>{m.name}</button>
    {/each}
    {#if macros.length && actions.length}<span class="sep"></span>{/if}
    {#if selected}
      {#each actions as a (a.name)}
        <button
          class="btn small action"
          title={`${selected.character.name}: ${a.action}`}
          onclick={() => store.sendChat(`%{selected|${a.name}}`, selected.tokenId)}>{a.name}</button
        >
      {/each}
    {/if}
  </div>
{/if}

<style>
  .quickbar {
    position: absolute;
    left: 12px;
    bottom: 12px;
    z-index: 20;
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    max-width: calc(50% - 24px);
    padding: 6px;
    border-radius: 10px;
    background: var(--gradient-surface);
    border: 1px solid var(--border);
    box-shadow: var(--shadow);
  }
  .sep {
    width: 1px;
    align-self: stretch;
    background: var(--border);
  }
  .action {
    border-color: var(--accent);
  }
</style>
