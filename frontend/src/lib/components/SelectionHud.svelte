<script lang="ts">
  import type { Bar, MapObject } from '../net/protocol'
  import { store } from '../state/game.svelte'
  import { BAR_COLORS, STATUSES } from '../util/statuses'

  let { onEdit }: { onEdit: (id: string) => void } = $props()

  const token = $derived.by<MapObject | null>(() => {
    void store.objectsVersion
    if (store.selection.length !== 1) return null
    const o = store.objects.get(store.selection[0])
    return o && o.kind === 'token' && store.controls(o) ? o : null
  })

  let showStatuses = $state(false)

  /** "12" sets the value, "-5" / "+3" change it relative to the current one. */
  function applyBar(index: number, field: 'value' | 'max', raw: string) {
    if (!token) return
    const key = `bar${index + 1}`
    const bar: Bar = { value: null, max: null, ...(token.props[key] ?? {}) }
    const text = raw.trim()
    let next: number | null
    if (text === '') next = null
    else if (/^[+-]\d+(\.\d+)?$/.test(text) && field === 'value') next = (bar.value ?? 0) + Number(text)
    else if (Number.isFinite(Number(text))) next = Number(text)
    else return
    const updated = { ...bar, [field]: next }
    store.updateProps(token.id, { [key]: updated.value === null && updated.max === null ? null : updated })
  }

  function toggleStatus(id: string) {
    if (!token) return
    const current: string[] = token.props.statuses ?? []
    const next = current.includes(id) ? current.filter((s) => s !== id) : [...current, id]
    store.updateProps(token.id, { statuses: next.length ? next : null })
  }
</script>

{#if token}
  <div class="hud panel">
    <button class="name" onclick={() => onEdit(token.id)} title="Apri impostazioni token">
      {token.props.name || 'Token'} ✎
    </button>
    {#each [0, 1, 2] as i (i)}
      {@const bar = token.props[`bar${i + 1}`]}
      <div class="bar" style:--c={BAR_COLORS[i]}>
        <input
          value={bar?.value ?? ''}
          placeholder="—"
          title="Valore (scrivi -5 o +3 per sottrarre/aggiungere)"
          onkeydown={(e) => e.key === 'Enter' && e.currentTarget.blur()}
          onchange={(e) => applyBar(i, 'value', e.currentTarget.value)}
        />
        <span>/</span>
        <input
          value={bar?.max ?? ''}
          placeholder="max"
          title="Massimo"
          onkeydown={(e) => e.key === 'Enter' && e.currentTarget.blur()}
          onchange={(e) => applyBar(i, 'max', e.currentTarget.value)}
        />
      </div>
    {/each}
    <div class="status-wrap">
      <button class="btn small" onclick={() => (showStatuses = !showStatuses)}>Stati ▾</button>
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
  .bar {
    display: flex;
    align-items: center;
    gap: 2px;
    padding-left: 8px;
    border-left: 3px solid var(--c);
  }
  .bar input {
    width: 46px;
    padding: 4px;
    text-align: center;
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
