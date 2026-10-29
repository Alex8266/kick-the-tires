# kick-the-tires

An agent skill that health-checks your AI agent setup and gives you a short status report.

It checks:

- **Client:** which client, agent and model are running
- **Skills:** every installed skill, for broken or mismatched files and available updates
- **MCP servers:** each connected server, with one read-only test call
- **Browser:** opens dr.dk through whichever browser route the session has
- **Computer use:** draws a smiley person giving a thumbs-up in a desktop app
- **News:** a fresh headline from DR or TV 2
- **Updates:** newer releases of Claude Code, Codex and Orca

The skill only reports. It never installs, updates, signs in or changes settings; the report tells you how to fix things.

Needs `git` and `python3` (standard library only). Built and tested on macOS with Claude Code and Codex.

## Give this to your AI agent

Paste this into Claude Code, Codex or another coding agent. It may ask permission to download the repo and write to your home folder.

```text
Install the "kick-the-tires" agent skill from https://github.com/Alex8266/kick-the-tires.

1. Clone the repo to ~/.agents/skills/kick-the-tires. If that folder already exists, run `git pull` in it instead.
2. Make the skill visible to yourself:
   - Codex: nothing more to do; you load skills from ~/.agents/skills.
   - Claude Code: mkdir -p ~/.claude/skills && ln -s ~/.agents/skills/kick-the-tires ~/.claude/skills/kick-the-tires (skip if it already exists).
   - Any other agent: link or copy the folder to wherever you load skills from.
3. Check that python3 runs and that SKILL.md is in the installed folder.
4. Don't run the skill now. Tell me it's installed, how to start it in this agent (/kick-the-tires in Claude Code, $kick-the-tires in Codex, or just say "kick the tires"), and that a new session may be needed before it shows up.
```
