<script lang="ts">
  import { PLAYER_COLORS } from '../theme'

  let { value, onchange }: { value: string; onchange: (color: string) => void } = $props()
</script>

<div class="swatches">
  {#each PLAYER_COLORS as c (c)}
    <button
      type="button"
      class="swatch"
      class:active={value === c}
      style:background={c}
      style:--c={c}
      aria-label={`Color ${c}`}
      onclick={() => onchange(c)}
    ></button>
  {/each}
  <input type="color" {value} onchange={(e) => onchange(e.currentTarget.value)} aria-label="Custom color" />
</div>

<style>
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
    box-shadow:
      0 0 0 2px var(--bg),
      0 0 12px var(--c, transparent);
  }
  input[type='color'] {
    width: 32px;
    height: 32px;
    padding: 0;
    border: none;
    background: none;
  }
</style>
