# kick-the-tires

An agent skill that health-checks your AI agent setup and gives you a short status report.

It checks:

- **Client:** which client, agent and model are running
- **Skills:** every installed skill, for broken or mismatched files and available updates
- **MCP servers:** each connected server, with one read-only test call
- **Browser:** opens your Google account page in your own browser to confirm the agent can use your signed-in sessions (the report never shows your name or email)
- **Computer use:** draws a smiley person giving a thumbs-up in a desktop app
- **Web search:** the agent searches the web for fresh Danish news, then fetches the article it finds, to prove it can get live information from the internet
- **Updates:** newer releases of Claude Code, Codex and Orca

The skill only reports. It never installs, updates, signs in or changes settings; the report tells you how to fix things.

Needs `git` and `python3` (standard library only). Built and tested on macOS with Claude Code and Codex.

## Give this to your AI agent

```text
Install the "kick-the-tires" agent skill from https://github.com/Alex8266/kick-the-tires.
Then start the skill. If it isn't available yet, restart the app you're running in and start it in a fresh new chat.
```
