# dotfiles — Agent Architecture Guide

This repo is a **topical dotfiles** system, forked from [Zach Holman's dotfiles pattern](https://github.com/holman/dotfiles).
It manages shell configuration, installed tools, and symlinked config files for a macOS developer environment.

---

## How it works

The repo is organized into **topic directories** (e.g., `git/`, `zsh/`, `node/`). Each topic
contains files that follow naming conventions the bootstrap and shell loading machinery understands.
There is no central registry — the conventions ARE the contract.

The `$ZSH` variable points to `~/.dotfiles` (set in `zsh/zshrc.symlink`) and is the root from
which all topic file loading is resolved.

---

## File naming conventions

| Extension / Filename | What happens |
|----------------------|--------------|
| `*.zsh` | Auto-sourced into every interactive shell session via `zshrc.symlink` |
| `*.path` | Sourced after `.zsh` files — use for `$PATH` additions that need priority ordering |
| `completion.sh` | Sourced LAST, after `compinit` — for shell completion scripts |
| `*.symlink` | Symlinked to `~/.{basename}` by `script/bootstrap` (strips `.symlink` extension) |
| `*.config` | Symlinked to `~/.config/{basename}` by `script/bootstrap` (strips `.config` extension) |
| `Brewfile` | Processed by `script/install` via `brew bundle install` |
| `install.sh` | Run by `script/install` after Brewfiles |
| `*.disabled` / `Brewfile.disabled` | **Ignored by all tooling** — soft-disable pattern, no deletion needed |

### Loading order summary

1. `system/` topic runs first (see below)
2. All `*.zsh` files across topics (every shell session)
3. All `*.path` files across topics
4. `compinit` runs
5. All `completion.sh` files across topics

---

## Special topics

### `system/`

The `system/` topic is special: `script/install` runs its `Brewfile` and `install.sh` **before**
all other topics. Use it for foundational dependencies everything else relies on.

### `claudecode/`

The `claudecode/` topic manages agent instructions and Claude Code configuration. Specifically:

- `claudecode/CLAUDE.md` — the repo-level instructions file that Claude Code loads automatically.
  **Edit this file here, not at `~/.claude/CLAUDE.md` directly.** The file is symlinked or managed
  via the bootstrap process so `~/.claude/` reflects the versioned source.
- `claudecode/settings.json` — Claude Code settings, versioned here.
- `claudecode/skills/` — custom slash command skills.
- `claudecode/hooks/` — lifecycle hooks for Claude Code sessions.
- `claudecode/commands/` — custom Claude Code commands.

---

## How to add a new topic

1. Create a directory: `mkdir mytopic/`
2. Add files using the conventions above — e.g., `mytopic/aliases.zsh`, `mytopic/Brewfile`, `mytopic/mytoolrc.symlink`
3. Run `script/bootstrap` to symlink and install, or `script/install` to install packages only

No registration or central config needed. The tooling discovers files by name.

---

## What NOT to do

- **Don't add files outside topic directories.** Files at the repo root (other than `CLAUDE.md`,
  `README.markdown`, `License`) are not discovered by the loading machinery.
- **Don't bypass bootstrap.** Manually placing symlinks in `$HOME` instead of using `script/bootstrap`
  means they won't be tracked or updated when the source changes.
- **Don't edit `~/.claude/` directly.** Make changes in `claudecode/` and let bootstrap propagate them.
- **Don't delete disabled files to "clean up."** The `.disabled` suffix IS the off-switch — removing
  the file loses the configuration if you want to re-enable it later.

---

## Key paths

| Path | Purpose |
|------|---------|
| `~/.dotfiles` (`$ZSH`) | The repo, cloned here by convention |
| `script/bootstrap` | Initial setup: gitconfig, symlinks, Homebrew |
| `script/install` | Idempotent: runs Brewfiles and install.sh scripts |
| `zsh/zshrc.symlink` | Shell entry point; sets `$ZSH` and sources all topic files |
| `system/` | First-run dependencies (fonts, base tools) |
| `claudecode/` | Agent instructions and Claude Code config |
