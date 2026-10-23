/** Mirror of PRESETS in backend/app/rules5e/effects.py: what the effect dialog offers. */
export const EFFECT_PRESETS: { key: string; label: string; concentration: boolean; save: boolean; note: string }[] = [
  { key: 'bless', label: 'Bless', concentration: true, save: false, note: '+1d4 to attacks and saves, 1 minute' },
  { key: 'bane', label: 'Bane', concentration: true, save: false, note: '−1d4 to attacks and saves, 1 minute' },
  { key: 'guidance', label: 'Guidance', concentration: true, save: false, note: '+1d4 to ability checks, 1 minute' },
  { key: 'resistance', label: 'Resistance', concentration: true, save: false, note: '+1d4 to saving throws, 1 minute' },
  { key: 'shield_of_faith', label: 'Shield of Faith', concentration: true, save: false, note: '+2 AC, 10 minutes' },
  { key: 'haste', label: 'Haste', concentration: true, save: false, note: '+2 AC, advantage on Dex saves, 1 minute' },
  { key: 'slow', label: 'Slow', concentration: true, save: true, note: '−2 AC and saves; Wis save at the end of its turns' },
  { key: 'hold_person', label: 'Hold Person', concentration: true, save: true, note: 'Paralyzed; Wis save at the end of its turns' },
  { key: 'faerie_fire', label: 'Faerie Fire', concentration: true, save: false, note: 'Attacks against it have advantage' },
  { key: 'invisibility', label: 'Invisibility', concentration: true, save: false, note: 'Invisible, 1 hour' },
  { key: 'shield', label: 'Shield', concentration: false, save: false, note: '+5 AC until the start of your next turn' },
  { key: 'dodge', label: 'Dodge', concentration: false, save: false, note: 'Attacks against it have disadvantage until your next turn' },
  { key: 'help', label: 'Help', concentration: false, save: false, note: 'Advantage on the next attack or check' },
  { key: 'frightened', label: 'Frightened', concentration: false, save: true, note: 'Frightened; Wis save at the end of its turns' },
]
