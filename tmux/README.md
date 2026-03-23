# tmux

## Authoritative Configuration

**`tmux.config/`** is the live, active configuration.

It symlinks to `~/.config/tmux/` and contains:

- `tmux.conf` — main tmux configuration
- `tmux.reset.conf` — option resets (sourced at the top of `tmux.conf`)

**If you modify tmux config, edit files under `tmux.config/`.**

## Legacy Files (reference only)

`tmux.conf.symlink.disabled` and `tmux.conf.local.symlink.disabled` are the
pre-`.config` directory approach. They are kept for historical reference only
and are **not active**. The `.symlink.disabled` suffix prevents the dotfiles
bootstrap from symlinking them.

Git history preserves their content if they are ever removed.
