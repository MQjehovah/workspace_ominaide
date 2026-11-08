import { ipcMain } from 'electron'
import { getServers, addServer, updateServer, removeServer, listTools, callTool, refresh, getServerStatus } from './mcp-manager'
import { listSkills, createSkill, updateSkill, deleteSkill, toggleSkill, installSkillFromFolder, installSkillFromUrl, pickSkillFolder } from './skills'

export function registerMcpIpc() {
  ipcMain.handle('mcp:list', () => getServers().map(s => ({ ...s, status: getServerStatus(s.id) })))

  ipcMain.handle('mcp:add', async (_e, cfg: any) => {
    try { const server = addServer(cfg); return { ok: true, server } } catch (e: any) { return { ok: false, error: e.message } }
  })

  ipcMain.handle('mcp:update', async (_e, id: string, patch: any) => {
    try { const server = updateServer(id, patch); return { ok: true, server } } catch (e: any) { return { ok: false, error: e.message } }
  })

  ipcMain.handle('mcp:remove', async (_e, id: string) => {
    try { await removeServer(id); return { ok: true } } catch (e: any) { return { ok: false, error: e.message } }
  })

  ipcMain.handle('mcp:refresh', async () => {
    try { await refresh(); return { ok: true, tools: await listTools() } } catch (e: any) { return { ok: false, error: e.message } }
  })

  ipcMain.handle('mcp:tools', async () => {
    try { return { ok: true, tools: await listTools() } } catch (e: any) { return { ok: false, error: e.message } }
  })

  ipcMain.handle('mcp:test-call', async (_e, name: string, args: any) => callTool(name, args))

  ipcMain.handle('skills:list', () => listSkills())

  ipcMain.handle('skills:create', async (_e, data: any) => {
    try { return { ok: true, skill: createSkill(data) } } catch (e: any) { return { ok: false, error: e.message } }
  })

  ipcMain.handle('skills:update', async (_e, id: string, patch: any) => {
    try { return { ok: true, skill: updateSkill(id, patch) } } catch (e: any) { return { ok: false, error: e.message } }
  })

  ipcMain.handle('skills:toggle', async (_e, id: string, enabled: boolean) => {
    try { return { ok: true, skill: toggleSkill(id, enabled) } } catch (e: any) { return { ok: false, error: e.message } }
  })

  ipcMain.handle('skills:delete', async (_e, id: string) => {
    try { deleteSkill(id); return { ok: true } } catch (e: any) { return { ok: false, error: e.message } }
  })

  ipcMain.handle('skills:install-folder', async () => {
    try {
      const folder = await pickSkillFolder()
      if (!folder) return { ok: false, canceled: true }
      return { ok: true, skill: await installSkillFromFolder(folder) }
    } catch (e: any) { return { ok: false, error: e.message } }
  })

  ipcMain.handle('skills:install-url', async (_e, url: string) => {
    try { return { ok: true, skill: await installSkillFromUrl(url) } } catch (e: any) { return { ok: false, error: e.message } }
  })


}
