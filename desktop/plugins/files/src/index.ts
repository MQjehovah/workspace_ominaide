import type {PluginModule, PluginContext} from "../../../src/shared/types";

export default {
  async activate(context: PluginContext) {
    async function loadFiles() {
      try {
        const data = await context.api.get("/files?page_size=5");
        return {files: data?.files?.filter((f: any) => !f.is_folder) || [], total: data?.total || 0};
      } catch {
        return {files: [], total: 0};
      }
    }

    context.registerCommand("getPanelData", async () => {
      const result = await loadFiles();
      const files = result.files || [];
      return {
        title: "文件管理",
        subtitle: `${result.total || 0} 个文件`,
        items: files.slice(0, 5).map((f: any) => ({
          title: f.original_name || f.name || "",
          subtitle: f.size ? `${(f.size / 1024).toFixed(1)} KB` : "",
          action: "open",
          actionArgs: {id: f.id, path: f.object_key},
        })),
      };
    });

    context.registerCommand("getPageData", async () => {
      try {
        const data = await context.api.get("/files?page_size=200");
        return {files: data?.files || [], total: data?.total || 0};
      } catch {
        return {files: [], total: 0};
      }
    });

    context.registerCommand("delete", async (args: any) => {
      try {
        await context.api.delete(`/files/${args.id}`);
        return {success: true};
      } catch {
        return {success: false};
      }
    });

    context.registerCommand("rename", async (args: any) => {
      try {
        await context.api.put(`/files/${args.id}/rename`, {new_name: args.name});
        return {success: true};
      } catch {
        return {success: false};
      }
    });

    context.registerCommand("move", async (args: any) => {
      try {
        await context.api.put(`/files/${args.id}/move`, {new_folder_path: args.folder});
        return {success: true};
      } catch {
        return {success: false};
      }
    });

    context.registerCommand("favorite", async (args: any) => {
      try {
        await context.api.post(`/files/${args.id}/favorite`);
        return {success: true};
      } catch {
        return {success: false};
      }
    });

    context.registerCommand("createFolder", async (args: any) => {
      try {
        await context.api.post("/files/folder", {name: args.name, parent_path: args.path || "/"});
        return {success: true};
      } catch {
        return {success: false};
      }
    });

    context.registerCommand("upload", async (args: any) => {
      try {
        const {filename, mime_type, folder_path} = args;
        const uploadInfo = await context.api.post("/files/upload-url", {filename, mime_type: mime_type || "application/octet-stream", folder_path: folder_path || "/"});
        if (!uploadInfo?.upload_url) return {success: false};
        await context.api.post("/files/confirm", {file_id: uploadInfo.file_id});
        return {success: true, upload_url: uploadInfo.upload_url, file_id: uploadInfo.file_id, object_key: uploadInfo.object_key};
      } catch {
        return {success: false};
      }
    });
  },
  deactivate() {},
} as PluginModule;
