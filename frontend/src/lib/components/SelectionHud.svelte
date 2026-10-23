<script lang="ts">
  import type { Bar, Effect, MapObject } from '../net/protocol'
  import { store } from '../state/game.svelte'
  import { BARS } from '../theme'
  import { STATUSES } from '../util/statuses'

  let { onEdit }: { onEdit: (id: string) => void } = $props()

  const token = $derived.by<MapObject | null>(() => {
    void store.objectsVersion
    if (store.selection.length !== 1) return null
    const o = store.objects.get(store.selection[0])
    // Cards are tokens too, but have no hit points or conditions.
    return o && o.kind === 'token' && o.props.shape !== 'card' && store.controls(o) ? o : null
  })

  let showStatuses = $state(false)
  let showEffects = $state(false)
  const effects = $derived<Effect[]>(token?.props.effects ?? [])

  function remaining(e: Effect): string {
    if (!e.ending) return e.duration || 'until removed'
    const by = store.objects.get(e.ending.of)?.props.name ?? 'its creator'
    return `${e.ending.rounds} round${e.ending.rounds === 1 ? '' : 's'} (${e.ending.when} of ${by}'s turn)`
  }

  /** "12" sets the value, "-5" / "+3" change it relative to the current one, empty clears it.
   *  On the HP of a token with a 5e sheet, "-12 fire", "+8" and "+5 temp" go through the
   *  damage rules instead (resistances, concentration, 0 HP), as one undoable action. */
  function applyValue(key: string, raw: string, input: HTMLInputElement) {
    if (!token) return
    const bar: Bar = { value: null, max: null, ...(token.props[key] ?? {}) }
    const text = raw.trim()
    const rules = key === 'bar1' && store.character(token.props.represents)?.sheet
    const change = rules ? /^([+-])\s*(\d+)\s*([a-z]*)$/i.exec(text) : null
    if (change) {
      const [, sign, amount, word] = change
      const type = word.toLowerCase()
      if (sign === '-') store.applyHp([token.id], 'damage', Number(amount), type || null)
      else store.applyHp([token.id], type === 'temp' ? 'temp' : 'healing', Number(amount))
      input.value = bar.value === null ? '' : String(bar.value)
      return
    }
    let value: number | null
    if (text === '') value = null
    else if (/^[+-]\d+(\.\d+)?$/.test(text)) value = (bar.value ?? 0) + Number(text)
    else if (Number.isFinite(Number(text))) value = Number(text)
    else {
      input.value = bar.value === null ? '' : String(bar.value)
      return
    }
    const next = { ...bar, value }
    store.updateProps(token.id, { [key]: next.value === null && next.max === null ? null : next })
  }

  function toggleStatus(id: string) {
    if (!token) return
    const current: string[] = token.props.statuses ?? []
    const next = current.includes(id) ? current.filter((s) => s !== id) : [...current, id]
    store.updateProps(token.id, { statuses: next.length ? next : null })
  }
</script>

{#if token}
  <div class="hud-wrap">
    <!-- HP / Temp. HP bubbles: type a value, or -5 / +3 to change it. -->
    <div class="bubbles">
      {#each BARS as b (b.key)}
        {@const bar = token.props[b.key] as Bar | undefined}
        <div class="bubble" style:--c={b.color}>
          <input
            value={bar?.value ?? ''}
            placeholder="–"
            inputmode="decimal"
            title={b.key === 'bar1' && store.character(token.props.represents)?.sheet
              ? `${b.label}: -12 fire = damage with resistances, +8 = healing, +5 temp = temporary HP`
              : `${b.label} (type -5 or +3 to subtract or add)`}
            aria-label={b.label}
            onfocus={(e) => e.currentTarget.select()}
            onkeydown={(e) => e.key === 'Enter' && e.currentTarget.blur()}
            onchange={(e) => applyValue(b.key, e.currentTarget.value, e.currentTarget)}
          />
          {#if bar?.max != null}<span class="max" title={`${b.label} max`}>{bar.max}</span>{/if}
        </div>
      {/each}
    </div>
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
      <div class="status-wrap">
        <button class="btn small" onclick={() => (showEffects = !showEffects)}>
          Effects{effects.length ? ` (${effects.length})` : ''} ▾
        </button>
        {#if showEffects}
          <div class="effects panel">
            {#each effects as e (e.id)}
              <div class="effect" title={remaining(e)}>
                <span class="effect-name">{e.name}</span>
                <small class="muted">{remaining(e)}</small>
                <button class="mini" aria-label={`Remove ${e.name}`} onclick={() => store.removeEffect(token.id, e.id)}>✕</button>
              </div>
            {:else}
              <p class="muted none">No effects.</p>
            {/each}
            {#if token.props.concentrating}
              <button class="btn small" onclick={() => store.endConcentration(token.id)}>
                End concentration ({token.props.concentrating.name})
              </button>
            {/if}
            <button class="btn small primary" onclick={() => ((store.effectTargets = [...store.selection]), (showEffects = false))}>
              + Add effect
            </button>
          </div>
        {/if}
      </div>
    </div>
  </div>
{/if}

<style>
  .effects {
    position: absolute;
    bottom: calc(100% + 6px);
    right: 0;
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 8px;
    width: 280px;
  }
  .effect {
    display: grid;
    grid-template-columns: 1fr auto;
    align-items: center;
    column-gap: 6px;
  }
  .effect small {
    grid-column: 1;
    font-size: 0.7rem;
  }
  .effect .mini {
    grid-row: 1 / span 2;
    grid-column: 2;
  }
  .effect-name {
    font-weight: 600;
  }
  .none {
    margin: 0;
    font-size: 0.8rem;
  }
  .mini {
    border: none;
    background: none;
    color: var(--text-muted);
    cursor: pointer;
  }
  .hud-wrap {
    position: absolute;
    left: 0;
    right: 0;
    bottom: 14px;
    width: max-content;
    max-width: calc(100% - 24px);
    margin: 0 auto;
    z-index: 20;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 10px;
  }
  .bubbles {
    display: flex;
    gap: 14px;
  }
  .bubble {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
  }
  .bubble input {
    width: 46px;
    height: 46px;
    padding: 0;
    border-radius: 50%;
    border: 2px solid var(--c);
    background: color-mix(in srgb, var(--c) 18%, var(--surface));
    box-shadow:
      0 0 14px color-mix(in srgb, var(--c) 45%, transparent),
      var(--shadow);
    color: var(--text);
    font-weight: 800;
    font-size: 0.95rem;
    text-align: center;
  }
  .bubble input::placeholder {
    color: var(--text-muted);
  }
  .bubble input:focus {
    outline: none;
    border-color: var(--text);
  }
  .max {
    padding: 2px 7px;
    border-radius: 999px;
    border: 1px solid color-mix(in srgb, var(--c) 45%, var(--border));
    background: var(--surface);
    font-size: 0.7rem;
    font-weight: 700;
    line-height: 1.2;
    color: var(--c);
  }
  .hud {
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
    z-index: 1;
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
