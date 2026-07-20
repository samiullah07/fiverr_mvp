const { app, BrowserWindow, ipcMain, screen, globalShortcut } = require('electron');
const path = require('path');
const fs = require('fs');
const WebSocket = require('ws');

// ---------------------------------------------------------------------------
// Window position persistence
// ---------------------------------------------------------------------------
let POSITION_FILE; // Will be set after app.whenReady()

function getStoredPosition() {
    try {
        if (fs.existsSync(POSITION_FILE)) {
            const data = JSON.parse(fs.readFileSync(POSITION_FILE, 'utf8'));
            return { x: data.x, y: data.y };
        }
    } catch (e) {
        console.log('Could not read stored position, using default');
    }
    // Default: top-right with 30px offset
    const primaryDisplay = screen.getPrimaryDisplay();
    return {
        x: primaryDisplay.workArea.width - 400 - 30,
        y: 30
    };
}

function savePosition(x, y) {
    try {
        const dir = path.dirname(POSITION_FILE);
        if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
        fs.writeFileSync(POSITION_FILE, JSON.stringify({ x, y }));
    } catch (e) {
        console.log('Could not save window position');
    }
}

// ---------------------------------------------------------------------------
// WebSocket client with exponential backoff reconnect
// ---------------------------------------------------------------------------
let ws = null;
let reconnectAttempts = 0;
let reconnectTimer = null;
const MAX_RECONNECT_DELAY = 30000; // Cap at 30s
const BACKEND_PORT = process.env.PORT || 8765;

function connectWebSocket() {
    ws = new WebSocket(`ws://127.0.0.1:${BACKEND_PORT}/ws/overlay`);

    ws.on('open', () => {
        console.log('[overlay] WebSocket connected');
        reconnectAttempts = 0;
    });

    ws.on('message', (data) => {
        try {
            const payload = JSON.parse(data.toString());
            if (mainWindow && !mainWindow.isDestroyed()) {
                mainWindow.webContents.send(`ws:${payload.type}`, payload);
            }
        } catch (e) {
            console.error('[overlay] Failed to parse WS message:', e);
        }
    });

    ws.on('close', () => {
        console.log('[overlay] WebSocket closed');
        scheduleReconnect();
    });

    ws.on('error', (err) => {
        console.error('[overlay] WebSocket error:', err.message);
        // 'close' will follow 'error' and handle reconnect
    });
}

function scheduleReconnect() {
    if (reconnectAttempts >= 10) {
        console.error('[overlay] Max reconnect attempts reached');
        return;
    }
    // Exponential backoff: 1s, 2s, 4s, 8s ... capped at 30s
    const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), MAX_RECONNECT_DELAY);
    reconnectAttempts++;
    console.log(`[overlay] Reconnecting in ${delay}ms (attempt ${reconnectAttempts})`);
    reconnectTimer = setTimeout(connectWebSocket, delay);
}

function sendToBackend(payload) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(payload));
    }
}

// ---------------------------------------------------------------------------
// Window creation
// ---------------------------------------------------------------------------
function createWindow() {
    const { x, y } = getStoredPosition();

    const mainWindow = new BrowserWindow({
        x: x,
        y: y,
        frame: false,
        transparent: true,
        skipTaskbar: true,
        focusable: true,
        show: false,
        resizable: true,
        width: 600,
        height: 400,
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            nodeIntegration: false,
            contextIsolation: true
        }
    });

    mainWindow.loadFile('src/index.html');
    mainWindow.showInactive();
    mainWindow.setAlwaysOnTop(true, 'screen-saver');

    // Persist position on move
    let saveTimer = null;
    mainWindow.on('moved', () => {
        if (saveTimer) clearTimeout(saveTimer);
        saveTimer = setTimeout(() => {
            const [nx, ny] = mainWindow.getPosition();
            savePosition(nx, ny);
        }, 1000);
    });

    return mainWindow;
}

let mainWindow = null;

// IPC from renderer → backend
ipcMain.on('close-window', () => {
    if (mainWindow) mainWindow.close();
});

ipcMain.on('user-input', (event, payload) => {
    sendToBackend({ type: 'user-input', ...payload });
});

// ---------------------------------------------------------------------------
// App lifecycle
// ---------------------------------------------------------------------------
app.whenReady().then(() => {
    POSITION_FILE = path.join(app.getPath('userData'), 'window-position.json');

    mainWindow = createWindow();
    connectWebSocket();

    // Register global "Assist Me" hotkey (system-wide, fires even when
    // Teams/Zoom have focus). Default: Ctrl/Cmd+Shift+Space.
    const assistHotkey = 'CommandOrControl+Shift+Space';
    try {
        const registered = globalShortcut.register(assistHotkey, () => {
            console.log('[overlay] Assist Me hotkey pressed');
            // Tell the renderer to show "Thinking..." immediately, in parallel
            // with sending the assist request to the backend.
            if (mainWindow && !mainWindow.isDestroyed()) {
                mainWindow.webContents.send('assist-start');
            }
            sendToBackend({ type: 'assist-request' });
        });
        if (!registered) {
            console.error(`[overlay] Failed to register hotkey: ${assistHotkey}`);
        }
    } catch (e) {
        console.error('[overlay] Hotkey registration error:', e);
    }

    app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) {
            mainWindow = createWindow();
            connectWebSocket();
        }
    });
});

app.on('will-quit', () => {
    globalShortcut.unregisterAll();
    if (reconnectTimer) clearTimeout(reconnectTimer);
    if (ws) {
        try { ws.close(); } catch (e) {}
    }
});

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit();
});
