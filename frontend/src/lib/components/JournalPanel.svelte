<script lang="ts">
  import type { Character, JournalFolder } from '../net/protocol'
  import { store } from '../state/game.svelte'
  import { initials } from '../util/ids'

  /** Drag payloads: a character goes to a folder or onto the map, a folder into a folder. */
  const CHARACTER_TYPE = 'application/x-frolls-character'
  const FOLDER_TYPE = 'application/x-frolls-folder'

  let query = $state('')
  let collapsed = $state<Set<string>>(new Set())
  let showArchived = $state(false)
  // Inline name input: a new folder (parent id or 'root') or renaming a folder.
  let naming = $state<{ mode: 'new'; parent: string | null } | { mode: 'rename'; id: string } | null>(null)
  let nameValue = $state('')
  let dropTarget = $state<string | null>(null)

  const byName = (a: { name: string }, b: { name: string }) => a.name.localeCompare(b.name)
  const active = $derived(store.characters.filter((c) => !c.archived).sort(byName))
  const archived = $derived(store.characters.filter((c) => c.archived).sort(byName))
  const results = $derived.by(() => {
    const q = query.trim().toLowerCase()
    return q ? store.characters.filter((c) => c.name.toLowerCase().includes(q)).sort(byName) : null
  })

  function childFolders(parent: string | null): JournalFolder[] {
    return store.folders.filter((f) => f.parent_id === parent).sort(byName)
  }

  function charactersIn(folder: string | null): Character[] {
    const known = new Set(store.folders.map((f) => f.id))
    // A character whose folder is gone shows at the top level.
    return active.filter((c) => (c.folder_id && known.has(c.folder_id) ? c.folder_id : null) === folder)
  }

  function toggle(id: string) {
    const next = new Set(collapsed)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    collapsed = next
  }

  function newCharacter() {
    store.openCharacterId = store.createCharacter()
  }

  function startNaming(state: NonNullable<typeof naming>, initial = '') {
    naming = state
    nameValue = initial
  }

  function commitName() {
    const name = nameValue.trim()
    if (name && naming?.mode === 'new') store.createFolder(name, naming.parent)
    if (name && naming?.mode === 'rename') store.updateFolder(naming.id, { name })
    naming = null
  }

  function dragCharacter(e: DragEvent, c: Character) {
    e.dataTransfer?.setData(CHARACTER_TYPE, c.id)
    e.dataTransfer!.effectAllowed = 'copyMove'
  }

  function dragFolder(e: DragEvent, f: JournalFolder) {
    e.dataTransfer?.setData(FOLDER_TYPE, f.id)
    e.dataTransfer!.effectAllowed = 'move'
  }

  function over(e: DragEvent, target: string) {
    const types = e.dataTransfer?.types ?? []
    if (!store.isGm || !(types.includes(CHARACTER_TYPE) || types.includes(FOLDER_TYPE))) return
    e.preventDefault()
    e.stopPropagation()
    dropTarget = target
  }

  /** Drop on a folder (or 'root'): move the character or folder there. */
  function drop(e: DragEvent, target: string) {
    e.preventDefault()
    e.stopPropagation()
    dropTarget = null
    const folder = target === 'root' ? null : target
    const characterId = e.dataTransfer?.getData(CHARACTER_TYPE)
    const folderId = e.dataTransfer?.getData(FOLDER_TYPE)
    if (characterId) store.updateCharacter(characterId, { folder_id: folder })
    else if (folderId && folderId !== folder) store.updateFolder(folderId, { parent_id: folder })
  }
</script>

{#snippet characterRow(c: Character)}
  <li>
    <button
      class="row character"
      draggable={store.isGm}
      ondragstart={(e) => dragCharacter(e, c)}
      onclick={() => (store.openCharacterId = c.id)}
      title={store.isGm ? 'Open · drag onto the map to place its token, or onto a folder' : 'Open'}
    >
      {#if c.avatar}
        <img class="avatar" src={c.avatar} alt="" />
      {:else}
        <span class="avatar initials">{initials(c.name)}</span>
      {/if}
      <span class="name">{c.name}</span>
      {#if store.isGm && c.player_id}
        <span class="player" style:--dot={store.players.find((p) => p.id === c.player_id)?.color}
          >{store.playerName(c.player_id)}</span
        >
      {/if}
    </button>
  </li>
{/snippet}

{#snippet nameInput()}
  <!-- svelte-ignore a11y_autofocus -->
  <input
    class="name-input"
    bind:value={nameValue}
    placeholder="Folder name"
    maxlength="120"
    autofocus
    onkeydown={(e) => {
      if (e.key === 'Enter') commitName()
      if (e.key === 'Escape') naming = null
    }}
    onblur={commitName}
  />
{/snippet}

{#snippet folderTree(parent: string | null)}
  {#each childFolders(parent) as f (f.id)}
    <li class="folder" class:target={dropTarget === f.id}>
      <div
        class="row folder-row"
        role="treeitem"
        aria-selected="false"
        aria-expanded={!collapsed.has(f.id)}
        tabindex="-1"
        draggable="true"
        ondragstart={(e) => dragFolder(e, f)}
        ondragover={(e) => over(e, f.id)}
        ondragleave={() => dropTarget === f.id && (dropTarget = null)}
        ondrop={(e) => drop(e, f.id)}
      >
        <button class="toggle" onclick={() => toggle(f.id)} aria-label={collapsed.has(f.id) ? 'Expand' : 'Collapse'}
          >{collapsed.has(f.id) ? '▸' : '▾'}</button
        >
        {#if naming?.mode === 'rename' && naming.id === f.id}
          {@render nameInput()}
        {:else}
          <span class="name folder-name">📁 {f.name}</span>
          <span class="actions">
            <button class="mini" title="New subfolder" onclick={() => startNaming({ mode: 'new', parent: f.id })}
              >＋</button
            >
            <button class="mini" title="Rename" onclick={() => startNaming({ mode: 'rename', id: f.id }, f.name)}
              >✎</button
            >
            <button class="mini" title="Delete folder (its content moves up)" onclick={() => store.deleteFolder(f.id)}
              >✕</button
            >
          </span>
        {/if}
      </div>
      {#if !collapsed.has(f.id)}
        <ul class="children">
          {#if naming?.mode === 'new' && naming.parent === f.id}<li>{@render nameInput()}</li>{/if}
          {@render folderTree(f.id)}
          {#each charactersIn(f.id) as c (c.id)}{@render characterRow(c)}{/each}
        </ul>
      {/if}
    </li>
  {/each}
{/snippet}

<div class="journal">
  <div class="top">
    <input class="search" type="search" placeholder="Search characters" bind:value={query} aria-label="Search characters" />
    {#if store.isGm}
      <div class="buttons">
        <button class="btn small primary" onclick={newCharacter}>+ Character</button>
        <button class="btn small" onclick={() => startNaming({ mode: 'new', parent: null })}>+ Folder</button>
      </div>
    {/if}
  </div>

  {#if results}
    <ul class="tree">
      {#each results as c (c.id)}{@render characterRow(c)}{:else}<li class="muted empty">No match.</li>{/each}
    </ul>
  {:else if store.isGm}
    <ul
      class="tree root"
      class:target={dropTarget === 'root'}
      role="tree"
      ondragover={(e) => over(e, 'root')}
      ondragleave={(e) => e.currentTarget === e.target && (dropTarget = null)}
      ondrop={(e) => drop(e, 'root')}
    >
      {#if naming?.mode === 'new' && naming.parent === null}<li>{@render nameInput()}</li>{/if}
      {@render folderTree(null)}
      {#each charactersIn(null) as c (c.id)}{@render characterRow(c)}{/each}
      {#if !store.characters.length && !store.folders.length}
        <li class="muted empty">No characters yet. Create one, then drag it onto the map to place its token.</li>
      {/if}
    </ul>
    {#if archived.length}
      <button class="archived-toggle" onclick={() => (showArchived = !showArchived)}>
        {showArchived ? '▾' : '▸'} Archived ({archived.length})
      </button>
      {#if showArchived}
        <ul class="tree archived">{#each archived as c (c.id)}{@render characterRow(c)}{/each}</ul>
      {/if}
    {/if}
  {:else}
    <ul class="tree">
      {#each store.characters as c (c.id)}{@render characterRow(c)}{:else}
        <li class="muted empty">You have no character yet: the GM assigns one to you.</li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  .journal {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 8px;
  }
  .top {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .search {
    width: 100%;
  }
  .buttons {
    display: flex;
    gap: 6px;
  }
  .tree,
  .children {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  .children {
    padding-left: 14px;
    border-left: 1px solid var(--border);
    margin-left: 9px;
  }
  .root {
    min-height: 60px;
    border-radius: 8px;
    padding-bottom: 12px;
  }
  .target {
    background: color-mix(in srgb, var(--accent) 12%, transparent);
    border-radius: 6px;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    padding: 5px 6px;
    border-radius: 6px;
    border: none;
    background: none;
    color: var(--text);
    text-align: left;
    cursor: pointer;
  }
  .row:hover {
    background: var(--surface-2);
  }
  .avatar {
    width: 26px;
    height: 26px;
    border-radius: 50%;
    object-fit: cover;
    flex-shrink: 0;
    border: 1px solid var(--border);
  }
  .initials {
    display: grid;
    place-items: center;
    font-size: 0.65rem;
    font-weight: 700;
    background: var(--surface-3);
    color: var(--text-muted);
  }
  .name {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .folder-name {
    font-weight: 600;
  }
  .player {
    font-size: 0.7rem;
    color: var(--text-muted);
    display: inline-flex;
    align-items: center;
    gap: 4px;
  }
  .player::before {
    content: '';
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--dot, var(--border));
  }
  .toggle,
  .mini {
    border: none;
    background: none;
    color: var(--text-muted);
    cursor: pointer;
    padding: 0 3px;
  }
  .actions {
    display: none;
    gap: 2px;
  }
  .folder-row:hover .actions,
  .folder-row:focus-within .actions {
    display: flex;
  }
  .mini:hover {
    color: var(--text);
  }
  .name-input {
    flex: 1;
    min-width: 0;
    padding: 2px 6px;
  }
  .empty {
    padding: 10px 6px;
    font-size: 0.8rem;
  }
  .archived-toggle {
    border: none;
    background: none;
    color: var(--text-muted);
    text-align: left;
    cursor: pointer;
    padding: 4px 6px;
    font-size: 0.8rem;
  }
  .archived {
    opacity: 0.7;
  }
</style>
