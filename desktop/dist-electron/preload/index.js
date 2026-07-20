"use strict";
const electron = require("electron");
electron.contextBridge.exposeInMainWorld("mqbox", {
  plugin: {
    list: () => electron.ipcRenderer.invoke("plugin:list"),
    getPanels: () => electron.ipcRenderer.invoke("plugin:get-panels"),
    getPage: (pluginId) => electron.ipcRenderer.invoke("plugin:get-page", pluginId),
    execute: (pluginId, command, args) => electron.ipcRenderer.invoke("plugin:execute", pluginId, command, args)
  },
  search: {
    plugin: (keyword, query) => electron.ipcRenderer.invoke("search:plugin", keyword, query),
    getProviders: () => electron.ipcRenderer.invoke("search:get-providers")
  },
  config: {
    get: (key) => electron.ipcRenderer.invoke("config:get", key),
    set: (key, value) => electron.ipcRenderer.invoke("config:set", key, value)
  },
  window: {
    openPage: (pluginId) => electron.ipcRenderer.invoke("window:open-page", pluginId),
    openSearch: () => electron.ipcRenderer.invoke("window:open-search"),
    hide: () => electron.ipcRenderer.invoke("window:hide")
  },
  api: {
    get: (path) => electron.ipcRenderer.invoke("api:get", path),
    post: (path, body) => electron.ipcRenderer.invoke("api:post", path, body),
    put: (path, body) => electron.ipcRenderer.invoke("api:put", path, body),
    delete: (path) => electron.ipcRenderer.invoke("api:delete", path)
  }
});
