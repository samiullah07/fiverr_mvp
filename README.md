# Meeting Copilot

A local Windows desktop assistant that listens to your meetings, transcribes
them in real time, and — when you press a hotkey — suggests answers drawn
from your own documents, with source citations.

Everything runs locally on your machine. The only external call is to your
chosen AI provider (Claude), using your own API key.

## What you need first

1. **Windows 10 or 11**
2. **Python 3.11+** — https://www.python.org/downloads/ (check "Add Python to PATH" during install)
3. **Node.js 18+** — https://nodejs.org/
4. **An Anthropic API key** — see "Getting your API key" below

## Getting your Anthropic API key

Your Claude.ai subscription is separate from API access — you need an API key.

1. Go to https://console.anthropic.com
2. Create an account (or sign in)
3. Add a small amount of billing credit under **Billing** (API usage is
   pay-per-use; typical cost for this app is low)
4. Under **API Keys**, create a key. It starts with `sk-ant-`
5. Copy it — you'll paste it in step 3 below

## Setup (one time)

### 1. Get the code
### 2. Install Python dependencies
### 3. Add your API key
Copy `.env.example` to `.env`:
Open `.env` in Notepad and set:
LLM_PROVIDER=claude
ANTHROPIC_API_KEY=sk-ant-your-key-here
ANTHROPIC_MODEL=claude-haiku-4-5-20251001
### 4. Install the overlay
cd overlay
npm install
cd ..
## Add your documents

Put the PDF and text files you want the assistant to reference into a folder,
e.g. `my_documents/`. The app indexes them the first time you run it, and
only re-indexes files that change after that.

## Running it (every time)

Open **two** PowerShell windows in the project folder.

**Window 1 — start the backend:**
..venv\Scripts\Activate.ps1
python -m backend.main my_documents
Wait until you see: `Uvicorn running on http://127.0.0.1:8765`

**Window 2 — start the overlay:**
cd overlay
npm start
A small "Meeting Copilot" window appears, always on top.

## Using it

1. Join your meeting (Teams, Zoom, or Google Meet) as normal.
2. The app listens and transcribes continuously — you'll see live text in
   the overlay, and the green "Transcription active" indicator.
3. When someone asks you something and you want help, press
   **Ctrl + Shift + Space**.
4. The assistant reads the recent conversation, searches your documents,
   and shows a suggested answer in the overlay — with the source document
   it came from.

If an answer isn't in your documents, the overlay clearly says so.

## Troubleshooting

- **"model not found" / 404 error** → your API key or model name is wrong.
  Confirm your key starts with `sk-ant-` and has billing credit at
  console.anthropic.com.
- **Overlay says "connecting" / won't connect** → make sure the backend
  (Window 1) is running and shows `Uvicorn running on ...`.
- **Hotkey does nothing** → another app may be using Ctrl+Shift+Space. Tell
  me and I'll change it to a different key.
- **Transcription is imperfect** → this is expected with local
  transcription; the assistant still works well because it reads the whole
  recent conversation for context.

## Notes

- Everything runs on your machine. Your documents and conversations are not
  sent anywhere except your chosen AI provider for generating answers.
- This app captures system audio, which includes other participants' voices.
  Please make sure you comply with your local recording/consent laws and
  your meeting platform's terms.
  pip freeze > requirements.txt