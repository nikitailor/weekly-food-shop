# Weekly Food Shop 🛒

Niki's weekly meal planning and Ocado shop. The plan and rules live in `CLAUDE.md`
and the **meal-planning** Claude skill; the shopping list lives in Apple Reminders
("Food Shopping").

The Ocado trolley is filled by Claude through the **uk-grocery MCP**
([abracadabra50/uk-grocery-cli](https://github.com/abracadabra50/uk-grocery-cli)),
run on the MacBook. Claude fills the trolley after you approve a match table, then
stops. You review it, book a slot and check out in the Ocado app yourself.

> This replaced the old `ocado_shopper.py` script and its GitHub Action, which were
> removed in November 2026.

---

## One-time setup (on the MacBook)

### 1. Install the CLI at the reviewed version

```bash
git clone https://github.com/abracadabra50/uk-grocery-cli.git && cd uk-grocery-cli && git checkout 6140a9e
```

```bash
npm ci && npx playwright install chromium && npm run build
```

`6140a9e` (4 Nov 2026) is the commit that was security-reviewed. Use `npm ci`
(not `npm install`) so the lockfile versions are used. Review the changes before
pulling a newer version.

### 2. Store the Ocado password in macOS Keychain

Copy it from the Passwords app, then paste it at the hidden prompt:

```bash
security add-generic-password -a n.tailor22@gmail.com -s ocado-groc -w
```

If you change your Ocado password, update it with the same command plus `-U`.

### 3. Connect the MCP

Claude desktop app: go to **Settings → Developer → Edit Config** and add this under
`"mcpServers"` (use `echo "$PWD/dist/mcp-server.js"` to get the path):

```json
"uk-grocery": {
  "command": "node",
  "args": ["/Users/<you>/.../uk-grocery-cli/dist/mcp-server.js"]
}
```

Then set these tools to **Never allow**: `grocery_checkout`,
`grocery_book_slot`, `grocery_basket_clear`, `grocery_login`.

Claude Code CLI alternative:

```bash
claude mcp add uk-grocery -s user -- node "$PWD/dist/mcp-server.js"
```

Then add `deny` rules for `mcp__uk-grocery__grocery_checkout`,
`mcp__uk-grocery__grocery_book_slot`, `mcp__uk-grocery__grocery_basket_clear` and
`mcp__uk-grocery__grocery_login` to `~/.claude/settings.json`.

---

## Logging in (first time, and whenever the session expires)

From the `uk-grocery-cli` folder:

```bash
SUPERMARKET_PASSWORD="$(security find-generic-password -s ocado-groc -a n.tailor22@gmail.com -w)" node dist/cli.js --provider ocado login -e n.tailor22@gmail.com
```

- Click **Allow** (not *Always Allow*) on the Keychain prompt.
- A browser window opens Ocado's real login page. Type the emailed code into
  Terminal if asked.
- Only Ocado's cookies are saved, to `~/.ocado/session.json` (owner-only). The password is not saved there.

Check it worked without changing anything:

```bash
node dist/cli.js --provider ocado basket
```

---

## Weekly use

In the Thursday food planning session (local desktop app or CLI, not a cloud session),
after the shopping list is added to Reminders, Claude:

1. Reads the Food Shopping list and skips headers, items you already have, and
   anything already in the trolley.
2. Searches your Ocado favourites first, then all products, matching meat and fish
   weights.
3. Shows a match table (★ favourite / ⚠️ check) and **waits for your approval**.
4. Adds the approved items and reports the trolley total.

You then review, book a slot and check out in the Ocado app.

**Limits:** Ocado slot booking and checkout aren't supported by the tool, and the
tool uses Ocado's unofficial site APIs, so it can break if Ocado changes their site.
Keep use to one trolley fill a week.
