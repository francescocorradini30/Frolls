/**
 * Frolls visual identity: the only place where colours are defined.
 *
 * Style: flat neon-pastel illustration on deep indigo, with violet → periwinkle → sky
 * gradients and pink / mint accents. Every new graphic element must use these values
 * (CSS through the `--*` variables, Pixi and stored colours through `palette`), never
 * a new hex literal.
 */

export const palette = {
  // Indigo night, from deepest to lightest surface.
  ink950: '#100e24',
  ink900: '#16142f',
  ink800: '#1e1b3e',
  ink700: '#27234f',
  ink600: '#312c61',
  ink500: '#433c7c',

  // Signature hues.
  violet: '#a27dff',
  periwinkle: '#7d8cff',
  sky: '#5cc8ff',
  pink: '#ff8fd2',
  mint: '#52e3a6',
  peach: '#ffb48f',
  butter: '#ffdb7a',
  rose: '#ff6b8e',

  // Light tones.
  cream: '#fff4fa',
  lavender: '#ece9ff',
  haze: '#a7a2d8',
} as const

/** Semantic CSS tokens, written on :root by `applyTheme()`. */
const cssTokens: Record<string, string> = {
  '--bg': palette.ink950,
  '--surface': palette.ink900,
  '--surface-2': palette.ink800,
  '--surface-3': palette.ink700,
  '--surface-4': palette.ink600,
  '--border': palette.ink500,
  '--text': palette.lavender,
  '--text-muted': palette.haze,
  '--accent': palette.violet,
  '--accent-2': palette.periwinkle,
  '--accent-3': palette.sky,
  '--accent-contrast': palette.ink950,
  '--highlight': palette.pink,
  '--success': palette.mint,
  '--danger': palette.rose,
  '--online': palette.mint,
  '--connecting': palette.butter,
  '--offline': palette.rose,
  '--whisper': palette.pink,
  '--gm': palette.sky,
  '--gradient-accent': `linear-gradient(135deg, ${palette.violet} 0%, ${palette.periwinkle} 50%, ${palette.sky} 100%)`,
  '--gradient-surface': `linear-gradient(180deg, ${palette.ink800} 0%, ${palette.ink900} 100%)`,
  '--glow': `radial-gradient(ellipse at 15% 0%, rgb(162 125 255 / 0.18) 0%, transparent 55%), radial-gradient(ellipse at 90% 100%, rgb(92 200 255 / 0.12) 0%, transparent 55%)`,
  '--halftone': `radial-gradient(rgb(236 233 255 / 0.05) 1px, transparent 1.5px)`,
  '--shadow': '0 12px 40px rgb(6 4 24 / 0.6)',
  '--backdrop': 'rgb(10 8 32 / 0.65)',
}

export function applyTheme(root: HTMLElement = document.documentElement): void {
  for (const [name, value] of Object.entries(cssTokens)) root.style.setProperty(name, value)
}

/** Colours drawn by the map engine. */
export const canvasColors = {
  background: palette.ink950,
  accent: palette.violet,
  handle: palette.cream,
  outline: palette.ink950,
  label: palette.cream,
  barTrack: palette.ink950,
  tokenBorder: palette.cream,
  template: palette.periwinkle,
} as const

/** Colours a player can pick when joining. */
export const PLAYER_COLORS = [
  palette.violet,
  palette.periwinkle,
  palette.sky,
  palette.mint,
  palette.butter,
  palette.peach,
  palette.pink,
  palette.rose,
] as const

/** Random fill for new tokens without an image. */
export const TOKEN_COLORS = [
  palette.violet,
  palette.periwinkle,
  palette.sky,
  palette.mint,
  palette.peach,
  palette.pink,
  palette.ink500,
] as const

export const DEFAULT_TOKEN_COLOR = palette.ink500

/** Token bars 1-3: health, resource, extra. */
export const BAR_COLORS = [palette.mint, palette.sky, palette.rose] as const

export const AURA_COLORS = [palette.butter, palette.sky] as const

export const DEFAULT_DRAW_COLOR = palette.pink
