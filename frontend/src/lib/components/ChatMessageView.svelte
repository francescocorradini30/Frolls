<script lang="ts">
  import type { ChatMessage, Roll } from '../net/protocol'
  import { store } from '../state/game.svelte'
  import RollView from './RollView.svelte'
  import CombatCard from './CombatCard.svelte'

  let { msg, compact }: { msg: ChatMessage; compact: boolean } = $props()

  type Part = { text: string } | { roll: Roll } | { button: string; run: string }

  /** Text with inline rolls `[[#n]]` and chat buttons `[Label](~Character|Ability)` / `[Label](#Macro)`. */
  function split(content: string): Part[] {
    const inline = msg.roll?.inline ?? []
    const out: Part[] = []
    const re = /\[\[#(\d+)\]\]|\[([^\]\n]+)\]\(([~#!][^)\n]+)\)/g
    let last = 0
    for (const m of content.matchAll(re)) {
      if (m.index > last) out.push({ text: content.slice(last, m.index) })
      if (m[1] !== undefined) {
        const r = inline[Number(m[1])]
        out.push(r ? { roll: r } : { text: m[0] })
      } else {
        out.push({ button: m[2], run: m[3] })
      }
      last = m.index + m[0].length
    }
    if (last < content.length) out.push({ text: content.slice(last) })
    return out
  }

  /** Natural value of the kept d20, to highlight 20s and 1s. */
  function natural(roll: Roll): number | null {
    const term = roll.terms.find((t) => t.sides === 20)
    return term?.dice.find((d) => d.kept)?.value ?? null
  }

  const parts = $derived(split(msg.content))
  const template = $derived(msg.roll?.template ?? null)

  const whisperLabel = $derived.by(() => {
    if (msg.kind !== 'whisper' || !msg.recipients) return ''
    const names = msg.recipients.map((r) => (r === 'gm' ? 'GM' : store.playerName(r)))
    return msg.player_id === store.me?.id ? `to ${names.join(', ')}` : 'to you'
  })

  const time = $derived(
    new Date(msg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
  )
</script>

{#snippet rich(list: Part[])}
  {#each list as part, i (i)}{#if 'text' in part}{part.text}{:else if 'roll' in part}<span class="inline" class:crit={natural(part.roll) === 20} class:fumble={natural(part.roll) === 1} title={`${part.roll.expression} → ${part.roll.breakdown}`}>{part.roll.text ?? part.roll.total}</span>{:else}<button class="chat-button" title={part.run} onclick={() => store.runButton(part.run)}>{part.button}</button>{/if}{/each}
{/snippet}

<article class="msg {msg.kind}" class:gm-only={msg.gm_only} class:compact>
  {#if !compact && msg.kind !== 'emote' && msg.kind !== 'desc'}
    <header>
      <span class="who" style:color={msg.color}>{msg.speaker}</span>
      {#if msg.kind === 'whisper'}<span class="tag">whisper {whisperLabel}</span>{/if}
      {#if msg.gm_only}<span class="tag">roll to GM</span>{/if}
      {#if msg.kind === 'ooc'}<span class="tag">out of character</span>{/if}
      {#if store.settings.chat_timestamps}<time>{time}</time>{/if}
    </header>
  {/if}

  {#if msg.kind === 'emote'}
    <p class="body"><span style:color={msg.color}>{msg.speaker}</span> {@render rich(parts)}</p>
  {:else if parts.length}
    <p class="body">{@render rich(parts)}</p>
  {/if}

  {#if msg.roll?.card}
    <CombatCard {msg} card={msg.roll.card} />
  {/if}

  {#if template}
    <div class="template">
      {#if template.title}<div class="template-title">{@render rich(split(template.title))}</div>{/if}
      {#each template.fields as [key, value], i (i)}
        <div class="template-row"><span class="key">{key}</span><span class="value">{@render rich(split(value))}</span></div>
      {/each}
    </div>
  {/if}

  {#if msg.roll?.main}
    <RollView roll={msg.roll.main} />
  {/if}
</article>

<style>
  .template {
    margin-top: 4px;
    border: 1px solid var(--border);
    border-radius: 8px;
    overflow: hidden;
    background: var(--surface-2);
  }
  .template-title {
    padding: 5px 10px;
    font-weight: 700;
    color: var(--accent-contrast);
    background: var(--gradient-accent);
  }
  .template-row {
    display: grid;
    grid-template-columns: minmax(70px, auto) 1fr;
    gap: 8px;
    padding: 4px 10px;
    border-top: 1px solid var(--border);
    font-size: 0.85rem;
  }
  .template-row:first-of-type {
    border-top: none;
  }
  .key {
    font-weight: 600;
    color: var(--text-muted);
  }
  .value {
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }
  .chat-button {
    border: 1px solid var(--accent);
    background: color-mix(in srgb, var(--accent) 18%, transparent);
    color: var(--text);
    border-radius: 6px;
    padding: 1px 8px;
    cursor: pointer;
    font: inherit;
    font-size: 0.8rem;
  }
  .chat-button:hover {
    background: color-mix(in srgb, var(--accent) 32%, transparent);
  }
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
    background: color-mix(in srgb, var(--whisper) 12%, transparent);
  }
  .gm-only {
    background: color-mix(in srgb, var(--gm) 10%, transparent);
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
  .inline.crit {
    border-color: var(--success);
    background: color-mix(in srgb, var(--success) 25%, var(--bg));
  }
  .inline.fumble {
    border-color: var(--danger);
    background: color-mix(in srgb, var(--danger) 25%, var(--bg));
  }
</style>
