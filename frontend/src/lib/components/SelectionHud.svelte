<script lang="ts">
  import type { MapObject } from '../net/protocol'
  import { store } from '../state/game.svelte'
  import { STATUSES } from '../util/statuses'

  let { onEdit }: { onEdit: (id: string) => void } = $props()

  const token = $derived.by<MapObject | null>(() => {
    void store.objectsVersion
    if (store.selection.length !== 1) return null
    const o = store.objects.get(store.selection[0])
    return o && o.kind === 'token' && store.controls(o) ? o : null
  })

  let showStatuses = $state(false)

  function toggleStatus(id: string) {
    if (!token) return
    const current: string[] = token.props.statuses ?? []
    const next = current.includes(id) ? current.filter((s) => s !== id) : [...current, id]
    store.updateProps(token.id, { statuses: next.length ? next : null })
  }
</script>

{#if token}
  <div class="hud panel">
    <button class="name" onclick={() => onEdit(token.id)} title="Open token settings">
      {token.props.name || 'Token'} ✎
    </button>
    <div class="status-wrap">
      <button class="btn small" onclick={() => (showStatuses = !showStatuses)}>Statuses ▾</button>
      {#if showStatuses}
        <div class="statuses panel">
          {#each STATUSES as s (s.id)}
            <button
              class:on={(token.props.statuses ?? []).includes(s.id)}
              title={s.label}
              onclick={() => toggleStatus(s.id)}>{s.icon}</button
            >
          {/each}
        </div>
      {/if}
    </div>
  </div>
{/if}

<style>
  .hud {
    position: absolute;
    left: 0;
    right: 0;
    bottom: 14px;
    width: max-content;
    max-width: calc(100% - 24px);
    margin: 0 auto;
    z-index: 20;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 6px 10px;
    flex-wrap: wrap;
    justify-content: center;
  }
  .name {
    border: none;
    background: none;
    font-weight: 700;
    cursor: pointer;
    max-width: 160px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .status-wrap {
    position: relative;
  }
  .statuses {
    position: absolute;
    bottom: calc(100% + 8px);
    right: 0;
    display: grid;
    grid-template-columns: repeat(6, 32px);
    gap: 3px;
    padding: 6px;
  }
  .statuses button {
    width: 32px;
    height: 32px;
    border: 1px solid transparent;
    border-radius: 6px;
    background: var(--surface-2);
    cursor: pointer;
    font-size: 1rem;
  }
  .statuses button.on {
    border-color: var(--accent);
    background: color-mix(in srgb, var(--accent) 25%, var(--surface-2));
  }
</style>
