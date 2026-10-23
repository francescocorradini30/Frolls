<script lang="ts">
  import { untrack } from 'svelte'
  import type { Ability, Character, CharacterAttribute, CharacterPatch, Sheet } from '../net/protocol'
  import { store } from '../state/game.svelte'
  import { initials } from '../util/ids'
  import { pickFile, uploadImage } from '../util/upload'
  import Sheet5e from './Sheet5e.svelte'

  let { character, onClose }: { character: Character; onClose: () => void } = $props()

  // The form edits a snapshot taken when the window opens.
  const start = untrack(() => character)
  let name = $state(start.name)
  let avatar = $state<string | null>(start.avatar)
  let bio = $state(start.bio)
  let gmNotes = $state(start.gm_notes ?? '')
  let attributes = $state<CharacterAttribute[]>(start.attributes.map((a) => ({ ...a })))
  let abilities = $state<Ability[]>((start.abilities ?? []).map((a) => ({ ...a })))
  let playerId = $state<string | null>(start.player_id)
  let folderId = $state<string | null>(start.folder_id)
  let archived = $state(start.archived)
  let editingBio = $state(!start.bio)
  let uploading = $state(false)
  let confirmDelete = $state(false)
  let tab = $state<'sheet' | 'bio'>(start.sheet ? 'sheet' : 'bio')

  /** Add a 5e sheet with the server's defaults (it fills every field). */
  function createSheet(kind: 'pc' | 'npc') {
    store.updateCharacter(character.id, { sheet: { kind } as Sheet })
    tab = 'sheet'
  }

  const editable = $derived(store.canEditCharacter(character))
  const players = $derived(store.players.filter((p) => !p.is_gm))

  /** Folders as indented paths, for the folder picker. */
  const folderOptions = $derived.by(() => {
    const out: { id: string; label: string }[] = []
    const walk = (parent: string | null, depth: number) => {
      for (const f of store.folders.filter((x) => x.parent_id === parent).sort((a, b) => a.name.localeCompare(b.name))) {
        out.push({ id: f.id, label: `${'  '.repeat(depth)}${f.name}` })
        walk(f.id, depth + 1)
      }
    }
    walk(null, 0)
    return out
  })

  /** Bio split into text and [Name] links to other journal entries. */
  const bioParts = $derived.by(() => {
    const parts: { text: string; link?: string }[] = []
    let last = 0
    for (const m of bio.matchAll(/\[([^[\]\n]{1,120})\]/g)) {
      const target = store.characters.find((c) => c.name.toLowerCase() === m[1].trim().toLowerCase())
      if (!target) continue
      parts.push({ text: bio.slice(last, m.index) }, { text: m[1], link: target.id })
      last = m.index + m[0].length
    }
    parts.push({ text: bio.slice(last) })
    return parts
  })

  async function chooseAvatar() {
    const file = await pickFile()
    if (!file) return
    uploading = true
    try {
      avatar = await uploadImage(file)
    } catch (e) {
      store.toast((e as Error).message)
    } finally {
      uploading = false
    }
  }

  function save() {
    const patch: CharacterPatch = {
      name: name.trim() || 'Unnamed',
      avatar,
      bio,
      attributes: attributes.filter((a) => a.name.trim() || a.current || a.max),
      abilities: abilities
        .filter((a) => a.name.trim() || a.action.trim())
        .map((a) => ({ ...a, name: a.name.trim() || 'Ability' })),
    }
    if (store.isGm) Object.assign(patch, { gm_notes: gmNotes, player_id: playerId, folder_id: folderId, archived })
    store.updateCharacter(character.id, patch)
    onClose()
  }

  function remove() {
    if (!confirmDelete) {
      confirmDelete = true
      return
    }
    store.deleteCharacter(character.id)
    onClose()
  }
</script>

<div class="backdrop" role="presentation" onclick={onClose}>
  <div
    class="dialog panel"
    class:wide={tab === 'sheet' && !!character.sheet}
    role="dialog"
    aria-modal="true"
    aria-label="Character"
    tabindex="-1"
    onclick={(e) => e.stopPropagation()}
    onkeydown={(e) => e.key === 'Escape' && onClose()}
  >
    <header>
      <div class="identity">
        {#if avatar}
          <img class="avatar" src={avatar} alt="" />
        {:else}
          <span class="avatar initials">{initials(name)}</span>
        {/if}
        {#if editable}
          <input class="title" bind:value={name} maxlength="120" aria-label="Name" />
        {:else}
          <strong class="title">{name}</strong>
        {/if}
      </div>
      <button class="icon-btn" aria-label="Close" onclick={onClose}>✕</button>
    </header>

    {#if character.sheet}
      <nav class="tabs">
        <button class:active={tab === 'sheet'} onclick={() => (tab = 'sheet')}>5e sheet</button>
        <button class:active={tab === 'bio'} onclick={() => (tab = 'bio')}>Bio & notes</button>
      </nav>
    {/if}

    {#if tab === 'sheet' && character.sheet}
      <div class="body"><Sheet5e {character} /></div>
    {:else}
    <div class="body">
      {#if !character.sheet && editable}
        <div class="create">
          <span class="muted">5e sheet:</span>
          <button class="btn small" onclick={() => createSheet('pc')}>Create character sheet</button>
          <button class="btn small" onclick={() => createSheet('npc')}>Create NPC stat block</button>
        </div>
      {/if}
      {#if editable}
        <div class="row">
          <button class="btn small" onclick={chooseAvatar} disabled={uploading}>
            {uploading ? 'Uploading…' : avatar ? 'Change avatar' : 'Upload avatar'}
          </button>
          {#if avatar}<button class="btn small" onclick={() => (avatar = null)}>Remove avatar</button>{/if}
        </div>
      {/if}

      {#if store.isGm}
        <div class="grid">
          <label class="field">
            <span>Played by</span>
            <select bind:value={playerId} aria-label="Played by">
              <option value={null}>Nobody (NPC)</option>
              {#each players as p (p.id)}<option value={p.id}>{p.name}</option>{/each}
            </select>
          </label>
          <label class="field">
            <span>Folder</span>
            <select bind:value={folderId} aria-label="Folder">
              <option value={null}>— top level —</option>
              {#each folderOptions as f (f.id)}<option value={f.id}>{f.label}</option>{/each}
            </select>
          </label>
        </div>
      {/if}

      <section>
        <div class="section-head">
          <span>Bio</span>
          {#if editable}
            <button class="link" onclick={() => (editingBio = !editingBio)}>{editingBio ? 'Preview' : 'Edit'}</button>
          {/if}
        </div>
        {#if editingBio && editable}
          <textarea rows="6" bind:value={bio} maxlength="20000" aria-label="Bio"
            placeholder="Story, looks, personality… Write [Name] to link another journal entry."></textarea>
        {:else if bio.trim()}
          <p class="bio">
            {#each bioParts as part, i (i)}
              {#if part.link}
                <button class="link" onclick={() => (store.openCharacterId = part.link!)}>{part.text}</button>
              {:else}{part.text}{/if}
            {/each}
          </p>
        {:else}
          <p class="muted">No bio.</p>
        {/if}
      </section>

      <section>
        <div class="section-head"><span>Attributes</span></div>
        {#if attributes.length}
          <div class="attrs">
            <span class="muted">Name</span><span class="muted">Current</span><span class="muted">Max</span><span></span>
            {#each attributes as a, i (i)}
              <input bind:value={a.name} maxlength="60" disabled={!editable} aria-label="Attribute name" placeholder="hp" />
              <input bind:value={a.current} maxlength="40" disabled={!editable} aria-label="Current value" />
              <input bind:value={a.max} maxlength="40" disabled={!editable} aria-label="Max value" />
              {#if editable}
                <button class="mini" title="Remove" onclick={() => attributes.splice(i, 1)}>✕</button>
              {:else}<span></span>{/if}
            {/each}
          </div>
        {:else}
          <p class="muted">No attributes.</p>
        {/if}
        {#if editable}
          <button class="btn small" onclick={() => attributes.push({ name: '', current: '', max: '' })}>+ Attribute</button>
        {/if}
      </section>

      <section>
        <div class="section-head">
          <span>Abilities</span>
          <span class="muted">run with %&#123;{name}|Name&#125;; token actions show under the map</span>
        </div>
        {#each abilities as a, i (i)}
          <div class="ability">
            <div class="ability-head">
              <input bind:value={a.name} maxlength="60" disabled={!editable} aria-label="Ability name" placeholder="Attack" />
              <label class="check" title="Show as a button when a token of this character is selected">
                <input type="checkbox" bind:checked={a.token_action} disabled={!editable} /> token action
              </label>
              <button class="mini" title="Run in chat" aria-label={`Run ${a.name}`}
                onclick={() => store.sendChat(`%{${character.name}|${a.name}}`)}>▶</button>
              {#if editable}<button class="mini" title="Remove" onclick={() => abilities.splice(i, 1)}>✕</button>{/if}
            </div>
            <textarea rows="2" bind:value={a.action} maxlength="4000" disabled={!editable} aria-label="Ability action"
              placeholder="/r 1d20+@&#123;str&#125;"></textarea>
          </div>
        {:else}
          <p class="muted">No abilities.</p>
        {/each}
        {#if editable}
          <button class="btn small" onclick={() => abilities.push({ name: '', action: '', token_action: true })}>+ Ability</button>
        {/if}
      </section>

      {#if store.isGm}
        <label class="field">
          <span>GM Notes (hidden from players)</span>
          <textarea rows="3" bind:value={gmNotes} maxlength="20000"></textarea>
        </label>
        <label class="check"><input type="checkbox" bind:checked={archived} /> Archived</label>
      {/if}
    </div>
    {/if}

    <footer>
      {#if store.isGm}
        <button class="btn danger" onclick={remove}>{confirmDelete ? 'Click again to delete' : 'Delete'}</button>
      {/if}
      <span class="spacer"></span>
      {#if editable}
        <button class="btn" onclick={onClose}>Cancel</button>
        <button class="btn primary" onclick={save}>Save</button>
      {:else}
        <button class="btn" onclick={onClose}>Close</button>
      {/if}
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
    width: min(560px, 100%);
  }
  .dialog.wide {
    width: min(780px, 100%);
  }
  .tabs {
    display: flex;
    gap: 2px;
    padding: 6px 10px 0;
    border-bottom: 1px solid var(--border);
  }
  .tabs button {
    border: none;
    background: none;
    padding: 8px 12px;
    cursor: pointer;
    border-bottom: 2px solid transparent;
    color: var(--text-muted);
  }
  .tabs button.active {
    color: var(--text);
    border-bottom-color: var(--accent);
  }
  .create {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
    padding: 8px;
    border: 1px dashed var(--border);
    border-radius: 8px;
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
    border-bottom: 1px solid var(--border);
    justify-content: space-between;
  }
  footer {
    border-top: 1px solid var(--border);
  }
  .spacer {
    flex: 1;
  }
  .identity {
    display: flex;
    align-items: center;
    gap: 10px;
    flex: 1;
    min-width: 0;
  }
  .avatar {
    width: 44px;
    height: 44px;
    border-radius: 50%;
    object-fit: cover;
    border: 2px solid var(--border);
    flex-shrink: 0;
  }
  .initials {
    display: grid;
    place-items: center;
    font-weight: 700;
    background: var(--surface-3);
    color: var(--text-muted);
  }
  .title {
    flex: 1;
    min-width: 0;
    font-size: 1.1rem;
    font-weight: 700;
  }
  .body {
    display: flex;
    flex-direction: column;
    gap: 14px;
    padding: 14px;
    overflow-y: auto;
  }
  .row {
    display: flex;
    gap: 6px;
  }
  .grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }
  section {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .section-head {
    display: flex;
    justify-content: space-between;
    font-size: 0.8rem;
    color: var(--text-muted);
  }
  .bio {
    margin: 0;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }
  .link {
    border: none;
    background: none;
    padding: 0;
    color: var(--accent-3);
    cursor: pointer;
    font: inherit;
  }
  .link:hover {
    text-decoration: underline;
  }
  .attrs {
    display: grid;
    grid-template-columns: minmax(0, 2fr) minmax(0, 1fr) minmax(0, 1fr) 22px;
    gap: 4px 6px;
    align-items: center;
    font-size: 0.75rem;
  }
  .attrs input {
    min-width: 0;
  }
  .mini {
    border: none;
    background: none;
    color: var(--text-muted);
    cursor: pointer;
  }
  .ability {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 6px;
    border: 1px solid var(--border);
    border-radius: 8px;
  }
  .ability-head {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .ability-head input:not([type='checkbox']) {
    flex: 1;
    min-width: 0;
  }
  .ability textarea {
    font-family: ui-monospace, monospace;
    font-size: 0.8rem;
  }
  .check {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 0.85rem;
  }
  textarea {
    width: 100%;
    resize: vertical;
  }
  @media (max-width: 520px) {
    .grid {
      grid-template-columns: 1fr;
    }
  }
</style>
