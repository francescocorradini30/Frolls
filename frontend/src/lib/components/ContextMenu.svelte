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
      <button onclick={() => act(() => onEdit(first.id))}>Modifica…</button>
    {/if}
    {#if anyToken}
      <button onclick={() => act(() => store.addToTurnOrder(ids))}>Aggiungi all'iniziativa</button>
      <button onclick={() => act(toggleName)}>{first.props.show_name === false ? 'Mostra' : 'Nascondi'} nome</button>
    {/if}
    <button onclick={() => act(() => store.send({ type: 'obj.order', ids, to: 'front' }))}>Porta in primo piano</button>
    <button onclick={() => act(() => store.send({ type: 'obj.order', ids, to: 'back' }))}>Porta in fondo</button>
    {#if store.isGm}
      <hr />
      <span class="label">Sposta sul livello</span>
      <button disabled={first.layer === 'map'} onclick={() => act(() => moveTo('map'))}>🗺 Mappa</button>
      <button disabled={first.layer === 'objects'} onclick={() => act(() => moveTo('objects'))}>♟ Oggetti e token</button>
      <button disabled={first.layer === 'gm'} onclick={() => act(() => moveTo('gm'))}>👁 GM</button>
      <hr />
      <button onclick={() => act(onDuplicate)}>Duplica (Ctrl+D)</button>
    {/if}
    {#if deletable}
      <button class="danger" onclick={() => act(() => store.deleteObjects(ids))}>Elimina (Canc)</button>
    {/if}
  {:else}
    <button onclick={() => act(() => (store.tool = 'select'))}>Strumento selezione</button>
    <button onclick={() => act(() => (store.tool = 'ruler'))}>Righello</button>
    <p class="muted hint">Tieni premuto su un punto vuoto per fare un ping{store.isGm ? ' (Maiusc: porta lì la vista di tutti)' : ''}.</p>
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
