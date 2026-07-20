const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
    // Called by renderer to register a WS message handler by type
    onWsMessage: (type, callback) => {
        ipcRenderer.on(`ws:${type}`, (_event, payload) => callback(payload));
    },
    // Main process → renderer: a new assist request just started (hotkey pressed)
    onAssistStart: (callback) => {
        ipcRenderer.on('assist-start', (_event) => callback());
    },
    // Renderer → backend (e.g., close window)
    closeWindow: () => ipcRenderer.send('close-window')
});