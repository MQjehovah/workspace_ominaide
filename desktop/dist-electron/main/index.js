"use strict";
var __defProp = Object.defineProperty;
var __typeError = (msg) => {
  throw TypeError(msg);
};
var __defNormalProp = (obj, key, value) => key in obj ? __defProp(obj, key, { enumerable: true, configurable: true, writable: true, value }) : obj[key] = value;
var __publicField = (obj, key, value) => __defNormalProp(obj, typeof key !== "symbol" ? key + "" : key, value);
var __accessCheck = (obj, member, msg) => member.has(obj) || __typeError("Cannot " + msg);
var __privateGet = (obj, member, getter) => (__accessCheck(obj, member, "read from private field"), getter ? getter.call(obj) : member.get(obj));
var __privateAdd = (obj, member, value) => member.has(obj) ? __typeError("Cannot add the same private member more than once") : member instanceof WeakSet ? member.add(obj) : member.set(obj, value);
var __privateSet = (obj, member, value, setter) => (__accessCheck(obj, member, "write to private field"), setter ? setter.call(obj, value) : member.set(obj, value), value);
var __privateMethod = (obj, member, method) => (__accessCheck(obj, member, "access private method"), method);
var _filename, _tempFilename, _locked, _prev, _next, _nextPromise, _nextData, _Writer_instances, add_fn, write_fn, _filename2, _writer, _adapter, _parse, _stringify;
const electron = require("electron");
const require$$1 = require("path");
const require$$6 = require("fs");
require("node:fs");
const promises = require("node:fs/promises");
const path = require("node:path");
const node_url = require("node:url");
function findPluginDirs() {
  const searchPaths = [
    require$$1.join(__dirname, "../../../plugins"),
    // dev
    require$$1.join(__dirname, "../../plugins"),
    // dev alt
    require$$1.join(electron.app.getPath("userData"), "plugins")
    // production
  ];
  const dirs = [];
  for (const base of searchPaths) {
    if (!require$$6.existsSync(base)) continue;
    for (const entry of require$$6.readdirSync(base, { withFileTypes: true })) {
      if (entry.isDirectory()) {
        const pluginDir = require$$1.join(base, entry.name);
        if (require$$6.existsSync(require$$1.join(pluginDir, "package.json"))) {
          dirs.push(pluginDir);
        }
      }
    }
  }
  return [...new Set(dirs)];
}
function loadPlugins() {
  const plugins2 = /* @__PURE__ */ new Map();
  for (const dir of findPluginDirs()) {
    try {
      const pkg = JSON.parse(require$$6.readFileSync(require$$1.join(dir, "package.json"), "utf-8"));
      const mqbox = pkg.omniaide || pkg.mqbox || {};
      const manifest = {
        id: mqbox.id || pkg.name,
        name: pkg.name,
        displayName: mqbox.displayName || pkg.displayName || pkg.name,
        description: pkg.description,
        version: pkg.version,
        icon: mqbox.icon,
        keywords: mqbox.keywords || [],
        permissions: mqbox.permissions || [],
        builtin: mqbox.builtin !== false,
        main: pkg.main || "dist/index.js"
      };
      plugins2.set(manifest.id, { id: manifest.id, manifest, path: dir, enabled: true });
    } catch (e) {
      console.error(`Failed to load plugin from ${dir}:`, e);
    }
  }
  return plugins2;
}
function checkArgs(adapter, defaultData) {
  if (adapter === void 0)
    throw new Error("lowdb: missing adapter");
  if (defaultData === void 0)
    throw new Error("lowdb: missing default data");
}
class Low {
  constructor(adapter, defaultData) {
    __publicField(this, "adapter");
    __publicField(this, "data");
    checkArgs(adapter, defaultData);
    this.adapter = adapter;
    this.data = defaultData;
  }
  async read() {
    const data = await this.adapter.read();
    if (data)
      this.data = data;
  }
  async write() {
    if (this.data)
      await this.adapter.write(this.data);
  }
  async update(fn) {
    fn(this.data);
    await this.write();
  }
}
function getTempFilename(file) {
  const f = file instanceof URL ? node_url.fileURLToPath(file) : file.toString();
  return path.join(path.dirname(f), `.${path.basename(f)}.tmp`);
}
async function retryAsyncOperation(fn, maxRetries, delayMs) {
  for (let i = 0; i < maxRetries; i++) {
    try {
      return await fn();
    } catch (error) {
      if (i < maxRetries - 1) {
        await new Promise((resolve) => setTimeout(resolve, delayMs));
      } else {
        throw error;
      }
    }
  }
}
class Writer {
  constructor(filename) {
    __privateAdd(this, _Writer_instances);
    __privateAdd(this, _filename);
    __privateAdd(this, _tempFilename);
    __privateAdd(this, _locked, false);
    __privateAdd(this, _prev, null);
    __privateAdd(this, _next, null);
    __privateAdd(this, _nextPromise, null);
    __privateAdd(this, _nextData, null);
    __privateSet(this, _filename, filename);
    __privateSet(this, _tempFilename, getTempFilename(filename));
  }
  async write(data) {
    return __privateGet(this, _locked) ? __privateMethod(this, _Writer_instances, add_fn).call(this, data) : __privateMethod(this, _Writer_instances, write_fn).call(this, data);
  }
}
_filename = new WeakMap();
_tempFilename = new WeakMap();
_locked = new WeakMap();
_prev = new WeakMap();
_next = new WeakMap();
_nextPromise = new WeakMap();
_nextData = new WeakMap();
_Writer_instances = new WeakSet();
// File is locked, add data for later
add_fn = function(data) {
  __privateSet(this, _nextData, data);
  __privateGet(this, _nextPromise) || __privateSet(this, _nextPromise, new Promise((resolve, reject) => {
    __privateSet(this, _next, [resolve, reject]);
  }));
  return new Promise((resolve, reject) => {
    var _a;
    (_a = __privateGet(this, _nextPromise)) == null ? void 0 : _a.then(resolve).catch(reject);
  });
};
write_fn = async function(data) {
  var _a, _b;
  __privateSet(this, _locked, true);
  try {
    await promises.writeFile(__privateGet(this, _tempFilename), data, "utf-8");
    await retryAsyncOperation(async () => {
      await promises.rename(__privateGet(this, _tempFilename), __privateGet(this, _filename));
    }, 10, 100);
    (_a = __privateGet(this, _prev)) == null ? void 0 : _a[0]();
  } catch (err) {
    if (err instanceof Error) {
      (_b = __privateGet(this, _prev)) == null ? void 0 : _b[1](err);
    }
    throw err;
  } finally {
    __privateSet(this, _locked, false);
    __privateSet(this, _prev, __privateGet(this, _next));
    __privateSet(this, _next, __privateSet(this, _nextPromise, null));
    if (__privateGet(this, _nextData) !== null) {
      const nextData = __privateGet(this, _nextData);
      __privateSet(this, _nextData, null);
      await this.write(nextData);
    }
  }
};
class TextFile {
  constructor(filename) {
    __privateAdd(this, _filename2);
    __privateAdd(this, _writer);
    __privateSet(this, _filename2, filename);
    __privateSet(this, _writer, new Writer(filename));
  }
  async read() {
    let data;
    try {
      data = await promises.readFile(__privateGet(this, _filename2), "utf-8");
    } catch (e) {
      if (e.code === "ENOENT") {
        return null;
      }
      throw e;
    }
    return data;
  }
  write(str) {
    return __privateGet(this, _writer).write(str);
  }
}
_filename2 = new WeakMap();
_writer = new WeakMap();
class DataFile {
  constructor(filename, { parse, stringify }) {
    __privateAdd(this, _adapter);
    __privateAdd(this, _parse);
    __privateAdd(this, _stringify);
    __privateSet(this, _adapter, new TextFile(filename));
    __privateSet(this, _parse, parse);
    __privateSet(this, _stringify, stringify);
  }
  async read() {
    const data = await __privateGet(this, _adapter).read();
    if (data === null) {
      return null;
    } else {
      return __privateGet(this, _parse).call(this, data);
    }
  }
  write(obj) {
    return __privateGet(this, _adapter).write(__privateGet(this, _stringify).call(this, obj));
  }
}
_adapter = new WeakMap();
_parse = new WeakMap();
_stringify = new WeakMap();
class JSONFile extends DataFile {
  constructor(filename) {
    super(filename, {
      parse: JSON.parse,
      stringify: (data) => JSON.stringify(data, null, 2)
    });
  }
}
function createSandbox(pluginInfo, commands2, searchProviders2) {
  const perms = pluginInfo.manifest.permissions || [];
  let storage = null;
  if (perms.includes("storage")) {
    const file = require$$1.join(electron.app.getPath("userData"), "plugin-data", `${pluginInfo.id}.json`);
    const adapter = new JSONFile(file);
    storage = new Low(adapter, {});
  }
  const notification = perms.includes("notification") ? { show: (title, body) => new electron.Notification({ title, body }).show() } : null;
  perms.includes("shell") ? {} : null;
  const api = {
    get: async (path2) => {
      const axios = (await Promise.resolve().then(() => require("./index-BJLg_xM-.js"))).default;
      const res = await axios.get(`${store.serverUrl}/api${path2}`, {
        headers: { Authorization: "Bearer " + store.token }
      });
      return res.data;
    },
    post: async (path2, body) => {
      const axios = (await Promise.resolve().then(() => require("./index-BJLg_xM-.js"))).default;
      const res = await axios.post(`${store.serverUrl}/api${path2}`, body, {
        headers: { Authorization: "Bearer " + store.token }
      });
      return res.data;
    },
    put: async (path2, body) => {
      const axios = (await Promise.resolve().then(() => require("./index-BJLg_xM-.js"))).default;
      const res = await axios.put(`${store.serverUrl}/api${path2}`, body, {
        headers: { Authorization: "Bearer " + store.token }
      });
      return res.data;
    },
    delete: async (path2) => {
      const axios = (await Promise.resolve().then(() => require("./index-BJLg_xM-.js"))).default;
      const res = await axios.delete(`${store.serverUrl}/api${path2}`, {
        headers: { Authorization: "Bearer " + store.token }
      });
      return res.data;
    }
  };
  const context = {
    plugin: pluginInfo,
    api,
    storage: {
      get: async (key) => {
        if (!storage) return null;
        await storage.read();
        return storage.data[key];
      },
      set: async (key, value) => {
        if (!storage) return;
        await storage.read();
        storage.data[key] = value;
        await storage.write();
      }
    },
    notification: notification || { show: () => {
    } },
    registerCommand: (name, handler) => {
      commands2.set(name, handler);
    },
    registerSearchProvider: (provider) => {
      searchProviders2.push(provider);
    }
  };
  return context;
}
const store = { serverUrl: "http://localhost:8000", token: "" };
function setAuth(serverUrl, token) {
  store.serverUrl = serverUrl;
  store.token = token;
}
const plugins = /* @__PURE__ */ new Map();
const modules = /* @__PURE__ */ new Map();
const commands = /* @__PURE__ */ new Map();
const searchProviders = [];
const panels = [];
function getPluginDir(plugin) {
  return plugin.path;
}
async function initPlugins() {
  const loaded = loadPlugins();
  for (const [id, info] of loaded) {
    try {
      const modulePath = require$$1.join(getPluginDir(info), info.manifest.main || "dist/index.js");
      const fileUrl = "file:///" + modulePath.replace(/\\/g, "/");
      const mod = await import(
        /* @vite-ignore */
        fileUrl
      );
      const plugin = mod.default || mod;
      if (plugin == null ? void 0 : plugin.activate) {
        const cmdMap = /* @__PURE__ */ new Map();
        commands.set(id, cmdMap);
        const ctx = createSandbox(info, cmdMap, searchProviders);
        await plugin.activate(ctx);
        modules.set(id, plugin);
        plugins.set(id, info);
        if (plugin.panel) {
          panels.push({ id: `${id}-panel`, pluginId: id, height: 120 });
        }
        console.log(`Plugin activated: ${info.manifest.displayName}`);
      }
    } catch (e) {
      console.error(`Failed to activate plugin ${id}:`, e);
    }
  }
}
function getPlugins() {
  return Array.from(plugins.values());
}
function getPanels() {
  return panels;
}
function getSearchProviders() {
  return searchProviders;
}
async function executeCommand(pluginId, command, args) {
  const cmdMap = commands.get(pluginId);
  if (!cmdMap) throw new Error(`Plugin ${pluginId} not found`);
  const handler = cmdMap.get(command);
  if (!handler) throw new Error(`Command ${command} not found in plugin ${pluginId}`);
  return handler(args);
}
function getPluginPage(pluginId) {
  const mod = modules.get(pluginId);
  return (mod == null ? void 0 : mod.page) || null;
}
function registerIpcHandlers() {
  electron.ipcMain.handle("auth:set", (_, serverUrl, token) => {
    setAuth(serverUrl, token);
  });
  electron.ipcMain.handle("plugin:list", () => getPlugins());
  electron.ipcMain.handle("plugin:get-panels", () => getPanels());
  electron.ipcMain.handle("plugin:get-page", (_, pluginId) => {
    const page = getPluginPage(pluginId);
    return page ? { pluginId, hasPage: true } : null;
  });
  electron.ipcMain.handle("plugin:execute", async (_, pluginId, command, args) => {
    try {
      return await executeCommand(pluginId, command, args);
    } catch (e) {
      return { error: e.message };
    }
  });
  electron.ipcMain.handle("search:plugin", async (_, keyword, query) => {
    const providers = getSearchProviders();
    const results = [];
    for (const p of providers) {
      if (keyword && p.keyword !== keyword) continue;
      try {
        const res = await Promise.race([
          Promise.resolve(p.onSearch(query)),
          new Promise((_2, reject) => setTimeout(() => reject([]), 2e3))
        ]);
        results.push(...res);
      } catch {
      }
      if (results.length >= 20) break;
    }
    return results.slice(0, 20);
  });
  electron.ipcMain.handle("search:get-providers", () => getSearchProviders().map((p) => ({ keyword: p.keyword, name: p.name, priority: p.priority })));
  electron.ipcMain.handle("window:hide", () => {
    const win = electron.BrowserWindow.getFocusedWindow();
    win == null ? void 0 : win.hide();
  });
}
let mainWindow = null;
let searchWindow = null;
let tray = null;
function createWindow(view = "main") {
  const win = new electron.BrowserWindow({
    width: view === "search" ? 640 : 380,
    height: view === "search" ? 400 : 600,
    resizable: false,
    frame: false,
    transparent: view === "search",
    webPreferences: {
      preload: require$$1.join(__dirname, "../preload/index.js"),
      contextIsolation: true,
      nodeIntegration: false
    }
  });
  if (process.env.VITE_DEV_SERVER_URL) {
    win.loadURL(`${process.env.VITE_DEV_SERVER_URL}?view=${view}`);
  } else {
    win.loadFile(require$$1.join(__dirname, "../../dist/index.html"), { query: { view } });
  }
  return win;
}
function showMainWindow() {
  if (mainWindow) {
    mainWindow.show();
    return;
  }
  mainWindow = createWindow("main");
  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}
function showSearchWindow() {
  if (searchWindow) {
    searchWindow.show();
    return;
  }
  searchWindow = createWindow("search");
  searchWindow.on("blur", () => {
    searchWindow == null ? void 0 : searchWindow.close();
    searchWindow = null;
  });
  searchWindow.on("closed", () => {
    searchWindow = null;
  });
}
function createTray() {
  const icon = electron.nativeImage.createEmpty();
  tray = new electron.Tray(icon);
  tray.setToolTip("OmniAide");
  const contextMenu = electron.Menu.buildFromTemplate([
    { label: "打开 OmniAide", click: showMainWindow },
    { type: "separator" },
    { label: "退出", click: () => {
      electron.app.quit();
    } }
  ]);
  tray.setContextMenu(contextMenu);
  tray.on("click", showMainWindow);
}
electron.app.whenReady().then(async () => {
  registerIpcHandlers();
  await initPlugins();
  createTray();
  showMainWindow();
  electron.globalShortcut.register("Alt+Space", showSearchWindow);
});
electron.app.on("window-all-closed", () => {
});
electron.app.on("before-quit", () => {
});
electron.ipcMain.handle("window:open-page", (_, pluginId) => {
  const win = new electron.BrowserWindow({
    width: 900,
    height: 700,
    webPreferences: {
      preload: require$$1.join(__dirname, "../preload/index.js"),
      contextIsolation: true
    }
  });
  const url = process.env.VITE_DEV_SERVER_URL ? `${process.env.VITE_DEV_SERVER_URL}?view=plugin-page&pluginId=${pluginId}` : `file://${require$$1.join(__dirname, "../../dist/index.html")}?view=plugin-page&pluginId=${pluginId}`;
  win.loadURL(url);
});
electron.ipcMain.handle("shell:open", (_, url) => electron.shell.openExternal(url));
