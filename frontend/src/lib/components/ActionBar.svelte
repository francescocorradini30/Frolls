<script lang="ts">
  import type { Character, MapObject, SheetAttack, SheetSpell, TurnAction, TurnEntry } from '../net/protocol'
  import { feetLabel } from '../canvas/rules'
  import { store } from '../state/game.svelte'

  let { token }: { token: MapObject } = $props()

  interface Slot {
    key: string
    glyph: string
    name: string
    info: string
    /** Slot pips for leveled spells: [left, max]. */
    pips?: [number, number]
    dim: boolean
    run: () => void
  }

  const character = $derived<Character | undefined>(store.character(token.props.represents))
  const sheet = $derived(character?.sheet ?? null)
  const metric = $derived(store.measurement === 'metric')

  const entry = $derived.by<TurnEntry | null>(() => {
    const g = store.game
    if (!g || (g.settings.round ?? 0) < 1) return null
    return g.turn_order.find((e) => e.object_id === token.id) ?? null
  })
  const myTurn = $derived(!!entry && store.game?.turn_order[0]?.id === entry.id)

  function signed(n: number | null | undefined): string {
    return n == null ? '' : n >= 0 ? `+${n}` : String(n)
  }

  function attackSlot(a: SheetAttack): Slot {
    const d = character?.derived?.attacks[a.id]
    const ranged = a.range_normal != null && a.reach == null
    const dmg = d?.parts?.map(([f, t]) => `${f} ${t}`.trim()).join(' + ') || d?.damage || ''
    const hit = a.kind === 'save' ? `DC ${d?.dc ?? '?'} ${a.save?.toUpperCase() ?? ''}` : signed(d?.to_hit)
    return {
      key: `a:${a.id}`,
      glyph: a.kind === 'save' ? '✷' : ranged ? '🏹' : '⚔',
      name: a.name,
      info: [hit, dmg, a.cost && a.cost !== 'action' ? a.cost : ''].filter(Boolean).join(' · '),
      dim: false,
      run: () => startAttack(a),
    }
  }

  function spellSlot(sp: SheetSpell): Slot {
    const slots = sheet?.spellcasting.slots[String(sp.level)]
    const left = slots ? slots.max - slots.used : 0
    const what = sp.heal ? `${sp.damage} ${sp.heal === 'temp' ? 'temp HP' : 'healing'}` : `${sp.damage} ${sp.damage_type}`.trim()
    return {
      key: `s:${sp.id}`,
      glyph: sp.heal ? '♥' : '✦',
      name: sp.name,
      info: [sp.level ? `Lv ${sp.level}` : 'Cantrip', what, sp.save ? `${sp.save.toUpperCase()} save` : ''].filter(Boolean).join(' · '),
      pips: sp.level ? [left, slots?.max ?? 0] : undefined,
      dim: sp.level > 0 && left <= 0,
      run: () => startSpell(sp),
    }
  }

  const slots = $derived.by<Slot[]>(() => {
    if (!sheet) return []
    const spells = sheet.spells.filter((sp) => sp.prepared && (sp.damage || sp.effect))
    const leveled = spells.filter((sp) => sp.level > 0).sort((a, b) => a.level - b.level)
    const cantrips = spells.filter((sp) => sp.level === 0)
    return [...sheet.attacks.map(attackSlot), ...leveled.map(spellSlot), ...cantrips.map(spellSlot)].slice(0, 9)
  })

  const allSpells = $derived(
    (sheet?.spells ?? []).filter((sp) => sp.prepared || sp.level === 0).sort((a, b) => a.level - b.level),
  )
  let spellsOpen = $state(false)

  function startAttack(a: SheetAttack) {
    store.startTargeting({
      actorId: token.id,
      action: { kind: 'attack', id: a.id },
      label: a.name,
      multi: a.kind === 'save' || !!a.area,
      range: { reach: a.range_normal == null ? (a.reach ?? 5) : (a.reach ?? null), normal: a.range_normal ?? null, long: a.range_long ?? null },
    })
  }

  function startSpell(sp: SheetSpell) {
    spellsOpen = false
    if (!character) return
    const feet = sp.range_ft ?? null
    store.startTargeting({
      actorId: token.id,
      action: { kind: 'spell', id: sp.id, slot: null },
      label: sp.name,
      multi: !sp.attack,
      range: { reach: feet != null && feet <= 5 ? 5 : null, normal: feet && feet > 5 ? feet : null, long: null },
      spell: { characterId: character.id, spellId: sp.id, slot: null },
      allowNone: !sp.attack,
    })
  }

  function togglePip(what: TurnAction) {
    if (entry) store.turnUse(entry.id, what, !entry.used?.[what])
  }

  function endTurn() {
    store.send({ type: 'turn.next' })
  }

  function onKey(e: KeyboardEvent) {
    const el = e.target as HTMLElement
    if (el.closest('input, textarea, select, [contenteditable="true"]')) return
    if (e.ctrlKey && e.key === 'Enter' && myTurn) {
      e.preventDefault()
      endTurn()
      return
    }
    if (e.ctrlKey || e.metaKey || e.altKey || store.targeting) return
    const n = Number(e.key)
    if (Number.isInteger(n) && n >= 1 && n <= 9 && slots[n - 1]) {
      e.preventDefault()
      slots[n - 1].run()
    }
  }

  const PIPS: { what: TurnAction; label: string; title: string }[] = [
    { what: 'action', label: 'A', title: 'Action' },
    { what: 'bonus_action', label: 'B', title: 'Bonus action' },
    { what: 'reaction', label: 'R', title: 'Reaction' },
  ]
</script>

<svelte:window onkeydown={onKey} />

{#if sheet}
  <div class="bar panel" role="toolbar" aria-label="Actions">
    {#if entry}
      <div class="economy">
        {#each PIPS as p (p.what)}
          {@const used = !!entry.used?.[p.what]}
          {@const extra = Number((entry.used as Record<string, unknown> | null)?.[`${p.what}_extra`] ?? 0)}
          <button
            class="pip"
            class:used
            class:over={extra > 0}
            title={`${p.title}: ${used ? 'used' : 'available'}${extra ? ` (spent ${extra + 1} times)` : ''}`}
            onclick={() => togglePip(p.what)}>{p.label}</button
          >
        {/each}
        <div class="move" class:over={(entry.moved ?? 0) > sheet.speed} title="Movement this turn">
          <div class="track"><div class="fill" style:width={`${Math.min(100, ((entry.moved ?? 0) / Math.max(1, sheet.speed)) * 100)}%`}></div></div>
          <span>{feetLabel(entry.moved ?? 0, metric)} / {feetLabel(sheet.speed, metric)}</span>
        </div>
        {#if (sheet.extra_attack ?? 1) > 1}
          <span class="atk" title="Attacks of the Attack action">Atk {(entry as TurnEntry & { attacks?: number }).attacks ?? 0}/{sheet.extra_attack}</span>
        {/if}
      </div>
    {/if}

    <div class="slots">
      {#each slots as slot, i (slot.key)}
        <button class="slot" class:dim={slot.dim} title={`${slot.name}\n${slot.info}`} onclick={slot.run}>
          <span class="n">{i + 1}</span>
          <span class="glyph">{slot.glyph}</span>
          <span class="name">{slot.name}</span>
          {#if slot.pips}
            <span class="spips">{#each Array(slot.pips[1]) as _, k (k)}<i class:on={k < slot.pips[0]}></i>{/each}</span>
          {/if}
        </button>
      {/each}
    </div>

    {#if allSpells.length}
      <div class="pop-wrap">
        <button class="btn small" onclick={() => (spellsOpen = !spellsOpen)} aria-expanded={spellsOpen}>✦ Spells ▾</button>
        {#if spellsOpen}
          <div class="pop panel">
            {#each allSpells as sp (sp.id)}
              {@const s = spellSlot(sp)}
              <button class="spell" class:dim={s.dim} onclick={s.run} title={sp.description}>
                <span class="glyph">{s.glyph}</span>
                <span class="name">{sp.name}</span>
                <small class="muted">{s.info}</small>
              </button>
            {/each}
          </div>
        {/if}
      </div>
    {/if}

    {#if myTurn}
      <button class="btn small primary end" onclick={endTurn} title="End my turn (Ctrl+Enter)">End turn ⏎</button>
    {/if}
  </div>
{/if}

<style>
  .bar {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 6px 8px;
    max-width: min(92vw, 980px);
  }
  .economy {
    display: flex;
    align-items: center;
    gap: 5px;
    padding-right: 10px;
    border-right: 1px solid var(--border);
  }
  .pip {
    width: 24px;
    height: 24px;
    border-radius: 50%;
    border: 1.5px solid var(--success);
    background: color-mix(in srgb, var(--success) 22%, transparent);
    color: var(--text);
    font-size: 0.7rem;
    font-weight: 800;
    padding: 0;
    cursor: pointer;
  }
  .pip.used {
    border-color: var(--border);
    background: var(--surface-3);
    color: var(--text-muted);
  }
  .pip.over {
    box-shadow: 0 0 0 2px var(--danger);
  }
  .move {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 92px;
    font-size: 0.68rem;
    color: var(--text-muted);
  }
  .track {
    height: 5px;
    border-radius: 3px;
    background: var(--surface-3);
    overflow: hidden;
  }
  .fill {
    height: 100%;
    background: var(--gradient-accent);
  }
  .move.over .fill {
    background: var(--danger);
  }
  .atk {
    font-size: 0.72rem;
    font-weight: 700;
    color: var(--text-muted);
  }
  .slots {
    display: flex;
    gap: 5px;
    overflow-x: auto;
  }
  .slot {
    position: relative;
    flex: none;
    width: 62px;
    height: 54px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 1px;
    border: 1px solid var(--border);
    border-radius: 10px;
    background: var(--surface-2);
    cursor: pointer;
    padding: 2px 3px;
  }
  .slot:hover {
    border-color: var(--accent);
    box-shadow: 0 0 12px color-mix(in srgb, var(--accent) 35%, transparent);
  }
  .slot.dim {
    opacity: 0.5;
  }
  .n {
    position: absolute;
    top: 2px;
    left: 5px;
    font-size: 0.6rem;
    color: var(--text-muted);
  }
  .glyph {
    font-size: 1.05rem;
    line-height: 1;
  }
  .name {
    max-width: 100%;
    font-size: 0.64rem;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .spips {
    display: flex;
    gap: 2px;
  }
  .spips i {
    width: 5px;
    height: 5px;
    border-radius: 50%;
    background: var(--surface-4);
  }
  .spips i.on {
    background: var(--accent-3);
  }
  .pop-wrap {
    position: relative;
  }
  .pop {
    position: absolute;
    bottom: calc(100% + 8px);
    right: 0;
    width: 280px;
    max-height: 340px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 3px;
    padding: 6px;
    z-index: 5;
  }
  .spell {
    display: grid;
    grid-template-columns: 22px 1fr;
    grid-template-rows: auto auto;
    text-align: left;
    border: 1px solid transparent;
    background: none;
    border-radius: 8px;
    padding: 4px 6px;
    cursor: pointer;
  }
  .spell:hover {
    border-color: var(--accent);
    background: var(--surface-3);
  }
  .spell .glyph {
    grid-row: span 2;
  }
  .spell small {
    font-size: 0.7rem;
  }
  .spell.dim {
    opacity: 0.55;
  }
  .end {
    margin-left: auto;
    white-space: nowrap;
  }
</style>
