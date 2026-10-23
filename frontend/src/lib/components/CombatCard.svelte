<script lang="ts">
  import type { CardRow, ChatMessage, CombatCard, Roll } from '../net/protocol'
  import { store } from '../state/game.svelte'
  import { STATUSES } from '../util/statuses'
  import RollView from './RollView.svelte'

  let { msg, card }: { msg: ChatMessage; card: CombatCard } = $props()

  let open = $state(false)
  let showAll = $state(false)
  /** Row whose "+ Damage" field is open. */
  let adding = $state<string | null>(null)
  let extra = $state('')

  const inline = $derived(msg.roll?.inline ?? [])
  const undone = $derived(!!card.undone_by)
  const mine = $derived(store.isGm || card.author_id === store.me?.id)
  const rows = $derived(showAll ? card.rows : card.rows.slice(0, 3))
  const targets = $derived(card.rows.filter((r) => r.token_id))

  const OUTCOME: Record<string, { label: string; cls: string }> = {
    hit: { label: 'HIT', cls: 'hit' },
    'critical hit': { label: 'CRIT', cls: 'crit' },
    miss: { label: 'MISS', cls: 'miss' },
    'critical miss': { label: 'MISS', cls: 'miss' },
    rolled: { label: 'ROLLED', cls: 'rolled' },
  }

  /** Outcome badge of the whole card: the best result among its targets. */
  const badge = $derived.by(() => {
    const order = ['critical hit', 'hit', 'rolled', 'miss', 'critical miss']
    const best = order.find((o) => card.rows.some((r) => r.outcome === o))
    return best ? OUTCOME[best] : null
  })

  const heading = $derived.by(() => {
    if (!targets.length) return card.actor_name
    const names = targets.length > 2 ? `${targets.length} targets` : targets.map((r) => r.name).join(', ')
    return `${card.actor_name} → ${names}`
  })

  function roll(i: number | null | undefined): Roll | null {
    return typeof i === 'number' ? (inline[i] ?? null) : null
  }

  function icon(status: string): string {
    return STATUSES.find((s) => s.id === status)?.icon ?? status
  }

  function damageText(r: CardRow): string {
    const parts = (r.damage ?? []).filter((d) => !card.undone_seqs.includes(d.seq ?? -1))
    if (r.taken != null) {
      const types = [...new Set(parts.map((d) => d.type).filter(Boolean))].join(', ')
      return `−${r.taken}${types ? ` ${types}` : ''}`
    }
    return parts.map((d) => `${d.total} ${d.type}`.trim()).join(' + ')
  }

  function health(r: CardRow): string {
    if (r.hp) return `${r.hp.current}/${r.hp.max}${r.hp.temp ? ` +${r.hp.temp}` : ''}`
    return r.state && r.monster ? r.state : ''
  }

  function submitExtra(r: CardRow) {
    const m = /^\s*([0-9d+\-*\s()]+?)\s*([a-z]*)\s*$/i.exec(extra)
    if (m && r.token_id) store.addDamage(msg.id, r.token_id, m[1].replace(/\s+/g, ''), m[2] || null)
    adding = null
    extra = ''
  }
</script>

<div class="card" class:undone class:hidden={card.hidden}>
  <header>
    <button class="title" onclick={() => (open = !open)} aria-expanded={open} title="Show the dice">
      <span class="dot" style:background={msg.color}></span>
      <span class="who">{heading}</span>
      <span class="action">· {card.action}</span>
    </button>
    {#if badge}<span class="badge-out {badge.cls}">{badge.label}</span>{/if}
    {#if mine && card.seqs.length}
      {#if undone}
        <button class="icon" title="Redo" aria-label="Redo" onclick={() => store.redoCard(msg.id)}>↷</button>
      {:else}
        <button class="icon" title="Undo this action" aria-label="Undo" onclick={() => store.undoCard(msg.id)}>↶</button>
      {/if}
    {/if}
  </header>

  {#each rows as r, i (i)}
    <div class="row">
      {#if r.token_id}<span class="name">{r.name}</span>{/if}
      {#if r.outcome && OUTCOME[r.outcome] && targets.length > 1}
        <span class="mini {OUTCOME[r.outcome].cls}">{OUTCOME[r.outcome].label}</span>
      {/if}
      {#if r.total != null && !r.token_id}<span class="num">{r.total}</span>{/if}
      {#if damageText(r)}<span class="dmg" class:applied={r.taken != null}>{damageText(r)}</span>{/if}
      {#if health(r)}<span class="hp">{health(r)}</span>{/if}
      {#each r.added ?? [] as s (s)}<span class="status" title={s}>{icon(s)}</span>{/each}
      {#if r.conc}<span class="conc" title="Concentration">◎ {r.conc}</span>{/if}
      {#if mine && !undone && r.token_id && (r.outcome === 'hit' || r.outcome === 'critical hit')}
        {#if adding === r.token_id}
          <form class="extra" onsubmit={(e) => (e.preventDefault(), submitExtra(r))}>
            <!-- svelte-ignore a11y_autofocus -->
            <input bind:value={extra} placeholder="3d6 piercing" aria-label="Extra damage" autofocus onblur={() => !extra && (adding = null)} />
          </form>
        {:else}
          <button class="plus" title="Add damage: Sneak Attack, Smite, Hex… (doubled on a critical)" onclick={() => ((adding = r.token_id), (extra = ''))}>＋ Damage</button>
        {/if}
      {/if}
    </div>
    {#if r.notes?.length}<div class="sub">{r.notes.join(' · ')}</div>{/if}
  {/each}
  {#if card.rows.length > 3 && !showAll}
    <button class="more" onclick={() => (showAll = true)}>+{card.rows.length - 3} more ▸</button>
  {/if}
  {#if card.notes?.length}<div class="sub">{card.notes.join(' · ')}</div>{/if}
  {#if card.warnings?.length}<div class="warn">{card.warnings.join(' · ')}</div>{/if}
  {#if undone}<div class="sub">Undone by {card.undone_by}</div>{/if}

  {#if open}
    <div class="details">
      {#each card.rows as r, i (i)}
        {@const d20 = roll(r.d20)}
        {#if d20}
          <div class="label">
            Attack{r.token_id ? ` vs ${r.name}` : ''}{r.ac != null ? ` · AC ${r.ac}` : ''}{r.distance ? ` · ${r.distance} ft` : ''}
          </div>
          <RollView roll={d20} />
        {/if}
        {#each r.damage ?? [] as d, j (j)}
          {@const dr = roll(d.roll)}
          {#if dr}
            <div class="label">{d.extra ? 'Extra damage' : 'Damage'} {d.type}</div>
            <RollView roll={dr} />
          {/if}
        {/each}
      {/each}
      {#if card.reasons?.length}<div class="sub">{card.reasons.join(' · ')}</div>{/if}
      {#if card.text}<p class="text">{card.text}</p>{/if}
    </div>
  {/if}
</div>

<style>
  .card {
    margin-top: 4px;
    border: 1px solid var(--border);
    border-radius: 10px;
    background: var(--gradient-surface);
    overflow: hidden;
  }
  .card.hidden {
    border-style: dashed;
  }
  .card.undone {
    opacity: 0.55;
  }
  .card.undone .row {
    text-decoration: line-through;
  }
  header {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 8px;
  }
  .title {
    flex: 1;
    min-width: 0;
    display: flex;
    align-items: center;
    gap: 6px;
    border: none;
    background: none;
    padding: 0;
    cursor: pointer;
    text-align: left;
  }
  .dot {
    flex: none;
    width: 8px;
    height: 8px;
    border-radius: 50%;
  }
  .who {
    font-weight: 700;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .action {
    color: var(--text-muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .badge-out,
  .mini {
    flex: none;
    font-size: 0.68rem;
    font-weight: 800;
    letter-spacing: 0.06em;
    padding: 2px 7px;
    border-radius: 999px;
    border: 1px solid currentColor;
  }
  .mini {
    font-size: 0.6rem;
    padding: 0 5px;
  }
  .hit {
    color: var(--success);
  }
  .crit {
    color: var(--highlight);
    box-shadow: 0 0 10px color-mix(in srgb, var(--highlight) 45%, transparent);
  }
  .miss {
    color: var(--text-muted);
  }
  .rolled {
    color: var(--accent-3);
  }
  .icon {
    flex: none;
    border: 1px solid var(--border);
    background: var(--surface-3);
    border-radius: 6px;
    width: 24px;
    height: 22px;
    padding: 0;
    cursor: pointer;
    color: var(--text);
  }
  .icon:hover {
    border-color: var(--accent);
  }
  .row {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 6px;
    padding: 3px 10px;
    font-size: 0.86rem;
    border-top: 1px solid color-mix(in srgb, var(--border) 60%, transparent);
  }
  .name {
    font-weight: 600;
  }
  .num {
    font-weight: 800;
  }
  .dmg {
    font-weight: 700;
    color: var(--text);
  }
  .dmg.applied {
    color: var(--danger);
  }
  .hp {
    font-size: 0.78rem;
    color: var(--text-muted);
  }
  .status {
    font-size: 0.85rem;
  }
  .conc {
    font-size: 0.75rem;
    color: var(--accent-3);
  }
  .plus,
  .more {
    margin-left: auto;
    border: 1px dashed var(--border);
    background: none;
    border-radius: 999px;
    font-size: 0.72rem;
    padding: 1px 8px;
    cursor: pointer;
    color: var(--text-muted);
  }
  .plus:hover,
  .more:hover {
    color: var(--text);
    border-color: var(--accent);
  }
  .more {
    margin: 2px 10px 4px;
  }
  .extra {
    margin-left: auto;
  }
  .extra input {
    width: 120px;
    padding: 2px 6px;
    font-size: 0.78rem;
  }
  .sub,
  .warn {
    padding: 0 10px 4px;
    font-size: 0.74rem;
    color: var(--text-muted);
  }
  .warn {
    color: var(--danger);
  }
  .details {
    border-top: 1px solid var(--border);
    padding: 6px 8px;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .label {
    font-size: 0.72rem;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .text {
    margin: 4px 0 0;
    font-size: 0.78rem;
    color: var(--text-muted);
    white-space: pre-wrap;
  }
</style>
