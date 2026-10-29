---
name: kick-the-tires
description: Health check of AI the agent setup. Audits installed skills, tests MCP servers, browser use and computer use, fetches a current Danish news, identifies the client, agent and model, and reports available updates in a short markdown status report. Use when the user says "kick the tires", "/kick-the-tires", or asks to check, test or audit their skills, MCP servers, tools or client setup.
---

# Kick the tires

Run every check, then give one short markdown report. **This skill only reports.** Never install, update, sign in, or change settings, even when a fix is obvious; the report says how to fix things.

Each check is independent. If one fails, record what you observed and move on. Never stop the run early.

Status symbols used everywhere: `✔` worked · `⚠` works but needs attention · `✖` broken · `–` not available in this client.
`–` means the client doesn't offer that capability. It is not a failure, so don't mark it `✖`.

Tell the user in one line that the check is starting, then work through the steps in order.

**Timing.** Every row in the report shows how long it took, as minutes:seconds (`0:07`, `2:05`).
- The script times its own parts (Skills, Updates, News) and returns them in `timings`.
- Time the agent steps yourself with a clock mark: run `date +%s` and note the number. Take a mark **before step 1**, **before steps 3, 4 and 5**, and **before step 7**. A step's time is the next mark minus its own. The total is the step 7 mark minus the step 1 mark.
- If News needs the web-search fallback, mark before and after that search and use that time instead.
- Never estimate a time. If a mark is missing, write `–`.

## 1. Facts and skill audit (script)

Run the probe with this skill folder's absolute path:

```sh
python3 -I <this-skill-dir>/scripts/probe.py --cwd "$PWD"
```

It prints JSON with:
- `environment`: client, agent and versions
- `skills`: a static audit of every installed skill, with `items[].problems`
- `skillUpdates` and `clientUpdates`: each with `status` (current / outdated / unknown) and `fix`
- `news`: one fresh DR or TV 2 headline
- `timings`: `skills`, `updates`, `news` and `total`, as minutes:seconds
- `errors`: sections that crashed

It needs no input and takes about 10 seconds. If the script itself fails, mark Skills and Updates `✖` with the error and keep going. You can still do News yourself (see step 6).

## 2. Identify yourself

Add what the script can't see: your **model** (name and ID) and **provider**, taken from your own system context. If you don't know something, write "unknown"; never guess. The result is one line: `Orca 1.4.237 (local build) · Claude Code 2.1.312 · Opus 5.5 (Anthropic)`.

## 3. MCP servers

List every MCP server in this session, using your tool list (`mcp__<server>__*`) and the session's notices (connected, needs authentication, still connecting, disconnected). If a server is still connecting, do one tool search for it to let it finish, then take its state as it stands.

Give each connected server **one** test call, only from this list of read-only calls:

| Server | Test call |
|---|---|
| open-cu | `list_apps` |
| ios-simulator | `get_booted_sim_id` |
| Gmail | `list_labels` |
| Google Calendar | `list_calendars` |
| Claude in Chrome, computer-use | covered by steps 4 and 5 |

For any other server, call a tool only if it clearly lists or reads metadata, needs no arguments, has no side effects, and won't return a large document. Otherwise report "connected, not tested". Claude Docs and Google Drive are "connected, not tested": Docs' only read call returns a very long guide, and Drive has no call that avoids file data. Never read messages, files or events, and never include personal data from results in the report; counts only.

Server states:
- `✔` the test call returned, including an answer like "no simulator booted": that's the server working and reporting state, not a failure. A connected server that wasn't tested also counts; say so.
- `⚠` needs sign-in, or still connecting
- `✖` connected but the test call errored, or disconnected

## 4. Browser

Use the first route that exists in this session. Before using it, load the skill that covers it, if that skill is listed:

1. Claude in Chrome (`mcp__claude-in-chrome__*`, skill `chrome-browser`). Read the tab context first, then work in a **new tab**.
2. Built-in browser (`mcp__Claude_Browser__*` or `mcp__remote-devices__Claude_Browser__*`, skill `built-in-browser`).
3. Orca's embedded browser: the `orca` CLI is available inside Orca. Use skill `orca-cli` and its browser reference.
4. None of these → `–`.

Open `https://www.dr.dk` and read back the page title. Close any tab you opened.

- `✔` the title came back: `Orca browser → opened dr.dk`
- If a route fails, report the error you observed, then try the next route. A generic error doesn't prove the site blocked you.

## 5. Computer use

Use the first route that exists:

1. The client's own computer use: an MCP server named `computer-use` (Claude desktop, Codex) or `mcp__remote-devices__computer_*`. Load the client's `computer-use` skill if one is listed.
2. open-cu: a server named `open-cu`, e.g. `mcp__plugin_open-cu_open-cu__*` (skill `open-cu`)
3. Orca computer use (`orca computer`, the Orca `computer-use` skill)
4. None of these → `–`

Recognise servers by name, not by an exact tool prefix, because each client names MCP tools differently.

The task is exactly this: **Draw a smiley person giving a thumbs-up on the screen.** How and where is your choice. The only rule is that every step, including opening the app and drawing, goes through computer-use tools. Don't create an image with the shell, a script or an image generator and then just open it; that doesn't test computer use.

Follow the route's safety rules: no terminals, password managers or sign-in prompts, and don't send or share anything. Leave the drawing on screen and unsaved.

- `✔` a screenshot or app state confirms the smiley person with a thumbs-up is visible: `open-cu → smiley thumbs-up drawn in Freeform`
- If the user presses Esc (`stopped_by_user`), mark it `⚠ stopped by user` and continue the run without retrying.
- If access to the app is declined (`app_not_approved` or similar), mark it `⚠ access to <app> declined`. Don't retry, and don't switch app or route to get around it. Continue the run, and add a To fix row saying how to approve the app.

## 6. News

Use `news` from the probe. Keep the Danish headline as is, and write a **one-sentence summary in the language of the conversation**, based only on the headline and description.

If `news.status` is `fail`, search the web for a current story from dr.dk or tv2.dk and use that; it must have a direct article link. If nothing works, mark `✖` with the reason.

## 7. Report

Output only this. No preamble, and nothing after it except the closing line if one applies. Fill it from your results, and leave out any row or bullet that doesn't apply.

```markdown
## Kick the tires · 29 Oct 2026, 09:14 · took 3:12

- **Client:** Orca 1.4.237 (local build) · Claude Code 2.1.312 · Opus 5.5 (Anthropic)
- **Working:** browser, computer use, news, 47 skills, 2 MCP servers
- **Needs attention:** 2 updates, 3 MCP sign-ins
- **Broken:** none

| Check | | Time | Result |
|---|:-:|--:|---|
| Browser | ✔ | 0:18 | Orca browser → opened dr.dk |
| Computer use | ✔ | 2:05 | open-cu → smiley thumbs-up drawn in Freeform |
| News | ✔ | 0:01 | **DR** · [Samsø frygter eksplosion i dieselpris](https://www.dr.dk/…) — Samsø's ferry company faces a monthly shortfall of DKK 650,000 as diesel prices rise. |
| Skills | ⚠ | 0:03 | 47 ok · 3 warnings · 1 update |
| MCP | ⚠ | 0:09 | 2 ok · 3 need sign-in |
| Updates | ⚠ | 0:02 | Codex 0.163.0 → 0.165.0 · Orca 1.4.237 → 1.4.244 |

### To fix

| # | What | How |
|---|---|---|
| 1 | superpowers 6.2.0 → 7.0.1 | `claude plugin update superpowers@superpowers-marketplace` |
| 2 | Orca 1.4.237 → 1.4.244 (local build) | use the `orca-update` skill |
| 3 | Gmail, Calendar, Drive need sign-in | claude.ai → Settings → Connectors |
```

Rules for filling it in:
- **Summary bullets:** Working, Needs attention and Broken name **areas**, not every item. Drop a bullet that would be empty, except write `**Broken:** none` when nothing is broken.
- **Table:** always these six rows, in this order. Each Result cell is one line: the route used and what it produced.
- **Time column and title:** the Skills, Updates and News times come from the script's `timings` (or your own marks for a web-search fallback). MCP, Browser and Computer use come from your clock marks. The title's `took` is the full run, from your first mark to your last. A check that wasn't available (`–`) gets `–` as its time.
- **Skills cell:** counts from `skills.counts` plus the outdated items in `skillUpdates`. Skills whose update source is unknown aren't a problem; don't count them as warnings.
- **Updates cell:** client updates only (Claude Code, Codex, Orca). Show `✔ all current` when nothing is outdated, or `⚠ couldn't check` with the reason.
- **To fix:** one row per actionable item: every `✖`, every `⚠`, and every outdated skill, plugin or client. Use the `fix` from the probe. For skill problems, give the file to edit. Put the most important first.
- If there is nothing to fix, replace the whole **To fix** section with one line: `**All good.**`
- Report what you observed. Don't invent causes, and keep raw output, personal data and secrets out of the report.
