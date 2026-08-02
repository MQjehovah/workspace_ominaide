import type { PluginModule, PluginContext } from "../../../src/shared/types";

const TYPE_META: Record<string, { label: string; icon: string; color: string }> = {
  app:    { label: "应用",   icon: "🚀", color: "#6366f1" },
  url:    { label: "网页",   icon: "🌐", color: "#0ea5e9" },
  folder: { label: "文件夹", icon: "📁", color: "#f59e0b" },
  script: { label: "脚本",   icon: "⚙️", color: "#10b981" },
  command:{ label: "命令",   icon: "⌨️", color: "#ef4444" },
};

const STORAGE_KEY = "quicklinks";
let ctx: PluginContext;

function uid(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

async function loadLinks(): Promise<any[]> {
  const data = await ctx.storage.get(STORAGE_KEY);
  return Array.isArray(data) ? data : [];
}

async function saveLinks(links: any[]) {
  await ctx.storage.set(STORAGE_KEY, links);
}

function splitArgs(args?: string): string[] {
  if (!args) return [];
  return args.split(/\s+/).filter(Boolean);
}

async function executeLink(link: any): Promise<any> {
  const target = String(link.target || "").trim();
  if (!target) return { ok: false, error: "目标为空" };
  switch (link.type) {
    case "url": {
      const err = await ctx.shell?.openExternal(target);
      if (err) return { ok: false, error: err };
      return { ok: true };
    }
    case "app": {
      // Launch exe directly (spawn detached) — most reliable for applications
      const ext = (target.split(".").pop() || "").toLowerCase();
      if (ext === "exe" || ext === "bat" || ext === "cmd" || ext === "lnk") {
        return (await ctx.signal("shell:exec", target, [])) || { ok: true };
      }
      const err = await ctx.shell?.openPath(target);
      if (err) return { ok: false, error: err };
      return { ok: true };
    }
    case "folder": {
      const err = await ctx.shell?.openPath(target);
      if (err) return { ok: false, error: err };
      return { ok: true };
    }
    case "script": {
      const ext = (target.split(".").pop() || "").toLowerCase();
      if (ext === "bat" || ext === "cmd") {
        return (await ctx.signal("shell:exec", "cmd.exe", ["/c", target, ...splitArgs(link.args)])) || { ok: true };
      } else if (ext === "ps1") {
        return (await ctx.signal("shell:exec", "powershell.exe", ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", target, ...splitArgs(link.args)])) || { ok: true };
      } else {
        return (await ctx.signal("shell:exec", target, splitArgs(link.args))) || { ok: true };
      }
    }
    case "command":
      return (await ctx.signal("shell:exec", process.platform === "win32" ? "cmd.exe" : "/bin/sh", [process.platform === "win32" ? "/c" : "-c", target])) || { ok: true };
    default:
      return { ok: false, error: "未知类型" };
  }
}

export default {
  async activate(context: PluginContext) {
    ctx = context;

    context.registerCommand("getPanelData", async () => {
      const links = await loadLinks();
      return {
        title: "快捷指令",
        subtitle: `${links.length} 个快捷指令`,
        itemsLayout: "grid",
        items: [
          ...links.slice(0, 7).map((l: any) => {
            const meta = TYPE_META[l.type] || TYPE_META.command;
            return {
              title: l.name || meta.label,
              subtitle: meta.label,
              icon: l.icon || meta.icon,
              color: l.color || meta.color,
              action: "run",
              actionArgs: { id: l.id },
            };
          }),
          {
            title: "添加",
            subtitle: "新建快捷指令",
            icon: "＋",
            color: "#e2e8f0",
            action: "openPage",
          },
        ],
      };
    });

    context.registerCommand("getPageData", async () => {
      return { links: await loadLinks(), typeMeta: TYPE_META };
    });

    context.registerCommand("openPage", async () => {
      context.openPage("quicklinks");
    });

    context.registerCommand("add", async (args: any) => {
      const links = await loadLinks();
      const link = {
        id: uid(),
        name: args?.name || "未命名",
        type: args?.type || "command",
        target: args?.target || "",
        args: args?.args || "",
        icon: args?.icon || "",
        color: args?.color || "",
        createdAt: Date.now(),
      };
      links.push(link);
      await saveLinks(links);
      context.signal("panel:updated");
      return { ok: true, id: link.id };
    });

    context.registerCommand("update", async (args: any) => {
      const links = await loadLinks();
      const idx = links.findIndex((l: any) => l.id === args?.id);
      if (idx < 0) return { ok: false, error: "未找到" };
      links[idx] = { ...links[idx], ...args?.patch };
      await saveLinks(links);
      context.signal("panel:updated");
      return { ok: true };
    });

    context.registerCommand("remove", async (args: any) => {
      const links = (await loadLinks()).filter((l: any) => l.id !== args?.id);
      await saveLinks(links);
      context.signal("panel:updated");
      return { ok: true };
    });

    context.registerCommand("move", async (args: any) => {
      const links = await loadLinks();
      const idx = links.findIndex((l: any) => l.id === args?.id);
      const dir = args?.dir || 1;
      const target = idx + dir;
      if (idx < 0 || target < 0 || target >= links.length) return { ok: false };
      const [item] = links.splice(idx, 1);
      links.splice(target, 0, item);
      await saveLinks(links);
      context.signal("panel:updated");
      return { ok: true };
    });

    context.registerCommand("run", async (args: any) => {
      ctx.log?.("info", `run command called: ${JSON.stringify(args)}`);
      const links = await loadLinks();
      ctx.log?.("info", `links count: ${links.length}`);
      const link = links.find((l: any) => l.id === args?.id);
      if (!link) {
        ctx.log?.("error", "link not found");
        return { ok: false, error: "未找到该快捷指令" };
      }
      ctx.log?.("info", `executing link: ${link.name} type=${link.type} target=${link.target}`);
      const result = await executeLink(link);
      ctx.log?.("info", `exec result: ${JSON.stringify(result)}`);
      if (result && result.ok === false) {
        ctx.notification?.show(`快捷指令失败：${link.name}`, result.error || "执行出错");
      }
      return result;
    });

    context.registerSearchProvider({
      keyword: "quick",
      name: "快捷指令",
      priority: 60,
      onSearch: async (query: string) => {
        const links = await loadLinks();
        if (!query) {
          return [{
            type: "quicklink",
            title: "打开快捷指令",
            subtitle: "一键启动软件 / 网页 / 脚本",
            icon: "quicklinks",
            action: "openPage",
            pluginId: "quicklinks",
          }];
        }
        const q = query.toLowerCase();
        return links
          .filter((l: any) => (l.name || "").toLowerCase().includes(q) || (l.target || "").toLowerCase().includes(q))
          .slice(0, 6)
          .map((l: any) => {
            const meta = TYPE_META[l.type] || TYPE_META.command;
            return {
              type: "quicklink",
              title: l.name || meta.label,
              subtitle: `${meta.label} · ${l.target}`,
              icon: l.icon || meta.icon,
              action: "run",
              actionArgs: { id: l.id },
              pluginId: "quicklinks",
            };
          });
      },
    });
  },
  deactivate() {},
} as PluginModule;
