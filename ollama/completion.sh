if command -v ollama > /dev/null 2>&1; then
  eval "$(ollama completion zsh)"
fi
