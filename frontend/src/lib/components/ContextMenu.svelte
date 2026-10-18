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
  const anyToken = $derived(ids.some((id) => store.objects.get(id)?.kind === 'token'))
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

  // Keep the menu on screen.
  const left = $derived(Math.min(x, window.innerWidth - 230))
  const top = $derived(Math.min(y, window.innerHeight - 340))
</script>

<svelte:window onpointerdown={onClose} onkeydown={(e) => e.key === 'Escape' && onClose()} />

<div class="menu panel" role="menu" tabindex="-1" style:left="{left}px" style:top="{top}px" onpointerdown={(e) => e.stopPropagation()}>
  {#if first}
    {#if ids.length === 1 && (first.kind === 'token' || first.kind === 'image')}
      <button onclick={() => act(() => onEdit(first.id))}>Edit…</button>
    {/if}
    {#if anyToken}
      <button onclick={() => act(() => store.addToTurnOrder(ids))}>Add to Turn Order</button>
      <button onclick={() => act(toggleName)}>{first.props.show_name === false ? 'Show' : 'Hide'} name</button>
    {/if}
    <button onclick={() => act(() => store.send({ type: 'obj.order', ids, to: 'front' }))}>To Front</button>
    <button onclick={() => act(() => store.send({ type: 'obj.order', ids, to: 'back' }))}>To Back</button>
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
  hr {
    border: none;
    border-top: 1px solid var(--border);
    margin: 4px 0;
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
