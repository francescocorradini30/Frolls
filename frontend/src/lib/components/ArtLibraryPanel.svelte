<script lang="ts">
  import type { Asset } from '../net/protocol'
  import { store } from '../state/game.svelte'
  import { baseName, pickFiles, uploadFile } from '../util/upload'

  let query = $state('')
  // null = every folder; '' = images outside any folder.
  let folder = $state<string | null>(null)
  let tag = $state<string | null>(null)
  let selectedId = $state<string | null>(null)
  let draft = $state<{ name: string; folder: string; tags: string } | null>(null)
  let progress = $state<{ done: number; total: number } | null>(null)
  let dropping = $state(false)

  const folders = $derived([...new Set(store.assets.map((a) => a.folder).filter(Boolean))].sort())
  const tags = $derived([...new Set(store.assets.flatMap((a) => a.tags))].sort())
  const shown = $derived.by(() => {
    const q = query.trim().toLowerCase()
    return store.assets
      .filter((a) => folder === null || a.folder === folder)
      .filter((a) => !tag || a.tags.includes(tag))
      .filter((a) => !q || a.name.toLowerCase().includes(q) || a.tags.some((t) => t.includes(q)))
      .sort((a, b) => a.name.localeCompare(b.name))
  })
  const selected = $derived(store.assets.find((a) => a.id === selectedId) ?? null)

  /** Several pictures at once, into the folder being shown. */
  async function upload(files: File[]) {
    const images = files.filter((f) => f.type.startsWith('image/'))
    if (!images.length) return
    progress = { done: 0, total: images.length }
    for (const f of images) {
      try {
        const up = await uploadFile(f)
        store.addAsset({ name: baseName(f), ...up, folder: folder ?? '' })
      } catch (e) {
        store.toast(`${f.name}: ${(e as Error).message}`)
      }
      progress = { done: progress.done + 1, total: images.length }
    }
    progress = null
  }

  function select(a: Asset) {
    selectedId = a.id
    draft = { name: a.name, folder: a.folder, tags: a.tags.join(', ') }
  }

  function save() {
    if (!selected || !draft) return
    store.updateAsset(selected.id, {
      name: draft.name.trim() || selected.name,
      folder: draft.folder.trim(),
      tags: draft.tags.split(',').map((t) => t.trim()).filter(Boolean),
    })
  }

  function remove() {
    if (!selected) return
    store.deleteAssets([selected.id])
    selectedId = null
    draft = null
  }

  function drag(e: DragEvent, a: Asset) {
    const data = { url: a.url, name: a.name, width: a.width, height: a.height }
    e.dataTransfer?.setData('application/x-frolls-asset', JSON.stringify(data))
  }
</script>

<div
  class="library"
  class:dropping
  role="region"
  aria-label="Art library"
  ondragover={(e) => {
    if (e.dataTransfer?.types.includes('Files')) {
      e.preventDefault()
      dropping = true
    }
  }}
  ondragleave={(e) => {
    if (e.currentTarget === e.target) dropping = false
  }}
  ondrop={(e) => {
    e.preventDefault()
    dropping = false
    upload([...(e.dataTransfer?.files ?? [])])
  }}
>
  <div class="row">
    <input type="search" placeholder="Search name or tag" bind:value={query} aria-label="Search the art library" />
    <button class="btn small primary" disabled={!!progress} onclick={async () => upload(await pickFiles())}>
      {progress ? `${progress.done}/${progress.total}` : '+ Upload'}
    </button>
  </div>
  <p class="hint muted">
    Pictures are stored optimised (WebP, with thumbnails). Drop files here to upload several at once.
    {#if store.isGm}Drag a picture onto the map: a token, or a map image on the map layer.{/if}
  </p>

  {#if folders.length}
    <div class="chips" role="group" aria-label="Folders">
      <button class="chip" class:on={folder === null} onclick={() => (folder = null)}>All</button>
      {#each folders as f (f)}<button class="chip" class:on={folder === f} onclick={() => (folder = f)}>📁 {f}</button>{/each}
      <button class="chip" class:on={folder === ''} onclick={() => (folder = '')}>No folder</button>
    </div>
  {/if}
  {#if tags.length}
    <div class="chips" role="group" aria-label="Tags">
      {#each tags as t (t)}<button class="chip tag" class:on={tag === t} onclick={() => (tag = tag === t ? null : t)}>#{t}</button>{/each}
    </div>
  {/if}

  <div class="grid">
    {#each shown as a (a.id)}
      <button
        class="tile"
        class:on={a.id === selectedId}
        draggable="true"
        title={a.name}
        aria-label={a.name}
        ondragstart={(e) => drag(e, a)}
        onclick={() => select(a)}
      >
        <img src={a.thumb ?? a.url} alt="" loading="lazy" draggable="false" />
        <span>{a.name}</span>
      </button>
    {:else}
      <p class="muted empty">{store.assets.length ? 'Nothing matches.' : 'Your library is empty: upload some pictures.'}</p>
    {/each}
  </div>

  {#if selected && draft}
    <div class="details">
      <img src={selected.thumb ?? selected.url} alt="" />
      <div class="fields">
        <input bind:value={draft.name} maxlength="120" aria-label="Picture name" onchange={save} />
        <input bind:value={draft.folder} maxlength="120" placeholder="Folder" aria-label="Folder" list="asset-folders" onchange={save} />
        <datalist id="asset-folders">{#each folders as f (f)}<option value={f}></option>{/each}</datalist>
        <input bind:value={draft.tags} placeholder="Tags, comma separated" aria-label="Tags" onchange={save} />
        <div class="row">
          <span class="muted small">{selected.width}×{selected.height}</span>
          <span class="spacer"></span>
          <button class="btn small danger" onclick={remove}>Remove</button>
        </div>
      </div>
    </div>
  {/if}
</div>

<style>
  .library {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 8px;
    min-height: 100%;
  }
  .library.dropping {
    outline: 2px dashed var(--accent);
    outline-offset: -4px;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .row input {
    flex: 1;
    min-width: 0;
  }
  .spacer {
    flex: 1;
  }
  .hint {
    font-size: 0.75rem;
    margin: 0 2px;
  }
  .small {
    font-size: 0.75rem;
  }
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }
  .chip {
    border: 1px solid var(--border);
    background: none;
    border-radius: 999px;
    padding: 2px 9px;
    font-size: 0.75rem;
    cursor: pointer;
    color: var(--text-muted);
  }
  .chip.on {
    color: var(--text);
    border-color: var(--accent);
    background: color-mix(in srgb, var(--accent) 18%, transparent);
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(84px, 1fr));
    gap: 6px;
  }
  .tile {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 4px;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--surface-2);
    cursor: grab;
    min-width: 0;
  }
  .tile.on {
    border-color: var(--accent);
  }
  .tile img {
    width: 100%;
    aspect-ratio: 1;
    object-fit: contain;
    border-radius: 5px;
    background: var(--surface-3);
  }
  .tile span {
    font-size: 0.7rem;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .empty {
    grid-column: 1 / -1;
    font-size: 0.85rem;
  }
  .details {
    display: grid;
    grid-template-columns: 72px 1fr;
    gap: 8px;
    padding: 8px;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--surface-2);
  }
  .details img {
    width: 72px;
    height: 72px;
    object-fit: contain;
    background: var(--surface-3);
    border-radius: 6px;
  }
  .fields {
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-width: 0;
  }
</style>
