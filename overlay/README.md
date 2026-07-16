# Meeting Copilot Overlay

## Setup

1. Install dependencies:
   ```bash
   npm install
   ```

2. Run in development mode:
   ```bash
   npm start
   ```

## Manual Test Checklist (Critical - Verify Against REAL Teams Window)

Before building further features, verify this scaffold works correctly with Microsoft Teams (or Zoom/Google Meet):

### Test Procedure:
1. **Start overlay**: `npm start`
2. **Open Microsoft Teams** and join/start a test meeting
3. Ensure Teams window is **focused and active**

### Verify each:
- [ ] **Focus behavior**: Teams remains active when overlay appears. Typing in Teams chat still goes to Teams (not the overlay). Cursor stays in Teams.
- [ ] **Always-on-top**: Overlay remains visible when you share your screen or go fullscreen in Teams
- [ ] **Dragging**: Click the title bar (anywhere except the close button) and drag the overlay to a new position
- [ ] **Position persistence**: Close the overlay, restart it - it should appear at the last dragged position
- [ ] **Interactive**: The close button (×) in the top-right works to close the application

### Expected Visual:
- Transparent dark background
- "Meeting Copilot" title bar with close button
- Red pulsing dot with "Transcription active" text
- Placeholder text: "Waiting for question..."

## Notes:
- The window is **focusable** (you can click it) but uses `showInactive()` to avoid stealing focus when shown
- Position is stored in `%APPDATA%\Meeting Copilot\window-position.json`
- For real testing: You must have a Teams meeting with video/screenshare to verify it stays visible over shared content
- This scaffold does NOT yet connect to the backend - that comes in later phases