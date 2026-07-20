import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface PanelData {
  id: string
  pluginId: string
  data: any
  component: any
}

export const usePluginStore = defineStore('plugin', () => {
  const plugins = ref<any[]>([])
  const panels = ref<PanelData[]>([])

  async function loadPlugins() {
    plugins.value = await window.mqbox.plugin.list()
    const panelInfos = await window.mqbox.plugin.getPanels()

    const results: PanelData[] = []
    for (const p of panelInfos) {
      const data = await window.mqbox.plugin.execute(p.pluginId, 'getPanelData')
      results.push({ id: p.id, pluginId: p.pluginId, data, component: null })
    }
    panels.value = results
  }

  async function executeCommand(pluginId: string, command: string, args?: unknown) {
    return await window.mqbox.plugin.execute(pluginId, command, args)
  }

  return { plugins, panels, loadPlugins, executeCommand }
})
