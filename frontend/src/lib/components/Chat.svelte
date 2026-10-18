<script lang="ts">
  import { tick } from 'svelte'
  import { store } from '../state/game.svelte'
  import ChatMessageView from './ChatMessageView.svelte'

  let text = $state('')
  let log: HTMLDivElement
  let stick = true
  const history: string[] = []
  let historyIndex = -1
  let showHelp = $state(false)

  $effect(() => {
    // Re-run on every new message; keep scrolled to bottom unless the user scrolled up.
    void store.chat.length
    if (stick) tick().then(() => log && (log.scrollTop = log.scrollHeight))
  })

  function onScroll() {
    stick = log.scrollHeight - log.scrollTop - log.clientHeight < 40
  }

  function send() {
    const value = text.trim()
    if (!value) return
    store.sendChat(value)
    history.unshift(value)
    historyIndex = -1
    text = ''
    stick = true
  }

  function onKey(e: KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    } else if (e.key === 'ArrowUp' && !text.includes('\n') && history.length) {
      e.preventDefault()
      historyIndex = Math.min(historyIndex + 1, history.length - 1)
      text = history[historyIndex]
    } else if (e.key === 'ArrowDown' && historyIndex >= 0) {
      e.preventDefault()
      historyIndex -= 1
      text = historyIndex >= 0 ? history[historyIndex] : ''
    }
  }

  function compact(i: number): boolean {
    if (i === 0) return false
    const prev = store.chat[i - 1]
    const cur = store.chat[i]
    return (
      prev.player_id === cur.player_id &&
      prev.kind === cur.kind &&
      cur.kind !== 'whisper' &&
      !cur.gm_only &&
      Date.parse(cur.created_at) - Date.parse(prev.created_at) < 120_000
    )
  }
</script>

<section class="chat">
  <div class="log" bind:this={log} onscroll={onScroll}>
    {#each store.chat as msg, i (msg.id)}
      <ChatMessageView {msg} compact={compact(i)} />
    {:else}
      <p class="empty muted">No messages yet. Try typing <code>d20</code>.</p>
    {/each}
  </div>

  {#if showHelp}
    <div class="help">
      <p><code>d20</code>, <code>2d6+3</code>, <code>4d6dl1</code> → direct roll</p>
      <p><code>2d20kh1</code> advantage · <code>2d20kl1</code> disadvantage</p>
      <p><code>8d6!</code> exploding · <code>5d10&gt;8</code> successes · <code>1d20r1</code> reroll</p>
      <p><code>I hit for [[1d8+3]]</code> → inline roll</p>
      <p><code>/w Name msg</code> whisper · <code>/w gm msg</code></p>
      <p><code>/gr 1d20</code> roll to GM only · <code>/em</code> emote · <code>/ooc</code></p>
      {#if store.isGm}<p><code>/desc text</code> narration</p>{/if}
    </div>
  {/if}

  <div class="composer">
    <textarea
      bind:value={text}
      onkeydown={onKey}
      rows="2"
      maxlength="4000"
      aria-label="Chat message"
    ></textarea>
    <div class="actions">
      <button class="icon-btn" title="Command help" onclick={() => (showHelp = !showHelp)}>?</button>
      <button class="btn primary small" onclick={send} disabled={!text.trim()}>Send</button>
    </div>
  </div>
</section>

<style>
  .chat {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
  }
  .log {
    flex: 1;
    overflow-y: auto;
    padding: 6px 0;
  }
  .empty {
    padding: 16px;
    text-align: center;
  }
  .help {
    padding: 8px 12px;
    border-top: 1px solid var(--border);
    font-size: 0.8rem;
    background: var(--surface-2);
  }
  .help p {
    margin: 3px 0;
  }
  code {
    font-family: ui-monospace, monospace;
    background: var(--bg);
    padding: 0 4px;
    border-radius: 3px;
  }
  .composer {
    border-top: 1px solid var(--border);
    padding: 8px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  textarea {
    resize: none;
    width: 100%;
  }
  .actions {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
</style>
