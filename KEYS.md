# Your keys — where they go

## The rule: **never paste a key into the chat.**

Anything you type into the chat is saved in the conversation forever. Put your keys in the **`.env`** file instead. Claude never reads that file — a setup script hands your keys straight to the tool, so they stay yours.

---

## What to do (2 minutes)

1. **Open the file named `.env`** in this folder. Any text editor works — Notepad, TextEdit, VS Code.
   *(Don't see it? It might be hidden. On Mac press `Cmd+Shift+.` in Finder. If there's only a `.env.template`, make a copy of it and name the copy `.env`.)*

2. **Paste each key after the `=` sign.** No quotes, no spaces:

   ```
   PRICELABS_API_KEY=abc123xyz
   ```
   not
   ```
   PRICELABS_API_KEY = "abc123xyz"
   ```

3. **Save the file.**

4. **Run the setup script.** Mac: `bash setup-keys.sh`. Windows: `powershell -File setup-keys.ps1`. It reads your `.env`, reports which keys it found without ever printing them, and copies each key into the connector that needs it. Don't paste anything into the chat.

   *(It merges. Any per-connector setting you already changed by hand, `TURNO_ENV` included, is left alone.)*

5. **Fully quit and reopen Claude Code.** It loads the connectors on startup.

---

## The keys you need

Only PriceLabs and Hospitable are required. Turno, AirROI and RankBreeze are enrichment: leave them blank and the pricing analysis still runs, just without the ops, named-competitor comp, and ranking layers. Turno in particular is partner-gated, so most people will not have it on day one.

| Key | What it's for | Required? | Where to get it |
|---|---|---|---|
| `PRICELABS_API_KEY` | PriceLabs | Yes | PriceLabs Dashboard -> Settings -> API Details -> Enable |
| `HOSPITABLE_API_KEY` | Hospitable | Yes | https://my.hospitable.com/apps/api-access |
| `HOSPITABLE_WEBHOOK_SECRET` | Hospitable webhook secret | Optional | https://my.hospitable.com/apps/api-access |
| `TURNO_API_TOKEN` | Turno — the long JWT (starts with eyJ) | Optional | Turno partner dashboard |
| `TURNO_PARTNER_ID` | Turno — the partner UUID | Optional | Turno partner dashboard |
| `TURNO_ENV` | `sandbox` or `production`. Blank keeps the connector's own setting, which is sandbox | Optional | you choose |
| `AIRROI_API_KEY` | AirROI (free key) | Optional | https://www.airroi.com/api/developer/activate |
| `RANKBREEZE_SESSION` | RankBreeze session cookie (_godzilla_session) | Optional | app.rankbreeze.com -> DevTools -> Cookies |

---

## Keeping your keys safe

- ✅ Keys live in `.env` on **your** computer. They never get uploaded.
- ❌ **Never** paste a key into a chat, a screenshot, a Skool post, or GitHub.
- ❌ **Never** commit `.env` (it's already in `.gitignore`).
- 🔄 **If you ever leak a key, rotate it.** Go to that service's dashboard and regenerate it. Takes 10 seconds and makes the old one useless.

**Already pasted a key into a chat by accident?** Rotate it now. Don't panic — just regenerate it and paste the new one into `.env` instead.
