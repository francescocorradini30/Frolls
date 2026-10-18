<script lang="ts">
  import { store } from '../state/game.svelte'
</script>

<div class="toasts" aria-live="polite">
  {#each store.toasts as t (t.id)}
    <div class="toast panel">{t.text}</div>
  {/each}
</div>

<style>
  .toasts {
    position: fixed;
    top: calc(var(--topbar-h) + 10px);
    left: 50%;
    transform: translateX(-50%);
    z-index: 200;
    display: flex;
    flex-direction: column;
    gap: 6px;
    pointer-events: none;
  }
  .toast {
    padding: 8px 14px;
    border-color: var(--danger);
    max-width: min(480px, calc(100vw - 32px));
  }
</style>
