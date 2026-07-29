const { app, BrowserWindow, screen, Menu, ipcMain, globalShortcut } = require('electron');
const path = require('path');

const WINDOW_SIZE = { width: 220, height: 240 };
const SKINS = ['orange', 'gray', 'pink'];

let win = null;
let dragging = false;
let wandering = true;
let currentSkin = SKINS[0];
let walkTimeout = null;
let walkInterval = null;
let dragInterval = null;
let dragOffset = { x: 0, y: 0 };

function createWindow() {
  const { workAreaSize } = screen.getPrimaryDisplay();

  win = new BrowserWindow({
    width: WINDOW_SIZE.width,
    height: WINDOW_SIZE.height,
    x: Math.round(workAreaSize.width / 2 - WINDOW_SIZE.width / 2),
    y: workAreaSize.height - WINDOW_SIZE.height - 10,
    transparent: true,
    frame: false,
    alwaysOnTop: true,
    resizable: false,
    skipTaskbar: true,
    hasShadow: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  win.setAlwaysOnTop(true, 'screen-saver');
  win.loadFile(path.join(__dirname, 'renderer', 'index.html'));

  win.once('ready-to-show', () => {
    win.webContents.send('pet-state', { action: 'set-skin', skin: currentSkin });
  });

  win.on('closed', () => {
    win = null;
    clearTimeout(walkTimeout);
    clearInterval(walkInterval);
    clearInterval(dragInterval);
  });

  scheduleNextWalk();
}

function scheduleNextWalk() {
  clearTimeout(walkTimeout);
  const idleDelay = 4000 + Math.random() * 6000;
  walkTimeout = setTimeout(() => {
    if (!win || dragging || !wandering) {
      scheduleNextWalk();
      return;
    }
    startWalk();
  }, idleDelay);
}

function startWalk() {
  const { workAreaSize } = screen.getPrimaryDisplay();
  const [curX, y] = win.getPosition();
  const maxX = workAreaSize.width - WINDOW_SIZE.width;
  const delta = Math.round(Math.random() * 400 - 200);
  const targetX = Math.max(0, Math.min(maxX, curX + delta));
  const facingLeft = targetX < curX;

  if (Math.abs(targetX - curX) < 20) {
    scheduleNextWalk();
    return;
  }

  win.webContents.send('pet-state', { action: 'walk', facingLeft });

  const steps = 40;
  const stepX = (targetX - curX) / steps;
  let i = 0;

  clearInterval(walkInterval);
  walkInterval = setInterval(() => {
    if (!win || dragging) {
      clearInterval(walkInterval);
      scheduleNextWalk();
      return;
    }
    i += 1;
    const [x] = win.getPosition();
    win.setPosition(Math.round(x + stepX), y);
    if (i >= steps) {
      clearInterval(walkInterval);
      win.webContents.send('pet-state', { action: 'idle' });
      scheduleNextWalk();
    }
  }, 50);
}

function showContextMenu() {
  const template = [
    {
      label: '换装',
      submenu: SKINS.map((skin) => ({
        label: skinLabel(skin),
        type: 'radio',
        checked: currentSkin === skin,
        click: () => {
          currentSkin = skin;
          win.webContents.send('pet-state', { action: 'set-skin', skin });
        },
      })),
    },
    { type: 'separator' },
    {
      label: '到处走走',
      type: 'checkbox',
      checked: wandering,
      click: (item) => {
        wandering = item.checked;
        if (wandering) scheduleNextWalk();
      },
    },
    { type: 'separator' },
    {
      label: '退出',
      click: () => app.quit(),
    },
  ];

  Menu.buildFromTemplate(template).popup({ window: win });
}

function skinLabel(skin) {
  const labels = { orange: '橘色（默认）', gray: '灰色', pink: '粉色' };
  return labels[skin] || skin;
}

ipcMain.on('drag-start', () => {
  if (!win || dragging) return;
  dragging = true;
  clearInterval(walkInterval);

  const cursor = screen.getCursorScreenPoint();
  const [winX, winY] = win.getPosition();
  dragOffset = { x: cursor.x - winX, y: cursor.y - winY };

  clearInterval(dragInterval);
  dragInterval = setInterval(() => {
    if (!win) return;
    const point = screen.getCursorScreenPoint();
    win.setPosition(point.x - dragOffset.x, point.y - dragOffset.y);
  }, 16);
});

ipcMain.on('drag-end', () => {
  dragging = false;
  clearInterval(dragInterval);
  scheduleNextWalk();
});

ipcMain.on('show-context-menu', showContextMenu);

app.whenReady().then(() => {
  createWindow();

  globalShortcut.register('CommandOrControl+Shift+Q', () => app.quit());

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('will-quit', () => {
  globalShortcut.unregisterAll();
});

app.on('window-all-closed', () => {
  app.quit();
});
