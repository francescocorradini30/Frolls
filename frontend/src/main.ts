import { mount } from 'svelte'
import './app.css'
import { applyTheme } from './lib/theme'
import App from './App.svelte'

applyTheme()

const app = mount(App, {
  target: document.getElementById('app')!,
})

export default app
