# Cursor Usage (macOS menu bar)

Shows your signed-in Cursor plan spend in the Mac menu bar.

**This uses unofficial Cursor APIs. They can change or break without notice.**

## Requirements

- macOS
- Python 3
- Cursor desktop app signed in on this Mac

## Auth (no tokens stored)

The app reads Cursor's local SQLite state DB **read-only**:

`~/Library/Application Support/Cursor/User/globalStorage/state.vscdb`

It never writes that DB, never saves access/refresh tokens to disk or Keychain, never logs cookies, and never calls Cursor's OAuth refresh endpoint (refreshing here could break your Cursor login). If the session is expired, open Cursor so it can refresh itself.

## Install (local only)

```bash
chmod +x install.sh
./install.sh run       # start once
./install.sh install   # LaunchAgent (RunAtLoad + KeepAlive)
./install.sh status
./install.sh uninstall
```

Menu title looks like `Cursor · $237.34 · 48%`. Click it for account/plan/spend/allowance/remaining/cycle/top model, then:

- View Model Breakdown… (native window, Auto accordion)
- Refresh Now
- Open Cursor Dashboard
- Quit

## Verify

```bash
.venv/bin/python -m cursor_usage_menubar.verify
```

Prints a redacted snapshot (email domain, plan, spend, model names). No tokens.

## License

Private local utility. Do not commit secrets.
