import client from './client'

export interface PluginInfo {
  name: string
  version: string
  title: string
  description: string | null
  icon: string | null
  enabled: boolean
  installed_at: string
}

export async function fetchPlugins(): Promise<PluginInfo[]> {
  const res = await client.get<PluginInfo[]>('/plugins')
  return res.data
}
