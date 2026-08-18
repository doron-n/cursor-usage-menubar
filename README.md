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

After `./install.sh install`, the LaunchAgent's `KeepAlive` means clicking Quit will relaunch the app; run `./install.sh uninstall` if you actually want it to stop.

Menu title looks like `Cursor · $237.34 · 48%`. Click it for account/plan/view/spend/allowance/remaining/cycle/top model, then:

- View (Myself only / billing groups / Enter Group ID…)
- View Users by Usage… (native window, when a group is selected)
- View Model Breakdown… (native window, Auto accordion; group-wide models)
- Refresh Now
- Open Cursor Dashboard
- Quit

**Myself only** uses your billing-group member spend and per-user cap. A billing group (for example `9484` / xDome-R&D) uses Cursor's group spend for this cycle.

## Verify

```bash
.venv/bin/python -m cursor_usage_menubar.verify
```

Prints a redacted snapshot (email domain, plan, spend, model names). No tokens.

## Share with others (`.pkg`)

Build a standalone Apple Silicon installer (no Python install required on their Mac):

```bash
./build-pkg.sh
```

The package is written to:

`dist/CursorUsage-1.0.0-arm64.pkg`

Recipients:

1. Must be on Apple Silicon and already signed in to the Cursor desktop app.
2. Double-click the pkg (or right-click → Open if macOS blocks it). It installs **Cursor Usage.app** into `/Applications`.
3. The pkg is ad-hoc signed, not Apple-notarized. If Gatekeeper blocks it: `xattr -dr com.apple.quarantine CursorUsage-1.0.0-arm64.pkg`.

Rebuild after code changes with `./build-pkg.sh`.

## License

Private local utility. Do not commit secrets.
