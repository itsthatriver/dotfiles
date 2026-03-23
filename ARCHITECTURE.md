# Dotfiles Architecture

This document explains how the dotfiles system works mechanically — the bootstrap
flow, ZSH loading order, and the conventions that tie everything together.

---

## Bootstrap Flow

Run `script/bootstrap` to set up a new machine from scratch.

```
script/bootstrap
  ├── setup_gitconfig        (creates ~/.local.gitconfig if absent)
  ├── install_dotfiles       (symlinks *.symlink → ~/.<name>)
  ├── install_configfiles    (symlinks *.config → ~/.config/<name>)
  └── script/install         (macOS only — installs packages)
       ├── system/Brewfile    (system-level packages first)
       ├── system/install.sh  (system-level setup first)
       ├── */Brewfile         (per-topic Brewfiles)
       └── */install.sh       (per-topic installers)
```

### Symlinking conventions

`install_dotfiles` finds every `*.symlink` file up to two levels deep and creates
a corresponding symlink in `$HOME`:

```
<topic>/foo.symlink  →  ~/.foo
```

`install_configfiles` does the same for `*.config` files, placing them under
`~/.config/` instead:

```
<topic>/bar.config  →  ~/.config/bar
```

If a destination already exists, bootstrap asks whether to skip, overwrite, or
back it up. Pass `--overwrite-all` or `--backup-all` to skip the prompt.

### Why `system/` runs first

`script/install` explicitly processes `system/Brewfile` and `system/install.sh`
before iterating the other topics. This ensures core packages (compilers,
Homebrew formulae, CLI tools) are present before topic installers try to use them.
Topic installers that depend on, say, `git` or `brew` being available will always
find them ready.

---

## ZSH Loading Order

`zsh/zshrc.symlink` is symlinked to `~/.zshrc` and is the single entry point for
interactive ZSH sessions. It loads configuration in this order:

| Order | What | Notes |
|-------|------|-------|
| 1 | `ulimit -n 4096` | Raise open-file limit before anything else |
| 2 | `export ZSH=$HOME/.dotfiles` | Anchors all glob patterns — see [$ZSH variable](#the-zsh-variable) |
| 3 | `brew --prefix` / Homebrew shellenv | Locates Homebrew prefix for subsequent sourcing |
| 4 | `zsh-syntax-highlighting` (optional) | Sourced only if installed via Homebrew |
| 5 | `zsh-autosuggestions` (optional) | Sourced only if installed via Homebrew |
| 6 | `$ZSH/**/*.zsh` | All `.zsh` files across every topic, excluding `backups/` |
| 7 | `$ZSH/**/*.path` | All `.path` files — PATH modifications after general config |
| 8 | `compinit` | Initialises ZSH completion; throttled to once per 24 h |
| 9 | `$ZSH/**/completion.sh` | Per-topic completion scripts, loaded after `compinit` |
| 10 | `zoxide init zsh` | Directory-jumping tool initialised after completions |
| 11 | iTerm2 shell integration | Sourced if `~/.iterm2_shell_integration.zsh` exists |
| 12 | `~/.localrc` | Machine-local overrides sourced last |

**Why `.path` files come after `.zsh` files:** completion scripts may need to
execute binaries (e.g. `mise`, `rbenv`) that are added to `$PATH` by `.path`
files. Sourcing `.path` first ensures those binaries are resolvable when
completions initialise.

**Why `completion.sh` files come after `compinit`:** `compinit` must run before
any `compdef` calls can succeed, so completion registrations are deferred until
step 9.

---

## The `$ZSH` Variable

`zshrc.symlink` sets `ZSH` to `$HOME/.dotfiles` early in startup:

```zsh
export ZSH=$HOME/.dotfiles
```

Every glob pattern in `zshrc.symlink` is written relative to `$ZSH`:

```zsh
for config_file ($ZSH/**/*.zsh~*/backups/*) source $config_file
```

This means the entire topic-file loading mechanism works from one canonical root,
and agents or scripts can rely on `$ZSH` to locate any file in the repo.

---

## Soft-Disable Pattern

Append `.disabled` to any file to exclude it from all tooling without deleting it:

```
vim/vimrc.symlink.disabled    # not symlinked by bootstrap
vim/install.sh.disabled       # not run by script/install
vim/Brewfile.disabled         # not processed by brew bundle
```

The glob patterns in both `script/install` and `zshrc.symlink` match on exact
extensions (`.symlink`, `.config`, `.zsh`, `.path`, `completion.sh`, `install.sh`,
`Brewfile`). A `.disabled` suffix breaks the match, so the file is silently
ignored. Use this instead of deleting configs you may want to re-enable later.

---

## Local Overrides (`~/.localrc`)

`~/.localrc` is sourced at the very end of `zshrc.symlink` and is **not committed
to the repo** (gitignored by convention, not the `.gitignore` in this repo — add
it to your global gitignore or simply never `git add` it).

Use it for:

- Machine-specific environment variables (`$WORK_TOKEN`, `$GOPATH`, etc.)
- API keys and secrets
- Aliases or functions that override repo defaults
- Anything that should not be public or shared across machines

Because it loads last, anything in `~/.localrc` takes precedence over every
topic file.

---

## Topic Structure

Each subdirectory is a *topic* — a self-contained unit for one tool or concern.
A topic can contain any combination of:

| File | Purpose |
|------|---------|
| `*.symlink` | Symlinked to `~/.<name>` by bootstrap |
| `*.config` | Symlinked to `~/.config/<name>` by bootstrap |
| `*.zsh` | Sourced at ZSH startup (step 6 above) |
| `*.path` | PATH modifications sourced after `.zsh` files (step 7) |
| `completion.sh` | Completion definitions sourced after `compinit` (step 9) |
| `Brewfile` | Homebrew packages installed by `script/install` |
| `install.sh` | Arbitrary setup script run by `script/install` |

Topics are discovered by glob — there is no registry. Adding a new topic
directory with the right file extensions is sufficient for it to be picked up.
