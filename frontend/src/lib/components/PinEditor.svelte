<script lang="ts">
  import { untrack } from 'svelte'
  import type { MapObject } from '../net/protocol'
  import { store } from '../state/game.svelte'
  import { TOKEN_COLORS } from '../theme'
  import ColorSwatches from './ColorSwatches.svelte'

  let { obj, onClose }: { obj: MapObject; onClose: () => void } = $props()

  const ICONS = ['📍', '⭐', '🏰', '🏠', '⚔️', '💀', '💰', '🗝️', '🚪', '⛺', '🌲', '⚠️', '❓', '📜']

  const start = untrack(() => obj)
  let title = $state<string>(start.props.title ?? '')
  let icon = $state<string>(start.props.icon ?? '📍')
  let color = $state<string>(start.props.color ?? TOKEN_COLORS[0])
  let notes = $state<string>(start.props.notes ?? '')
  let gmNotes = $state<string>(start.props.gm_notes ?? '')
  let showTitle = $state<boolean>(start.props.show_title !== false)
  let visible = $state<boolean>(start.layer !== 'gm')

  function save() {
    store.updateObjects([
      {
        id: obj.id,
        layer: visible ? 'objects' : 'gm',
        props: {
          title: title.trim() || null,
          icon,
          color,
          notes: notes.trim() || null,
          gm_notes: gmNotes.trim() || null,
          show_title: showTitle ? null : false,
        },
      },
    ])
    onClose()
  }

  function remove() {
    store.deleteObjects([obj.id])
    onClose()
  }
</script>

<div class="backdrop" role="presentation" onclick={onClose}>
  <div
    class="dialog panel"
    role="dialog"
    aria-modal="true"
    aria-label="Map pin"
    tabindex="-1"
    onclick={(e) => e.stopPropagation()}
    onkeydown={(e) => e.key === 'Escape' && onClose()}
  >
    <header>
      <strong>{icon} Map pin</strong>
      <button class="icon-btn" aria-label="Close" onclick={onClose}>✕</button>
    </header>
    <div class="body">
      <label class="field"><span>Title</span><input bind:value={title} maxlength="120" placeholder="The Prancing Pony" /></label>
      <div class="field">
        <span>Icon</span>
        <div class="icons">
          {#each ICONS as i (i)}
            <button class="icon" class:on={icon === i} aria-label={`Icon ${i}`} onclick={() => (icon = i)}>{i}</button>
          {/each}
        </div>
      </div>
      <div class="field"><span>Colour</span><ColorSwatches value={color} onchange={(c) => (color = c)} /></div>
      <label class="field"><span>Notes (players see them)</span><textarea rows="4" bind:value={notes}></textarea></label>
      <label class="field"><span>GM notes (hidden from players)</span><textarea rows="3" bind:value={gmNotes}></textarea></label>
      <label class="check"><input type="checkbox" bind:checked={visible} /> Players can see this pin</label>
      <label class="check"><input type="checkbox" bind:checked={showTitle} /> Show the title on the map</label>
    </div>
    <footer>
      <button class="btn danger" onclick={remove}>Delete</button>
      <span class="spacer"></span>
      <button class="btn" onclick={onClose}>Cancel</button>
      <button class="btn primary" onclick={save}>Save</button>
    </footer>
  </div>
</div>

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    z-index: 100;
    display: grid;
    place-items: center;
    padding: 16px;
    background: var(--backdrop);
  }
  .dialog {
    width: min(440px, 100%);
    max-height: 90vh;
    display: flex;
    flex-direction: column;
  }
  header,
  footer {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 14px;
  }
  header {
    justify-content: space-between;
    border-bottom: 1px solid var(--border);
  }
  footer {
    border-top: 1px solid var(--border);
  }
  .spacer {
    flex: 1;
  }
  .body {
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding: 12px 14px;
    overflow-y: auto;
  }
  .field {
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 0.85rem;
  }
  .field > span {
    color: var(--text-muted);
  }
  .icons {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }
  .icon {
    width: 34px;
    height: 34px;
    border-radius: 8px;
    border: 1px solid var(--border);
    background: var(--surface-2);
    cursor: pointer;
    font-size: 1.05rem;
  }
  .icon.on {
    border-color: var(--accent);
    background: color-mix(in srgb, var(--accent) 22%, transparent);
  }
  .check {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 0.85rem;
  }
</style>
