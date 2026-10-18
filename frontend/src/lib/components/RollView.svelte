<script lang="ts">
  import type { Die, Roll, RollTerm } from '../net/protocol'

  let { roll }: { roll: Roll } = $props()

  function dieClass(term: RollTerm, d: Die): string {
    if (d.rerolled || !d.kept) return 'dropped'
    if (term.success_mode) return d.success ? 'crit' : d.failure ? 'fumble' : ''
    if (term.sides === 'F') return ''
    if (d.value >= term.sides) return 'crit'
    if (d.value === 1) return 'fumble'
    return ''
  }

  function fmt(n: number): string {
    return Number.isInteger(n) ? String(n) : n.toFixed(2).replace(/\.?0+$/, '')
  }

  const successMode = $derived(roll.terms.length === 1 && roll.terms[0].success_mode)
</script>

<div class="roll">
  <div class="expr" title={roll.breakdown}>{roll.expression}</div>
  <div class="dice">
    {#each roll.terms as term, ti (ti)}
      <span class="term" title={term.notation}>
        {#each term.dice as d, di (di)}
          <span class="die {dieClass(term, d)}" class:exploded={d.exploded}>{d.value}</span>
        {/each}
      </span>
    {/each}
  </div>
  <div class="total">
    {fmt(roll.total)}
    {#if successMode}<small>{roll.total === 1 ? 'success' : 'successes'}</small>{/if}
  </div>
</div>

<style>
  .roll {
    display: grid;
    grid-template-columns: 1fr auto;
    grid-template-areas: 'expr total' 'dice total';
    gap: 4px 10px;
    padding: 8px 10px;
    margin-top: 4px;
    border-radius: 8px;
    background: var(--bg);
    border: 1px solid var(--border);
  }
  .expr {
    grid-area: expr;
    font-family: ui-monospace, monospace;
    font-size: 0.8rem;
    color: var(--text-muted);
    overflow-wrap: anywhere;
  }
  .dice {
    grid-area: dice;
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .term {
    display: flex;
    flex-wrap: wrap;
    gap: 3px;
  }
  .die {
    min-width: 24px;
    height: 24px;
    padding: 0 5px;
    display: grid;
    place-items: center;
    border-radius: 5px;
    background: var(--surface-3);
    font-weight: 700;
    font-size: 0.85rem;
  }
  .die.crit {
    background: color-mix(in srgb, var(--success) 30%, var(--surface-3));
    color: var(--success);
    box-shadow: inset 0 0 0 1px var(--success);
  }
  .die.fumble {
    background: color-mix(in srgb, var(--danger) 30%, var(--surface-3));
    color: var(--danger);
    box-shadow: inset 0 0 0 1px var(--danger);
  }
  .die.dropped {
    opacity: 0.4;
    text-decoration: line-through;
  }
  .die.exploded::after {
    content: '!';
    font-size: 0.7rem;
    margin-left: 1px;
  }
  .total {
    grid-area: total;
    align-self: center;
    font-size: 1.7rem;
    font-weight: 800;
    background: var(--gradient-accent);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
    text-align: center;
    line-height: 1;
  }
  .total small {
    display: block;
    font-size: 0.65rem;
    font-weight: 600;
    color: var(--text-muted);
  }
</style>
