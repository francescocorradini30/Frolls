<script lang="ts">
  import { store } from '../state/game.svelte'

  // Macro being edited: its draft, so typing doesn't send a message per key.
  let editing = $state<{ id: string; name: string; action: string; in_bar: boolean } | null>(null)

  const sorted = $derived([...store.macros].sort((a, b) => a.name.localeCompare(b.name)))

  function add() {
    const name = `Macro_${store.macros.length + 1}`
    const id = store.createMacro({ name, action: '/r 1d20', in_bar: true })
    editing = { id, name, action: '/r 1d20', in_bar: true }
  }

  function save() {
    if (!editing) return
    const { id, ...fields } = editing
    store.updateMacro(id, { ...fields, name: fields.name.trim() || 'Macro' })
    editing = null
  }
</script>

<div class="macros">
  <p class="hint muted">
    Chat text run with a click or with <code>#Name</code>. Use <code>@&#123;selected|hp&#125;</code>,
    <code>@&#123;target|hp&#125;</code>, <code>%&#123;Character|Ability&#125;</code> and
    <code>?&#123;Question|default&#125;</code>.
  </p>
  <button class="btn small primary" onclick={add}>+ Macro</button>

  <ul>
    {#each sorted as m (m.id)}
      <li>
        {#if editing?.id === m.id}
          <div class="edit">
            <input bind:value={editing.name} maxlength="60" aria-label="Macro name" />
            <textarea bind:value={editing.action} rows="3" maxlength="4000" aria-label="Macro action"></textarea>
            <label class="check"><input type="checkbox" bind:checked={editing.in_bar} /> Show in the quick bar</label>
            <div class="row">
              <button class="btn small danger" onclick={() => (store.deleteMacro(m.id), (editing = null))}>Delete</button>
              <span class="spacer"></span>
              <button class="btn small" onclick={() => (editing = null)}>Cancel</button>
              <button class="btn small primary" onclick={save}>Save</button>
            </div>
          </div>
        {:else}
          <div class="row">
            <button class="btn small run" title={m.action} onclick={() => store.sendChat(m.action)}>▶ {m.name}</button>
            {#if m.in_bar}<span class="badge" title="In the quick bar">bar</span>{/if}
            <span class="spacer"></span>
            <button class="mini" title="Edit" aria-label={`Edit ${m.name}`} onclick={() => (editing = { ...m })}>✎</button>
          </div>
        {/if}
      </li>
    {:else}
      <li class="muted empty">No macros yet.</li>
    {/each}
  </ul>
</div>

<style>
  .macros {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 8px;
  }
  .hint {
    font-size: 0.75rem;
    margin: 0 2px;
  }
  code {
    font-family: ui-monospace, monospace;
    background: var(--bg);
    padding: 0 3px;
    border-radius: 3px;
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .spacer {
    flex: 1;
  }
  .run {
    max-width: 75%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .edit {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 8px;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--surface-2);
  }
  textarea {
    width: 100%;
    resize: vertical;
    font-family: ui-monospace, monospace;
    font-size: 0.8rem;
  }
  .check {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 0.8rem;
  }
  .mini {
    border: none;
    background: none;
    color: var(--text-muted);
    cursor: pointer;
  }
  .empty {
    font-size: 0.8rem;
    padding: 6px 2px;
  }
</style>
