import { defineStore } from 'pinia'

export interface PluginManifest {
  name: string
  title: string
  icon: string
  description?: string
  version?: string
  routes: {
    main: string
    settings?: string
  }
}

export const usePluginStore = defineStore('plugin', {
  state: () => ({
    installed: [] as PluginManifest[],
    componentMap: {} as Record<string, any>
  }),
  actions: {
    register(manifest: PluginManifest, component?: any) {
      if (!this.installed.find(p => p.name === manifest.name)) {
        this.installed.push(manifest)
      }
      if (component) {
        this.componentMap[manifest.name] = component
      }
    }
  }
})
