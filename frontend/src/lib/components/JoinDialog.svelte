<script lang="ts">
  import { newIdentity, type Identity } from '../state/identity'
  import { PLAYER_COLORS } from '../theme'

  let { onJoin }: { onJoin: (identity: Identity) => void } = $props()


  let name = $state('')
  let color = $state<string>(PLAYER_COLORS[Math.floor(Math.random() * PLAYER_COLORS.length)])
  let isGm = $state(false)

  function submit(e: SubmitEvent) {
    e.preventDefault()
    const trimmed = name.trim()
    if (!trimmed) return
    onJoin(newIdentity(trimmed, color, isGm))
  }
</script>

<div class="backdrop">
  <form class="card" onsubmit={submit}>
    <h1 class="text-gradient">Frolls</h1>
    <p class="muted">Entra nella partita. Ogni scheda del browser è un giocatore diverso.</p>

    <label class="field">
      <span>Nome</span>
      <!-- svelte-ignore a11y_autofocus -->
      <input bind:value={name} maxlength="60" placeholder="Es. Aria la Ranger" autofocus />
    </label>

    <div class="field">
      <span>Colore</span>
      <div class="swatches">
        {#each PLAYER_COLORS as c (c)}
          <button
            type="button"
            class="swatch"
            class:active={color === c}
            style:background={c}
            style:--c={c}
            aria-label={`Colore ${c}`}
            onclick={() => (color = c)}
          ></button>
        {/each}
        <input type="color" bind:value={color} aria-label="Colore personalizzato" />
      </div>
    </div>

    <div class="field">
      <span>Ruolo</span>
      <div class="segmented">
        <button type="button" class:active={!isGm} onclick={() => (isGm = false)}>Giocatore</button>
        <button type="button" class:active={isGm} onclick={() => (isGm = true)}>Game Master</button>
      </div>
    </div>

    <button class="btn primary" type="submit" disabled={!name.trim()}>Entra</button>
  </form>
</div>

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    display: grid;
    place-items: center;
    padding: 16px;
    background: var(--halftone) 0 0 / 6px 6px, var(--glow), var(--bg);
  }
  .card {
    width: min(420px, 100%);
    display: flex;
    flex-direction: column;
    gap: 18px;
    padding: 28px;
    background: var(--gradient-surface);
    border: 1px solid var(--border);
    border-radius: 18px;
    box-shadow:
      var(--shadow),
      0 0 0 1px color-mix(in srgb, var(--accent) 18%, transparent);
  }
  h1 {
    margin: 0;
    font-size: 2.2rem;
    letter-spacing: 0.02em;
    width: fit-content;
  }
  p {
    margin: -8px 0 0;
  }
  .swatches {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    align-items: center;
  }
  .swatch {
    width: 28px;
    height: 28px;
    border-radius: 50%;
    border: 2px solid transparent;
    cursor: pointer;
  }
  .swatch.active {
    border-color: var(--text);
    box-shadow: 0 0 0 2px var(--bg), 0 0 12px var(--c, transparent);
  }
  input[type='color'] {
    width: 32px;
    height: 32px;
    padding: 0;
    border: none;
    background: none;
  }
</style>
