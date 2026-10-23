<script lang="ts">
  import type { GameOption } from '../net/protocol'
  import { store } from '../state/game.svelte'

  let query = $state('')

  const sections = $derived.by(() => {
    const q = query.trim().toLowerCase()
    const shown = store.options.filter(
      (o) => !q || o.label.toLowerCase().includes(q) || o.help.toLowerCase().includes(q),
    )
    const out = new Map<string, GameOption[]>()
    for (const o of shown) out.set(o.section, [...(out.get(o.section) ?? []), o])
    return [...out]
  })

  const changed = (o: GameOption) => store.option(o.key) !== o.default
</script>

<div class="options">
  <input class="search" type="search" placeholder="Search game settings" bind:value={query} />
  {#if !store.isGm}
    <p class="hint muted">The GM chooses these rules. You can read them here.</p>
  {/if}
  {#each sections as [section, list] (section)}
    <h4>{section}</h4>
    {#each list as o (o.key)}
      <div class="option" class:changed={changed(o)}>
        <div class="head">
          <span class="label">{o.label}</span>
          {#if o.kind === 'bool'}
            <button
              type="button"
              class="switch"
              role="switch"
              aria-checked={store.option<boolean>(o.key)}
              aria-label={o.label}
              disabled={!store.isGm}
              onclick={() => store.setOption(o.key, !store.option<boolean>(o.key))}
            ><span></span></button>
          {:else if o.kind === 'int'}
            <input
              type="number"
              min={o.min}
              max={o.max}
              value={store.option<number>(o.key)}
              disabled={!store.isGm}
              onchange={(e) => {
                const v = Math.round(Number(e.currentTarget.value))
                if (Number.isFinite(v)) store.setOption(o.key, Math.max(o.min, Math.min(o.max, v)))
              }}
            />
          {/if}
        </div>
        {#if o.kind === 'choice'}
          {#if o.choices.length <= 3}
            <div class="segmented">
              {#each o.choices as [value, label] (value)}
                <button
                  type="button"
                  class:active={store.option(o.key) === value}
                  disabled={!store.isGm}
                  onclick={() => store.setOption(o.key, value)}>{label}</button
                >
              {/each}
            </div>
          {:else}
            <select
              value={store.option<string>(o.key)}
              disabled={!store.isGm}
              onchange={(e) => store.setOption(o.key, e.currentTarget.value)}
            >
              {#each o.choices as [value, label] (value)}
                <option {value}>{label}</option>
              {/each}
            </select>
          {/if}
        {/if}
        <p class="help muted">{o.help}</p>
      </div>
    {/each}
  {:else}
    <p class="hint muted">No setting matches.</p>
  {/each}
</div>

<style>
  .options {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 12px;
  }
  .search {
    width: 100%;
  }
  h4 {
    margin: 10px 0 0;
    font-size: 0.72rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-muted);
  }
  .option {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 10px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface-2);
  }
  .option.changed {
    border-color: color-mix(in srgb, var(--accent) 55%, var(--border));
  }
  .head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
  }
  .label {
    font-weight: 600;
  }
  .head input {
    width: 70px;
  }
  .help {
    margin: 0;
    font-size: 0.8rem;
    line-height: 1.35;
  }
  .segmented {
    flex-wrap: wrap;
  }
  .segmented button {
    flex: 1;
  }
  .switch {
    flex: none;
    position: relative;
    width: 38px;
    height: 22px;
    border-radius: 999px;
    border: 1px solid var(--border);
    background: var(--bg);
    cursor: pointer;
    padding: 0;
    transition: background 0.15s;
  }
  .switch span {
    position: absolute;
    top: 2px;
    left: 2px;
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: var(--text-muted);
    transition:
      transform 0.15s,
      background 0.15s;
  }
  .switch[aria-checked='true'] {
    background: var(--gradient-accent);
    border-color: transparent;
  }
  .switch[aria-checked='true'] span {
    transform: translateX(16px);
    background: var(--accent-contrast);
  }
  .switch:disabled,
  button:disabled {
    cursor: default;
    opacity: 0.7;
  }
</style>
