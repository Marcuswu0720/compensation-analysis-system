const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('pet', {
  onState: (callback) => {
    ipcRenderer.on('pet-state', (_event, payload) => callback(payload));
  },
  dragStart: () => ipcRenderer.send('drag-start'),
  dragEnd: () => ipcRenderer.send('drag-end'),
  moveWindow: (dx, dy) => ipcRenderer.send('move-window', { dx, dy }),
  showContextMenu: () => ipcRenderer.send('show-context-menu'),
});
