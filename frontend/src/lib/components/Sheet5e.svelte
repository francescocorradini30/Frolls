<script lang="ts">
  import type { AbilityKey, Character, Sheet, SheetAttack, SheetRollKind, SheetSpell } from '../net/protocol'
  import { store } from '../state/game.svelte'
  import { EFFECT_PRESETS } from '../util/effects'
  import { uid } from '../util/ids'

  let { character }: { character: Character } = $props()

  const ABILITIES: { key: AbilityKey; short: string; name: string }[] = [
    { key: 'str', short: 'STR', name: 'Strength' },
    { key: 'dex', short: 'DEX', name: 'Dexterity' },
    { key: 'con', short: 'CON', name: 'Constitution' },
    { key: 'int', short: 'INT', name: 'Intelligence' },
    { key: 'wis', short: 'WIS', name: 'Wisdom' },
    { key: 'cha', short: 'CHA', name: 'Charisma' },
  ]
  // Mirror of SKILLS in backend/app/rules5e/data.py.
  const SKILLS: [string, AbilityKey][] = [
    ['acrobatics', 'dex'], ['animal_handling', 'wis'], ['arcana', 'int'], ['athletics', 'str'],
    ['deception', 'cha'], ['history', 'int'], ['insight', 'wis'], ['intimidation', 'cha'],
    ['investigation', 'int'], ['medicine', 'wis'], ['nature', 'int'], ['perception', 'wis'],
    ['performance', 'cha'], ['persuasion', 'cha'], ['religion', 'int'], ['sleight_of_hand', 'dex'],
    ['stealth', 'dex'], ['survival', 'wis'],
  ]
  const DAMAGE_TYPES = ['acid', 'bludgeoning', 'cold', 'fire', 'force', 'lightning', 'necrotic', 'piercing',
    'poison', 'psychic', 'radiant', 'slashing', 'thunder']
  const CRS = ['0', '1/8', '1/4', '1/2', ...Array.from({ length: 30 }, (_, i) => String(i + 1))]
  const SIZES = ['tiny', 'small', 'medium', 'large', 'huge', 'gargantuan'] as const

  const sheet = $derived(character.sheet!)
  const d = $derived(character.derived)
  const editable = $derived(store.canEditCharacter(character))
  const metric = $derived(store.measurement === 'metric')
  let editingAttack = $state<string | null>(null)
  let editingSpell = $state<string | null>(null)
  /** Slot level chosen for each spell's next cast. */
  let castLevel = $state<Record<string, number>>({})
  const LEVELS = [1, 2, 3, 4, 5, 6, 7, 8, 9]

  const slotOf = (level: number) => sheet.spellcasting.slots[String(level)] ?? { max: 0, used: 0 }
  /** Slot levels a spell can be cast with now (its level or higher, with slots left). */
  const castable = (s: SheetSpell) => LEVELS.filter((l) => l >= s.level && slotOf(l).max - slotOf(l).used > 0)
  const spells = $derived([...sheet.spells].sort((a, b) => a.level - b.level || a.name.localeCompare(b.name)))

  function setSlot(level: number, change: (slot: { max: number; used: number }) => void) {
    patch((s) => {
      const slot = s.spellcasting.slots[String(level)] ?? { max: 0, used: 0 }
      change(slot)
      slot.used = Math.min(slot.used, slot.max)
      if (slot.max) s.spellcasting.slots[String(level)] = slot
      else delete s.spellcasting.slots[String(level)]
    })
  }

  function setSpell(id: string, change: (sp: SheetSpell) => void) {
    patch((s) => {
      const sp = s.spells.find((x) => x.id === id)
      if (sp) change(sp)
    })
  }

  function addSpell() {
    const id = uid()
    patch((s) => {
      s.spells.push({
        id, name: 'Spell', level: 1, prepared: true, concentration: false, ritual: false, attack: false,
        save: null, half_on_save: true, damage: '', damage_type: '', upcast: '', duration: '', description: '',
        effect: null,
      })
    })
    editingSpell = id
  }

  function castSpell(s: SheetSpell) {
    if (s.level === 0) return store.cast(character.id, s.id, null)
    const options = castable(s)
    const level = castLevel[s.id] && options.includes(castLevel[s.id]) ? castLevel[s.id] : options[0]
    if (!level) return store.toast(`No slots left for ${s.name}`)
    store.cast(character.id, s.id, level)
  }

  const label = (key: string) => key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
  const signed = (n: number | null | undefined) => (n === null || n === undefined ? '—' : n >= 0 ? `+${n}` : `${n}`)

  /** Change the sheet and send it whole: the server validates it and recomputes the derived values. */
  function patch(change: (s: Sheet) => void) {
    const next = structuredClone($state.snapshot(sheet)) as Sheet
    change(next)
    store.updateCharacter(character.id, { sheet: next })
  }

  function int(value: string, min: number, max: number, fallback: number): number {
    const n = Math.round(Number(value))
    return Number.isFinite(n) ? Math.min(max, Math.max(min, n)) : fallback
  }

  function roll(kind: SheetRollKind, key: string | null = null) {
    store.sheetRoll(character.id, kind, key)
  }

  function cycleSkill(skill: string) {
    patch((s) => {
      const next = ((s.skills[skill] ?? 0) + 1) % 3
      if (next) s.skills[skill] = next as 1 | 2
      else delete s.skills[skill]
    })
  }

  function toggleSave(a: AbilityKey) {
    patch((s) => {
      s.save_proficiencies = s.save_proficiencies.includes(a)
        ? s.save_proficiencies.filter((x) => x !== a)
        : [...s.save_proficiencies, a]
    })
  }

  function addAttack() {
    const id = uid()
    patch((s) => {
      s.attacks.push({
        id, name: 'Attack', kind: 'attack', ability: 'str', proficient: true, bonus: 0, to_hit: null,
        damage: '1d6', damage_type: 'slashing', add_modifier: true, save: null, dc: null, half_on_save: true,
        range: '', notes: '',
      })
    })
    editingAttack = id
  }

  function setAttack(id: string, change: (a: SheetAttack) => void) {
    patch((s) => {
      const a = s.attacks.find((x) => x.id === id)
      if (a) change(a)
    })
  }

  // Speed is stored in feet; in metric games it is shown and typed in metres (5 ft = 1.5 m).
  const speedShown = $derived(metric ? Math.round((sheet.speed / 5) * 1.5 * 10) / 10 : sheet.speed)
  function setSpeed(value: string) {
    const n = Number(value)
    if (!Number.isFinite(n)) return
    const feet = metric ? Math.round((n / 1.5) * 5 / 5) * 5 : Math.round(n)
    patch((s) => (s.speed = Math.max(0, Math.min(500, feet))))
  }

  const list = (v: string) => v.split(',').map((x) => x.trim().toLowerCase()).filter(Boolean).slice(0, 20)
  const targetName = $derived(store.sheetTarget ? store.objects.get(store.sheetTarget)?.props.name ?? 'token' : null)
</script>

<div class="sheet">
  <div class="rollbar">
    <div class="seg" role="radiogroup" aria-label="Roll mode">
      {#each [['normal', 'Normal'], ['advantage', 'Adv'], ['disadvantage', 'Dis']] as [mode, text] (mode)}
        <button class:on={store.sheetMode === mode} role="radio" aria-checked={store.sheetMode === mode}
          onclick={() => (store.sheetMode = mode as typeof store.sheetMode)}>{text}</button>
      {/each}
    </div>
    <label class="check" title="Only you and the GM see the roll"><input type="checkbox" bind:checked={store.sheetGmOnly} /> to GM</label>
    <span class="target">
      🎯
      {#if store.pickingSheetTarget}
        <em>click a token…</em>
      {:else if targetName}
        <strong>{targetName}</strong>
        <button class="mini" title="No target" onclick={() => (store.sheetTarget = null)}>✕</button>
      {:else}
        <button class="link" onclick={() => (store.pickingSheetTarget = true)}>pick target</button>
      {/if}
    </span>
  </div>

  <div class="identity">
    {#if sheet.kind === 'pc'}
      <label>Level <input type="number" min="1" max="20" value={sheet.level} disabled={!editable}
        onchange={(e) => patch((s) => (s.level = int(e.currentTarget.value, 1, 20, s.level)))} /></label>
      <label class="grow">Class <input value={sheet.classes} maxlength="120" disabled={!editable}
        onchange={(e) => patch((s) => (s.classes = e.currentTarget.value))} /></label>
      <label class="grow">Species <input value={sheet.species} maxlength="120" disabled={!editable}
        onchange={(e) => patch((s) => (s.species = e.currentTarget.value))} /></label>
    {:else}
      <label>CR <select value={sheet.cr} disabled={!editable} onchange={(e) => patch((s) => (s.cr = e.currentTarget.value))}>
        {#each CRS as cr (cr)}<option value={cr}>{cr}</option>{/each}</select></label>
      <label class="grow">Type <input value={sheet.creature_type} maxlength="120" disabled={!editable} placeholder="humanoid"
        onchange={(e) => patch((s) => (s.creature_type = e.currentTarget.value))} /></label>
      <span class="stat">XP <b>{d?.xp ?? '—'}</b></span>
    {/if}
    <label>Size <select value={sheet.size} disabled={!editable}
      onchange={(e) => patch((s) => (s.size = e.currentTarget.value as Sheet['size']))}>
      {#each SIZES as size (size)}<option value={size}>{label(size)}</option>{/each}</select></label>
  </div>

  <div class="abilities">
    {#each ABILITIES as a (a.key)}
      <div class="ability">
        <span class="short" title={a.name}>{a.short}</span>
        <input class="score" type="number" min="1" max="30" value={sheet.abilities[a.key]} disabled={!editable}
          aria-label={`${a.name} score`}
          onchange={(e) => patch((s) => (s.abilities[a.key] = int(e.currentTarget.value, 1, 30, s.abilities[a.key])))} />
        <button class="roll mod" title={`${a.name} check`} onclick={() => roll('check', a.key)}>{signed(d?.modifiers[a.key])}</button>
        <div class="save">
          <button class="dot" class:on={sheet.save_proficiencies.includes(a.key)} disabled={!editable}
            title="Proficient in this saving throw" aria-label={`${a.name} save proficiency`} onclick={() => toggleSave(a.key)}></button>
          <button class="roll" title={`${a.name} save`} onclick={() => roll('save', a.key)}>save {signed(d?.saves[a.key])}</button>
        </div>
      </div>
    {/each}
  </div>

  <div class="combat">
    <label class="box">AC<input type="number" min="0" max="40" value={sheet.ac} disabled={!editable}
      onchange={(e) => patch((s) => (s.ac = int(e.currentTarget.value, 0, 40, s.ac)))} /></label>
    <label class="box">HP<span class="hp">
      <input type="number" min="0" value={sheet.hp.current} disabled={!editable} aria-label="Current HP"
        onchange={(e) => patch((s) => (s.hp.current = int(e.currentTarget.value, 0, 9999, s.hp.current)))} />/<input
        type="number" min="0" value={sheet.hp.max} disabled={!editable} aria-label="Max HP"
        onchange={(e) => patch((s) => (s.hp.max = int(e.currentTarget.value, 0, 9999, s.hp.max)))} /></span></label>
    <label class="box">Temp<input type="number" min="0" value={sheet.hp.temp} disabled={!editable} aria-label="Temporary HP"
      onchange={(e) => patch((s) => (s.hp.temp = int(e.currentTarget.value, 0, 9999, s.hp.temp)))} /></label>
    <label class="box">Speed ({metric ? 'm' : 'ft'})<input type="number" min="0" step={metric ? 1.5 : 5} value={speedShown}
      disabled={!editable} onchange={(e) => setSpeed(e.currentTarget.value)} /></label>
    <div class="box">Initiative<button class="roll big" onclick={() => roll('initiative')}>{signed(d?.initiative)}</button></div>
    <div class="box">Proficiency<b class="big">{signed(d?.proficiency)}</b></div>
    <div class="box">Passive Perc.<b class="big">{d?.passive_perception ?? '—'}</b></div>
    <label class="box">Exhaustion<select value={sheet.exhaustion} disabled={!editable}
      onchange={(e) => patch((s) => (s.exhaustion = Number(e.currentTarget.value)))}>
      {#each [0, 1, 2, 3, 4, 5, 6] as n (n)}<option value={n}>{n}</option>{/each}</select></label>
    {#if sheet.kind === 'pc'}
      <label class="box">Hit dice<span class="hp">
        <select value={sheet.hit_dice.die} disabled={!editable} aria-label="Hit die"
          onchange={(e) => patch((s) => (s.hit_dice.die = Number(e.currentTarget.value) as 6 | 8 | 10 | 12))}>
          {#each [6, 8, 10, 12] as die (die)}<option value={die}>d{die}</option>{/each}</select>
        <small>{(d?.hit_dice_total ?? 0) - sheet.hit_dice.spent}/{d?.hit_dice_total ?? 0}</small></span></label>
    {/if}
  </div>

  {#if sheet.kind === 'pc'}
    <div class="rest">
      {#if sheet.hp.current === 0}
        <div class="death" aria-label="Death saves">
          <span>Death saves</span>
          <span class="pips ok" title="Successes">{#each [0, 1, 2] as i (i)}<i class:on={i < sheet.death_saves.successes}></i>{/each}</span>
          <span class="pips ko" title="Failures">{#each [0, 1, 2] as i (i)}<i class:on={i < sheet.death_saves.failures}></i>{/each}</span>
          <button class="btn small" onclick={() => roll('death_save')}>Roll death save</button>
        </div>
      {/if}
      <button class="btn small" onclick={() => store.sheetRest(character.id, 'hit_die')}
        title="Roll one hit point die plus Constitution and regain that many hit points">Spend hit die</button>
      <button class="btn small" onclick={() => store.sheetRest(character.id, 'short')}>Short rest</button>
      <button class="btn small" onclick={() => store.sheetRest(character.id, 'long')}
        title="All hit points, hit point dice, spell slots and resources; exhaustion −1">Long rest</button>
    </div>
  {/if}

  <section>
    <h4>Attacks & actions</h4>
    {#each sheet.attacks as a (a.id)}
      {@const da = d?.attacks[a.id]}
      <div class="attack">
        <span class="name">{a.name}</span>
        {#if a.kind === 'attack'}
          <button class="roll" title="Attack roll" onclick={() => roll('attack', a.id)}>{signed(da?.to_hit)}</button>
        {:else}
          <button class="roll" title="Show the saving throw" onclick={() => roll('attack', a.id)}>DC {da?.dc} {a.save?.toUpperCase() ?? ''}</button>
        {/if}
        {#if da?.damage}
          <button class="roll" title="Damage roll" onclick={() => roll('damage', a.id)}>{da.damage} {a.damage_type}</button>
        {/if}
        {#if editable}
          <button class="mini" title="Edit" aria-label={`Edit ${a.name}`}
            onclick={() => (editingAttack = editingAttack === a.id ? null : a.id)}>✎</button>
        {/if}
      </div>
      {#if editingAttack === a.id && editable}
        <div class="attack-edit">
          <label>Name <input value={a.name} maxlength="120" onchange={(e) => setAttack(a.id, (x) => (x.name = e.currentTarget.value))} /></label>
          <label>Kind <select value={a.kind} onchange={(e) => setAttack(a.id, (x) => (x.kind = e.currentTarget.value as 'attack' | 'save'))}>
            <option value="attack">Attack roll</option><option value="save">Saving throw</option></select></label>
          <label>Ability <select value={a.ability} onchange={(e) => setAttack(a.id, (x) => (x.ability = e.currentTarget.value as SheetAttack['ability']))}>
            {#each ABILITIES as ab (ab.key)}<option value={ab.key}>{ab.short}</option>{/each}
            <option value="spell">Spellcasting</option><option value="none">None</option></select></label>
          {#if a.kind === 'attack'}
            <label class="check"><input type="checkbox" checked={a.proficient} onchange={(e) => setAttack(a.id, (x) => (x.proficient = e.currentTarget.checked))} /> proficient</label>
            <label>Extra bonus <input type="number" value={a.bonus} onchange={(e) => setAttack(a.id, (x) => (x.bonus = int(e.currentTarget.value, -99, 99, 0)))} /></label>
            <label title="Fixed bonus from a stat block; empty = computed">Fixed to hit <input type="number" value={a.to_hit ?? ''}
              onchange={(e) => setAttack(a.id, (x) => (x.to_hit = e.currentTarget.value === '' ? null : int(e.currentTarget.value, -99, 99, 0)))} /></label>
          {:else}
            <label>Save <select value={a.save ?? ''} onchange={(e) => setAttack(a.id, (x) => (x.save = (e.currentTarget.value || null) as AbilityKey | null))}>
              <option value="">—</option>{#each ABILITIES as ab (ab.key)}<option value={ab.key}>{ab.short}</option>{/each}</select></label>
            <label title="Fixed DC from a stat block; empty = 8 + proficiency + modifier">Fixed DC <input type="number" value={a.dc ?? ''}
              onchange={(e) => setAttack(a.id, (x) => (x.dc = e.currentTarget.value === '' ? null : int(e.currentTarget.value, 1, 40, 10)))} /></label>
            <label class="check"><input type="checkbox" checked={a.half_on_save} onchange={(e) => setAttack(a.id, (x) => (x.half_on_save = e.currentTarget.checked))} /> half damage on a success</label>
          {/if}
          <label>Damage <input value={a.damage} maxlength="80" placeholder="1d8" onchange={(e) => setAttack(a.id, (x) => (x.damage = e.currentTarget.value))} /></label>
          <label>Type <select value={a.damage_type} onchange={(e) => setAttack(a.id, (x) => (x.damage_type = e.currentTarget.value))}>
            {#each DAMAGE_TYPES as t (t)}<option value={t}>{t}</option>{/each}</select></label>
          <label class="check"><input type="checkbox" checked={a.add_modifier} onchange={(e) => setAttack(a.id, (x) => (x.add_modifier = e.currentTarget.checked))} /> add modifier to damage</label>
          <label>Range <input value={a.range} maxlength="120" onchange={(e) => setAttack(a.id, (x) => (x.range = e.currentTarget.value))} /></label>
          <label class="wide">Notes <input value={a.notes} maxlength="2000" onchange={(e) => setAttack(a.id, (x) => (x.notes = e.currentTarget.value))} /></label>
          <button class="btn small danger" onclick={() => patch((s) => (s.attacks = s.attacks.filter((x) => x.id !== a.id)))}>Remove</button>
        </div>
      {/if}
    {:else}
      <p class="muted">No attacks.</p>
    {/each}
    {#if editable}<button class="btn small" onclick={addAttack}>+ Attack</button>{/if}
  </section>

  <section>
    <h4>Spellcasting</h4>
    <div class="casting">
      <label>Ability
        <select value={sheet.spellcasting.ability ?? ''} disabled={!editable} aria-label="Spellcasting ability"
          onchange={(e) => patch((s) => (s.spellcasting.ability = (e.currentTarget.value || null) as AbilityKey | null))}>
          <option value="">—</option>
          {#each ABILITIES as ab (ab.key)}<option value={ab.key}>{ab.name}</option>{/each}
        </select>
      </label>
      <span class="stat">Save DC <b>{d?.spell_dc ?? '—'}</b></span>
      <span class="stat">Spell attack <b>{signed(d?.spell_attack)}</b></span>
    </div>
    <div class="slots" aria-label="Spell slots">
      {#each LEVELS as level (level)}
        {@const slot = slotOf(level)}
        <div class="slot">
          <small>{level}</small>
          <input type="number" min="0" max="9" value={slot.max} disabled={!editable} aria-label={`Level ${level} slots`}
            onchange={(e) => setSlot(level, (sl) => (sl.max = int(e.currentTarget.value, 0, 9, sl.max)))} />
          <span class="pips">
            {#each Array.from({ length: slot.max }, (_, i) => i) as i (i)}
              {@const left = i < slot.max - slot.used}
              <button class="pip" class:on={left} disabled={!editable} title={left ? 'Use a slot' : 'Get a slot back'}
                aria-label={`Level ${level} slot ${i + 1}`}
                onclick={() => setSlot(level, (sl) => (sl.used = Math.max(0, sl.used + (left ? 1 : -1))))}></button>
            {/each}
          </span>
        </div>
      {/each}
    </div>
    {#each spells as s (s.id)}
      {@const options = castable(s)}
      <div class="spell">
        <span class="level" title={s.level === 0 ? 'Cantrip' : `Level ${s.level}`}>{s.level === 0 ? 'C' : s.level}</span>
        <span class="name">{s.name}
          {#if s.concentration}<small title="Concentration">◎</small>{/if}
          {#if s.ritual}<small title="Ritual">®</small>{/if}
        </span>
        {#if s.level > 0 && options.length > 1}
          <select class="slot-pick" value={castLevel[s.id] ?? options[0]} aria-label={`Slot for ${s.name}`}
            onchange={(e) => (castLevel[s.id] = Number(e.currentTarget.value))}>
            {#each options as l (l)}<option value={l}>lvl {l}</option>{/each}
          </select>
        {/if}
        <button class="roll" disabled={s.level > 0 && !options.length} title="Cast: targets are the sheet target or the selected tokens"
          onclick={() => castSpell(s)}>Cast</button>
        {#if editable}
          <button class="mini" aria-label={`Edit ${s.name}`} onclick={() => (editingSpell = editingSpell === s.id ? null : s.id)}>✎</button>
        {/if}
      </div>
      {#if editingSpell === s.id && editable}
        <div class="attack-edit">
          <label>Name <input value={s.name} maxlength="120" onchange={(e) => setSpell(s.id, (x) => (x.name = e.currentTarget.value))} /></label>
          <label>Level <select value={s.level} onchange={(e) => setSpell(s.id, (x) => (x.level = Number(e.currentTarget.value)))}>
            <option value={0}>Cantrip</option>{#each LEVELS as l (l)}<option value={l}>{l}</option>{/each}</select></label>
          <label class="check"><input type="checkbox" checked={s.concentration} onchange={(e) => setSpell(s.id, (x) => (x.concentration = e.currentTarget.checked))} /> concentration</label>
          <label class="check"><input type="checkbox" checked={s.ritual} onchange={(e) => setSpell(s.id, (x) => (x.ritual = e.currentTarget.checked))} /> ritual</label>
          <label class="check"><input type="checkbox" checked={s.attack} onchange={(e) => setSpell(s.id, (x) => (x.attack = e.currentTarget.checked))} /> spell attack</label>
          <label>Save <select value={s.save ?? ''} onchange={(e) => setSpell(s.id, (x) => (x.save = (e.currentTarget.value || null) as AbilityKey | null))}>
            <option value="">—</option>{#each ABILITIES as ab (ab.key)}<option value={ab.key}>{ab.short}</option>{/each}</select></label>
          <label class="check"><input type="checkbox" checked={s.half_on_save} onchange={(e) => setSpell(s.id, (x) => (x.half_on_save = e.currentTarget.checked))} /> half on a success</label>
          <label>Damage <input value={s.damage} maxlength="80" placeholder="8d6" onchange={(e) => setSpell(s.id, (x) => (x.damage = e.currentTarget.value))} /></label>
          <label>Type <select value={s.damage_type} onchange={(e) => setSpell(s.id, (x) => (x.damage_type = e.currentTarget.value))}>
            <option value="">—</option>{#each DAMAGE_TYPES as t (t)}<option value={t}>{t}</option>{/each}</select></label>
          <label title="Dice added per slot level above the spell's level">Per level up <input value={s.upcast} maxlength="80" placeholder="1d6"
            onchange={(e) => setSpell(s.id, (x) => (x.upcast = e.currentTarget.value))} /></label>
          <label>Effect <select value={s.effect ?? ''} onchange={(e) => setSpell(s.id, (x) => (x.effect = e.currentTarget.value || null))}>
            <option value="">—</option>{#each EFFECT_PRESETS as p (p.key)}<option value={p.key}>{p.label}</option>{/each}</select></label>
          <label>Duration <input value={s.duration} maxlength="120" placeholder="1 minute" onchange={(e) => setSpell(s.id, (x) => (x.duration = e.currentTarget.value))} /></label>
          <label class="wide">Description <textarea rows="2" maxlength="4000" value={s.description}
            onchange={(e) => setSpell(s.id, (x) => (x.description = e.currentTarget.value))}></textarea></label>
          <button class="btn small danger" onclick={() => patch((sh) => (sh.spells = sh.spells.filter((x) => x.id !== s.id)))}>Remove</button>
        </div>
      {/if}
    {:else}
      <p class="muted">No spells.</p>
    {/each}
    {#if editable}<button class="btn small" onclick={addSpell}>+ Spell</button>{/if}
  </section>

  <section>
    <h4>Resources</h4>
    {#each sheet.resources as r (r.id)}
      <div class="resource">
        <input class="grow" value={r.name} maxlength="120" disabled={!editable} aria-label="Resource name"
          onchange={(e) => patch((s) => { const x = s.resources.find((y) => y.id === r.id); if (x) x.name = e.currentTarget.value })} />
        <input type="number" min="0" value={r.max - r.used} disabled={!editable} aria-label={`${r.name} left`}
          onchange={(e) => patch((s) => { const x = s.resources.find((y) => y.id === r.id); if (x) x.used = Math.max(0, x.max - int(e.currentTarget.value, 0, 99, 0)) })} />
        <span>/</span>
        <input type="number" min="0" value={r.max} disabled={!editable} aria-label={`${r.name} max`}
          onchange={(e) => patch((s) => { const x = s.resources.find((y) => y.id === r.id); if (x) x.max = int(e.currentTarget.value, 0, 99, x.max) })} />
        <select value={r.reset} disabled={!editable} aria-label={`${r.name} recharge`}
          onchange={(e) => patch((s) => { const x = s.resources.find((y) => y.id === r.id); if (x) x.reset = e.currentTarget.value as 'short' | 'long' | 'none' })}>
          <option value="short">short rest</option><option value="long">long rest</option><option value="none">never</option>
        </select>
        {#if editable}<button class="mini" aria-label={`Remove ${r.name}`} onclick={() => patch((s) => (s.resources = s.resources.filter((y) => y.id !== r.id)))}>✕</button>{/if}
      </div>
    {:else}
      <p class="muted">No resources.</p>
    {/each}
    {#if editable}
      <button class="btn small" onclick={() => patch((s) => s.resources.push({ id: uid(), name: 'Resource', max: 1, used: 0, reset: 'long' }))}>+ Resource</button>
    {/if}
  </section>

  <section>
    <h4>Skills</h4>
    <div class="skills">
      {#each SKILLS as [skill, ability] (skill)}
        {@const level = sheet.skills[skill] ?? 0}
        <div class="skill">
          <button class="dot" class:on={level === 1} class:expert={level === 2} disabled={!editable}
            title={level === 2 ? 'Expertise' : level === 1 ? 'Proficient' : 'Not proficient'}
            aria-label={`${label(skill)} proficiency`} onclick={() => cycleSkill(skill)}></button>
          <button class="roll skill-roll" onclick={() => roll('skill', skill)}>
            <span>{label(skill)} <small>{ability.toUpperCase()}</small></span><b>{signed(d?.skills[skill])}</b>
          </button>
        </div>
      {/each}
    </div>
  </section>

  <section class="defenses">
    <h4>Defenses</h4>
    {#each [['resistances', 'Resistances'], ['immunities', 'Immunities'], ['vulnerabilities', 'Vulnerabilities']] as [key, text] (key)}
      <label>{text}
        <input value={(sheet[key as 'resistances'] ?? []).join(', ')} disabled={!editable} placeholder="fire, poison"
          onchange={(e) => patch((s) => (s[key as 'resistances'] = list(e.currentTarget.value)))} /></label>
    {/each}
  </section>

  <section>
    <h4>Features & traits</h4>
    <textarea rows="4" value={sheet.features} disabled={!editable} maxlength="20000" aria-label="Features"
      onchange={(e) => patch((s) => (s.features = e.currentTarget.value))}></textarea>
  </section>
  {#if editable}<p class="muted saved">Changes are saved as you go.</p>{/if}
</div>

<style>
  .sheet {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .rollbar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 10px;
    position: sticky;
    top: -14px;
    z-index: 1;
    padding: 6px 0;
    background: var(--surface);
  }
  .seg {
    display: flex;
    border: 1px solid var(--border);
    border-radius: 8px;
    overflow: hidden;
  }
  .seg button {
    border: none;
    background: none;
    color: var(--text-muted);
    padding: 4px 10px;
    cursor: pointer;
  }
  .seg button.on {
    background: var(--gradient-accent);
    color: var(--accent-contrast);
    font-weight: 700;
  }
  .target {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 0.85rem;
  }
  .identity {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: end;
    font-size: 0.75rem;
    color: var(--text-muted);
  }
  .identity label {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .identity .grow {
    flex: 1;
    min-width: 110px;
  }
  .identity input[type='number'] {
    width: 60px;
  }
  .stat b {
    color: var(--text);
  }
  .abilities {
    display: grid;
    grid-template-columns: repeat(6, minmax(0, 1fr));
    gap: 6px;
  }
  .ability {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 3px;
    padding: 6px 4px;
    border: 1px solid var(--border);
    border-radius: 10px;
    background: var(--surface-2);
  }
  .short {
    font-size: 0.7rem;
    font-weight: 700;
    color: var(--text-muted);
    letter-spacing: 0.06em;
  }
  .score {
    width: 52px;
    text-align: center;
  }
  .roll {
    border: 1px solid var(--border);
    background: var(--surface-3);
    color: var(--text);
    border-radius: 6px;
    padding: 2px 8px;
    cursor: pointer;
    font: inherit;
  }
  .roll:hover {
    border-color: var(--accent);
    background: color-mix(in srgb, var(--accent) 20%, var(--surface-3));
  }
  .mod {
    font-size: 1.1rem;
    font-weight: 700;
    min-width: 48px;
  }
  .save {
    display: flex;
    align-items: center;
    gap: 3px;
    font-size: 0.72rem;
  }
  .save .roll {
    padding: 1px 5px;
    font-size: 0.72rem;
  }
  .dot {
    width: 12px;
    height: 12px;
    padding: 0;
    border-radius: 50%;
    border: 1.5px solid var(--text-muted);
    background: transparent;
    cursor: pointer;
    flex-shrink: 0;
  }
  .dot.on {
    background: var(--accent);
    border-color: var(--accent);
  }
  .dot.expert {
    background: var(--highlight);
    border-color: var(--highlight);
    border-radius: 2px;
  }
  .combat {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(96px, 1fr));
    gap: 6px;
  }
  .box {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 3px;
    padding: 6px;
    border: 1px solid var(--border);
    border-radius: 10px;
    font-size: 0.7rem;
    color: var(--text-muted);
  }
  .box input,
  .box select {
    width: 64px;
    text-align: center;
  }
  .hp {
    display: flex;
    align-items: center;
    gap: 2px;
  }
  .hp input {
    width: 48px;
  }
  .big {
    font-size: 1.05rem;
    font-weight: 700;
    color: var(--text);
  }
  section {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  h4 {
    margin: 0;
    font-size: 0.75rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--text-muted);
  }
  .rest {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
  }
  .death {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 4px 8px;
    border: 1px solid var(--danger);
    border-radius: 8px;
    font-size: 0.8rem;
  }
  .pips {
    display: inline-flex;
    gap: 3px;
  }
  .pips i {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    border: 1.5px solid currentColor;
  }
  .pips.ok {
    color: var(--success);
  }
  .pips.ko {
    color: var(--danger);
  }
  .pips i.on {
    background: currentColor;
  }
  .attack {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
  }
  .attack .name {
    flex: 1;
    min-width: 100px;
    font-weight: 600;
  }
  .attack-edit {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
    gap: 6px;
    padding: 8px;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--surface-2);
    font-size: 0.75rem;
  }
  .attack-edit label {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .attack-edit .wide {
    grid-column: 1 / -1;
  }
  .attack-edit input,
  .attack-edit select {
    min-width: 0;
  }
  .casting {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 12px;
    font-size: 0.8rem;
  }
  .casting label {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .slots {
    display: grid;
    grid-template-columns: repeat(9, minmax(0, 1fr));
    gap: 4px;
  }
  .slot {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 3px;
    padding: 4px 2px;
    border: 1px solid var(--border);
    border-radius: 8px;
  }
  .slot small {
    color: var(--text-muted);
    font-size: 0.65rem;
  }
  .slot input {
    width: 38px;
    text-align: center;
    padding: 1px;
  }
  .pips {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 2px;
    min-height: 10px;
  }
  .pip {
    width: 9px;
    height: 9px;
    padding: 0;
    border-radius: 50%;
    border: 1.5px solid var(--accent);
    background: transparent;
    cursor: pointer;
  }
  .pip.on {
    background: var(--accent);
  }
  .spell {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .spell .level {
    width: 22px;
    height: 22px;
    display: grid;
    place-items: center;
    border-radius: 6px;
    background: var(--surface-3);
    font-size: 0.75rem;
    font-weight: 700;
  }
  .spell .name {
    flex: 1;
    min-width: 0;
    font-weight: 600;
  }
  .spell .name small {
    color: var(--accent-3);
    margin-left: 3px;
  }
  .slot-pick {
    width: 72px;
  }
  .resource {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .resource input[type='number'] {
    width: 52px;
  }
  .resource .grow {
    flex: 1;
    min-width: 0;
  }
  .skills {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 3px 10px;
  }
  .skill {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .skill-roll {
    flex: 1;
    display: flex;
    justify-content: space-between;
    border-color: transparent;
    background: transparent;
    font-size: 0.82rem;
  }
  .skill-roll small {
    color: var(--text-muted);
    font-size: 0.65rem;
  }
  .defenses label {
    display: grid;
    grid-template-columns: 110px 1fr;
    align-items: center;
    font-size: 0.8rem;
  }
  .check {
    display: flex;
    align-items: center;
    gap: 5px;
    font-size: 0.8rem;
    flex-direction: row !important;
  }
  .mini {
    border: none;
    background: none;
    color: var(--text-muted);
    cursor: pointer;
  }
  .link {
    border: none;
    background: none;
    padding: 0;
    color: var(--accent-3);
    cursor: pointer;
    font: inherit;
  }
  textarea {
    width: 100%;
    resize: vertical;
  }
  .saved {
    font-size: 0.7rem;
    margin: 0;
  }
  @media (max-width: 560px) {
    .abilities {
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }
    .skills {
      grid-template-columns: 1fr;
    }
  }
</style>
