<script lang="ts">
  import type { ChatMessage, Roll } from '../net/protocol'
  import { store } from '../state/game.svelte'
  import RollView from './RollView.svelte'

  let { msg, compact }: { msg: ChatMessage; compact: boolean } = $props()

  type Part = { text: string } | { roll: Roll }

  const parts = $derived.by<Part[]>(() => {
    const inline = msg.roll?.inline ?? []
    const out: Part[] = []
    const re = /\[\[#(\d+)\]\]/g
    let last = 0
    for (const m of msg.content.matchAll(re)) {
      if (m.index > last) out.push({ text: msg.content.slice(last, m.index) })
      const r = inline[Number(m[1])]
      out.push(r ? { roll: r } : { text: m[0] })
      last = m.index + m[0].length
    }
    if (last < msg.content.length) out.push({ text: msg.content.slice(last) })
    return out
  })

  const whisperLabel = $derived.by(() => {
    if (msg.kind !== 'whisper' || !msg.recipients) return ''
    const names = msg.recipients.map((r) => (r === 'gm' ? 'GM' : store.playerName(r)))
    return msg.player_id === store.me?.id ? `a ${names.join(', ')}` : 'a te'
  })

  const time = $derived(
    new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
  )
</script>

<article class="msg {msg.kind}" class:gm-only={msg.gm_only} class:compact>
  {#if !compact && msg.kind !== 'emote' && msg.kind !== 'desc'}
    <header>
      <span class="who" style:color={msg.color}>{msg.speaker}</span>
      {#if msg.kind === 'whisper'}<span class="tag">sussurro {whisperLabel}</span>{/if}
      {#if msg.gm_only}<span class="tag">tiro al GM</span>{/if}
      {#if msg.kind === 'ooc'}<span class="tag">fuori gioco</span>{/if}
      <time>{time}</time>
    </header>
  {/if}

  {#if msg.kind === 'emote'}
    <p class="body"><span style:color={msg.color}>{msg.speaker}</span>
      {#each parts as part, i (i)}{#if 'text' in part}{part.text}{:else}<span class="inline" title={`${part.roll.expression} → ${part.roll.breakdown}`}>{part.roll.total}</span>{/if}{/each}
    </p>
  {:else if parts.length}
    <p class="body">
      {#each parts as part, i (i)}{#if 'text' in part}{part.text}{:else}<span class="inline" title={`${part.roll.expression} → ${part.roll.breakdown}`}>{part.roll.total}</span>{/if}{/each}
    </p>
  {/if}

  {#if msg.roll?.main}
    <RollView roll={msg.roll.main} />
  {/if}
</article>

<style>
  .msg {
    padding: 6px 12px;
  }
  .msg.compact {
    padding-top: 0;
  }
  header {
    display: flex;
    align-items: baseline;
    gap: 6px;
    flex-wrap: wrap;
  }
  .who {
    font-weight: 700;
  }
  .tag {
    font-size: 0.72rem;
    color: var(--text-muted);
    font-style: italic;
  }
  time {
    margin-left: auto;
    font-size: 0.7rem;
    color: var(--text-muted);
  }
  .body {
    margin: 2px 0 0;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    line-height: 1.4;
  }
  .whisper {
    background: color-mix(in srgb, #9b59b6 12%, transparent);
  }
  .gm-only {
    background: color-mix(in srgb, #3498db 10%, transparent);
  }
  .emote .body {
    font-style: italic;
    color: var(--text-muted);
  }
  .ooc .body {
    color: var(--text-muted);
  }
  .desc .body {
    font-family: Georgia, 'Times New Roman', serif;
    font-size: 1.02rem;
    font-style: italic;
    padding: 6px 10px;
    border-left: 3px solid var(--accent);
    background: color-mix(in srgb, var(--accent) 8%, transparent);
  }
  .inline {
    display: inline-block;
    padding: 0 6px;
    border-radius: 4px;
    background: color-mix(in srgb, var(--accent) 25%, var(--bg));
    border: 1px solid var(--accent);
    font-weight: 700;
    cursor: help;
  }
</style>
