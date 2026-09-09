# Setup and recovery

These steps apply to Practice Room 0.3.1. For normal practice, use the [daily workflow](../WORKFLOW_GUIDE.md). For source layout and test setup, use the [architecture guide](ARCHITECTURE.md).

## Updating without losing work

Save or pause the session before updating. Check whether the app reports **Saved locally**, a browser-only draft, or pending synchronization. Export an unsaved draft before closing its browser. Keep the existing checkout and ignored recovery files, including `.study-local/`, when updating to the reviewed release.

Close the old app terminal, update the checkout while preserving local changes, then reopen **Start Study.cmd**. The launcher refreshes changed dependencies and rebuilds the interface when needed. A preview ZIP is a separate local copy; it does not carry over unpublished work from an existing installation and does not provide Git synchronization by itself.

## The app does not open, or still shows the older interface

The Windows launcher needs Python 3.11 or newer. A source interface build needs Node.js 22.12 or newer; Git is needed for repository synchronization. Initial dependency setup requires internet access. Read the terminal's setup message if the launcher stops.

If the browser shows the interface-setup page, reopen **Start Study.cmd** and let the build finish. For manual setup, follow the [README](../README.md#manual-setup). If an older server is running, close its terminal and relaunch; refreshing the browser alone cannot upgrade that Python process.

The app normally uses `http://127.0.0.1:8765`. If another checkout owns that port, close its app terminal or launch this checkout on another port:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\study.ps1 app --port 8766
```

Use the address printed by that instance. Browser drafts are tied to the browser origin, so changing the port does not transfer unsaved browser-only text. With an installed Python environment, `python -m study doctor` provides a general setup check; the web connection status provides Codex-specific diagnostics.

## Codex cannot connect

Practice Room checks for the validated CLI version **0.153.4**, including the Codex desktop installation and usual npm directory on Windows. A missing PATH entry alone does not require reinstalling the desktop app.

1. Open Settings or the coach panel and choose **Connect Codex**. Read the connection result.
2. If no supported installation is available, expand **Help connecting Codex**. With Node.js installed, run `npm install -g @openai/codex@0.153.4` in a terminal, then reconnect.
3. Follow **Sign in with ChatGPT**, finish the sign-in, and choose **Refresh connection**. Practice Room has its own managed login; desktop sign-in does not automatically connect this app.
4. If the CLI is in a custom location, set `PRACTICE_ROOM_CODEX` to its existing absolute executable path in the same terminal used to launch the app. This override selects that path explicitly; remove a stale override before relying on automatic discovery.

An unsupported version stays disabled until the adapter is validated for it. Connection failure leaves local practice, saving, testing, and completion available. Official setup instructions are in the [Codex installation guide](https://learn.chatgpt.com/docs/codex/cli).

If a question's acknowledgement is uncertain, reconnect and review its recorded status before sending a different question. Do not assume a network timeout means it was never accepted. Unknown or exhausted allowance also requires a successful refresh before another turn. **Stop coach** interrupts coaching; **Stop tests** and **Stop repair test** stop their respective code checks.

## The timer looks wrong

Normal foreground polling should count continuously, including during a repair. Use **Pause** to stop active time; switching tabs or talking with Codex is not an automatic pause. Resume continues from saved time.

A suspended computer or delayed browser may require the display to reconcile with saved state. If the app reports an uncertain gap, review **Total active minutes** in the completion preview. This preserves an honest record without treating an unobserved gap as confirmed study. After upgrading from the version with polling jumps, restart the old app server first.

## A draft is unsaved or two versions conflict

**Saved locally** means the app has saved the code on this computer. **Saved in browser** means the save could not be confirmed and the local browser draft is being retained when storage is available. Keep that browser open, restore the connection, and use the export control if needed. If browser storage itself is unavailable, the app shows a separate warning; export before closing.

For **Two versions need your review**, expand **Other saved version**, compare it with the editor, then choose **Use other saved version** or **Keep my browser draft**. **Export my draft** preserves a copy before the choice. Ordinary polling of your own save should no longer create this conflict; actual competing edits still require review.

After a delayed or timed-out action, use **Refresh workspace** at the bottom of the sidebar (or **Retry connection**, when shown) and inspect what happened before repeating it. The app preserves pending coaching request identities instead of blindly sending a second request. A changed exercise cannot receive a save intended for the prior exercise.

## Git synchronization is pending

**Saved locally; sync pending** means work remains on this computer. Check Git installation, network access, and your repository authentication, then use **Retry sync**. GitHub authentication and ChatGPT coaching sign-in are separate.

Pause and successfully synchronize before moving to another computer. For divergent attempts, preserve both versions and follow the [two-computer recovery guide](../WORKFLOW_GUIDE.md#recovery-and-two-computers). Do not delete recovery receipts while a publication is pending. Historical learning files retain their exact bytes through checkout; line-ending normalization is not a reason to rewrite them.
