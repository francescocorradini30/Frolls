<script lang="ts">
  import { untrack } from 'svelte'
  import { store } from '../state/game.svelte'
  import { EFFECT_PRESETS } from '../util/effects'

  let { targets, onClose }: { targets: string[]; onClose: () => void } = $props()

  const tokens = $derived.by(() => {
    void store.objectsVersion
    return [...store.objects.values()].filter((o) => o.kind === 'token')
  })
  const sources = $derived(tokens.filter((o) => store.isGm || store.controls(o)))
  const targetNames = $derived(
    targets.map((id) => store.objects.get(id)?.props.name ?? 'Token').join(', '),
  )

  // Who creates the effect: whose turn it is, or a token I control.
  const firstSource = untrack(() => {
    const current = store.game?.turn_order[0]?.object_id
    if (current && store.objects.has(current) && (store.isGm || store.controls(store.objects.get(current)!))) return current
    return sources[0]?.id ?? ''
  })

  let preset = $state(EFFECT_PRESETS[0].key)
  let sourceId = $state<string>(firstSource)
  let concentrate = $state(true)
  let dc = $state<number>(13)

  const chosen = $derived(EFFECT_PRESETS.find((p) => p.key === preset)!)

  // The spell DC of the source's sheet, when there is one.
  $effect(() => {
    const src = store.objects.get(sourceId)
    const spellDc = store.character(src?.props.represents)?.derived?.spell_dc
    if (spellDc) dc = spellDc
  })

  function apply() {
    store.applyEffect(targets, preset, sourceId || null, chosen.save ? dc : null, concentrate)
    onClose()
  }
</script>

<div class="backdrop" role="presentation" onclick={onClose}>
  <div
    class="dialog panel"
    role="dialog"
    aria-modal="true"
    aria-label="Add effect"
    tabindex="-1"
    onclick={(e) => e.stopPropagation()}
    onkeydown={(e) => e.key === 'Escape' && onClose()}
  >
    <header><strong>Add effect</strong><span class="muted">on {targetNames}</span></header>
    <div class="body">
      <label class="field">
        <span>Effect</span>
        <select bind:value={preset} aria-label="Effect">
          {#each EFFECT_PRESETS as p (p.key)}<option value={p.key}>{p.label}</option>{/each}
        </select>
      </label>
      <p class="note muted">{chosen.note}</p>
      <label class="field">
        <span>Created by (its turns time the effect)</span>
        <select bind:value={sourceId} aria-label="Created by">
          <option value="">— nobody (until removed) —</option>
          {#each sources as o (o.id)}<option value={o.id}>{o.props.name || 'Token'}</option>{/each}
        </select>
      </label>
      {#if chosen.concentration}
        <label class="check"><input type="checkbox" bind:checked={concentrate} /> Needs concentration</label>
      {/if}
      {#if chosen.save}
        <label class="field">
          <span>Save DC (repeated at the end of each of its turns)</span>
          <input type="number" min="1" max="40" bind:value={dc} aria-label="Save DC" />
        </label>
      {/if}
    </div>
    <footer>
      <button class="btn" onclick={onClose}>Cancel</button>
      <button class="btn primary" onclick={apply}>Apply</button>
    </footer>
  </div>
</div>

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    z-index: 105;
    display: grid;
    place-items: center;
    padding: 16px;
    background: var(--backdrop);
  }
  .dialog {
    width: min(400px, 100%);
    display: flex;
    flex-direction: column;
  }
  header,
  footer {
    display: flex;
    align-items: baseline;
    gap: 8px;
    padding: 10px 14px;
  }
  header {
    border-bottom: 1px solid var(--border);
    flex-wrap: wrap;
  }
  header .muted {
    font-size: 0.8rem;
  }
  footer {
    border-top: 1px solid var(--border);
    justify-content: flex-end;
  }
  .body {
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding: 14px;
  }
  .note {
    margin: -4px 0 0;
    font-size: 0.8rem;
  }
  .check {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 0.85rem;
  }
</style>
