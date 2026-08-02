import type {PluginModule, PluginContext} from "../../../src/shared/types";

// Backend stores naive UTC; parse as UTC so display is correct.
function fmtDate(iso: string): string {
  if (!iso) return ""
  const d = /[zZ]|[+-]\d{2}:?\d{2}$/.test(iso) ? new Date(iso) : new Date(iso + "Z")
  if (isNaN(d.getTime())) return ""
  return `${d.getMonth() + 1}/${d.getDate()}`
}

export default {
  async activate(context: PluginContext) {
    context.registerCommand("getPanelData", async () => {
      try {
        const data = (await context.api.get("/plugins/notes/tree")) || [];
        const notesArr = Array.isArray(data) ? data : [];
        return {
          title: "笔记",
          subtitle: `${notesArr.length} 篇笔记`,
          items: notesArr.slice(0, 5).map((n: any) => ({
            title: n.title || n.name || "无标题",
            subtitle: fmtDate(n.updated_at || n.created_at),
            action: "open",
            actionArgs: {id: n.id},
          })),
          buttons: [{label: "新建", command: "create"}],
        };
      } catch {
        return {title: "笔记", subtitle: "0 篇笔记", buttons: [{label: "新建", command: "create"}]};
      }
    });

    context.registerCommand("getPageData", async () => {
      try {
        const data = await context.api.get("/plugins/notes");
        return {notes: data || []};
      } catch {
        return {notes: []};
      }
    });

    context.registerCommand("create", async () => {
      try {
        const res = await context.api.post("/plugins/notes", {title: "无标题", content: ""});
        context.openPage("notes");
        return {success: true, id: res?.id};
      } catch {
        return {success: false};
      }
    });

    context.registerCommand("open", async () => {
      context.openPage("notes");
    });

    // Search provider for notes (merged from quick-notes).
    context.registerSearchProvider({
      keyword: "note",
      name: "笔记",
      priority: 40,
      onSearch: async (query: string) => {
        if (!query) {
          return [{
            title: "打开笔记",
            subtitle: "快速记录与整理",
            icon: "note",
            action: "notes:open",
            pluginId: "notes",
          }];
        }
        try {
          const res = await context.api.get(`/plugins/notes/search?q=${encodeURIComponent(query)}`);
          const items = res || [];
          return items.slice(0, 5).map((n: any) => ({
            title: n.title || "无标题",
            subtitle: n.updated_at ? fmtDate(n.updated_at) : "",
            icon: "note",
            action: "notes:open",
            actionArgs: {id: n.id},
            pluginId: "notes",
          }));
        } catch {
          return [];
        }
      },
    });
  },
  deactivate() {},
} as PluginModule;
