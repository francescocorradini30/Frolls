<script lang="ts">
  import { untrack } from 'svelte'
  import type { PendingChat } from '../state/game.svelte'
  import { store } from '../state/game.svelte'

  let { pending }: { pending: PendingChat } = $props()

  // Every question of the message in one window, prefilled with its default.
  let answers = $state<string[]>(untrack(() => pending.queries.map((q) => q.default)))

  function submit(e: SubmitEvent) {
    e.preventDefault()
    store.answerQueries($state.snapshot(answers))
  }
</script>

<div class="backdrop" role="presentation" onclick={() => store.answerQueries(null)}>
  <div
    class="dialog panel"
    role="dialog"
    aria-modal="true"
    aria-label="Roll questions"
    tabindex="-1"
    onclick={(e) => e.stopPropagation()}
    onkeydown={(e) => e.key === 'Escape' && store.answerQueries(null)}
  >
    <form onsubmit={submit}>
      <header><strong>Before rolling</strong></header>
      <div class="body">
        {#each pending.queries as q, i (q.prompt)}
          <label class="field">
            <span>{q.prompt}</span>
            {#if q.options.length > 1}
              <select bind:value={answers[i]} aria-label={q.prompt}>
                {#each q.options as [label, value] (label)}<option {value}>{label}</option>{/each}
              </select>
            {:else}
              <!-- svelte-ignore a11y_autofocus -->
              <input bind:value={answers[i]} maxlength="500" aria-label={q.prompt} autofocus={i === 0} />
            {/if}
          </label>
        {/each}
      </div>
      <footer>
        <button type="button" class="btn" onclick={() => store.answerQueries(null)}>Cancel</button>
        <button type="submit" class="btn primary">Roll</button>
      </footer>
    </form>
  </div>
</div>

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    z-index: 110;
    display: grid;
    place-items: center;
    padding: 16px;
    background: var(--backdrop);
  }
  .dialog {
    width: min(380px, 100%);
  }
  form {
    display: flex;
    flex-direction: column;
  }
  header,
  footer {
    display: flex;
    gap: 8px;
    padding: 10px 14px;
  }
  header {
    border-bottom: 1px solid var(--border);
  }
  footer {
    border-top: 1px solid var(--border);
    justify-content: flex-end;
  }
  .body {
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding: 14px;
  }
</style>
