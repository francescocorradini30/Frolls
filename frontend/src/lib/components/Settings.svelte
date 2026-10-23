<script lang="ts">
  import type { Measurement } from '../net/protocol'
  import { store } from '../state/game.svelte'
  import ColorSwatches from './ColorSwatches.svelte'

  let { onLeave }: { onLeave: () => void } = $props()

  const me = $derived(store.me)

  const MEASUREMENTS: { value: Measurement; label: string; cell: string }[] = [
    { value: 'metric', label: 'Metric', cell: '1 cell = 1.5 m' },
    { value: 'imperial', label: 'Imperial', cell: '1 cell = 5 ft' },
  ]
</script>

{#if me}
  <form class="settings" onsubmit={(e) => e.preventDefault()}>
    <h4>Profile</h4>
    <label class="field">
      <span>Name</span>
      <input
        value={me.name}
        maxlength="60"
        onchange={(e) => {
          const name = e.currentTarget.value.trim()
          if (name) store.updateProfile({ name })
          else e.currentTarget.value = me.name
        }}
      />
    </label>
    <div class="field">
      <span>Color</span>
      <ColorSwatches value={me.color} onchange={(color) => store.updateProfile({ color })} />
    </div>

    <h4>Map</h4>
    <div class="field">
      <span>Mouse wheel</span>
      <div class="segmented">
        <button type="button" class:active={store.settings.wheel === 'zoom'} onclick={() => store.updateSettings({ wheel: 'zoom' })}>
          Zoom
        </button>
        <button type="button" class:active={store.settings.wheel === 'pan'} onclick={() => store.updateSettings({ wheel: 'pan' })}>
          Pan the map
        </button>
      </div>
    </div>
    {#if store.settings.wheel === 'pan'}
      <p class="hint muted">Use Ctrl + wheel to zoom. Shift + wheel pans horizontally.</p>
    {/if}

    <h4>Chat</h4>
    <label class="check">
      <input
        type="checkbox"
        checked={store.settings.chat_timestamps}
        onchange={(e) => store.updateSettings({ chat_timestamps: e.currentTarget.checked })}
      />
      Show message timestamps
    </label>

    {#if store.isGm}
      <h4>Game</h4>
      <div class="field">
        <span>Measurement units</span>
        <div class="segmented">
          {#each MEASUREMENTS as m (m.value)}
            <button
              type="button"
              class:active={store.measurement === m.value}
              title={m.cell}
              onclick={() => store.send({ type: 'game.settings', measurement: m.value })}
            >
              {m.label}
            </button>
          {/each}
        </div>
      </div>
      <p class="hint muted">
        {MEASUREMENTS.find((m) => m.value === store.measurement)?.cell}. Switching systems converts the page scales
        (5 ft = 1.5 m, 1 mi = 1.5 km) for all players.
      </p>
    {/if}

    <button type="button" class="btn danger leave" onclick={onLeave}>Leave game</button>
  </form>
{/if}

<style>
  .leave {
    margin-top: 12px;
  }
</style>
