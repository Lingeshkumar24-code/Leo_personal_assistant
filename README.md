# LEO AI — desktop AI assistant

Talk or type; LEO plans, acts on your PC, checks the result, and reports what really happened.

## Quick start (Windows)
1. Install Python 3.10+ (tick "Add to PATH").
2. Run `scripts\setup_windows.bat` (creates a venv, installs everything, installs Chromium for the browser agent).
3. Open `.env` and add `GEMINI_API_KEY` (or `GROQ_API_KEY`). Set `SCREEN_CAPTURE_ENABLED=true` if you want LEO to see your screen.
4. Double-click **`LEO.bat`** → the 3D interface opens.

Other ways to run: `python main.py` (typed shell) · `python main.py --voice` (microphone in terminal) · `python main.py --ui` (3D interface).

## What it can do
| Area | Tools |
|---|---|
| Computer | open/close apps, click, type, hotkeys, screenshot, volume, mute, brightness, lock |
| Screen | `screen.look` (asks the vision model about your screen), `screen.read_text` (local OCR), optional **screen watch** (local OCR every few seconds; nothing uploaded) |
| Browser | open, search, read page, click, type (Playwright) |
| Coding | detect & run a project, run tests, read terminal output; Python/JS/Rust/Go project types |
| Documents | Word (open/edit/create), Excel totals, PowerPoint from outline, PDF text |
| Files | find, read, create folder, move, rename, **delete (to recoverable trash, always asks)** |
| Jobs | search postings, analyse vs your profile, fill applications (**never submits without your approval, never bypasses CAPTCHA, never guesses answers**), record history |
| Memory | remembers preferences/projects; view and delete them in Settings |

## Safety model
* Permission levels OBSERVE / NORMAL / PRIVILEGED / HIGH_RISK, with modes **manual** (asks before actions), **assisted**, **autonomous**. HIGH_RISK (delete, submit application) *always* asks, in every mode.
* Emergency stop: **CTRL+SHIFT+L**, the STOP button, or say "LEO stop".
* Only read-only tools are auto-retried, so a click/type is never repeated by accident.
* The UI server listens on 127.0.0.1 only and requires a per-session token, so websites can't control your PC.
* Secrets are redacted from logs (`logs/leo.log`); an audit trail of permission decisions is in `logs/audit.log`.
* Screenshots are only sent to your AI provider when you ask a screen question.

## Honest status — what was tested, and where
* **Tested automatically (32 tests):** provider abstraction plumbing, planner→tool pipeline, permissions, files/delete safety, documents (real .docx/.xlsx/.pptx), coding agent, job form filling and CAPTCHA refusal (real headless Chromium), screen-watch logic, wake-word parsing, the UI server (token/Host/Origin checks, approval flow), and the 3D UI rendering in Chromium.
* **Needs your Windows PC to verify** (no display/mic/Windows in the build environment): mouse & keyboard control, opening apps, volume/brightness/lock, microphone + speech, global hotkey, real Gemini/Groq calls with your key, screen capture + Tesseract OCR. The code follows each library's documented API and fails with a clear message rather than pretending. If something misbehaves, the error text in the Activity panel says why.
* **Not built:** always-on-top window (browsers can't do this; the "Compact" button shrinks to an orb instead), true measured microphone amplitude for the waveform (it is a stylised indicator), an installer `.exe`.
* Voice recognition uses Google's free web recognizer via SpeechRecognition, so it needs internet.

## Layout
`app/core` pipeline & config · `app/agents` planner/task manager · `app/tools` registry · `app/{computer,browser,coding,documents,filesystem,jobs,vision,voice,memory,security,providers,ui}` capabilities · `assets/ui` 3D interface (Three.js vendored, works offline) · `tests/`.

Add a tool: subclass `Tool` (see `app/tools/base.py`), give it a name, schema and permission level, register it in `app/tools/registry.py`. The planner picks it up automatically.
