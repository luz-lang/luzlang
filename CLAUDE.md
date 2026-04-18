# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

If you have any doubt about language behaviour or features, consult the documentation first: https://luz-lang.github.io/luzdocs/

## Docs

- [Commands](docs/commands.md) — how to run tests, the interpreter, linter, and build the C lexer
- [Architecture](docs/architecture.md) — Lexer → Parser → Interpreter pipeline, key runtime objects, error hierarchy
- [Important Patterns](docs/patterns.md) — explicit `self`, builtin shadowing, import resolution
- [Language Features](docs/language-features.md) — typed variables, slices, dict methods, builtins, inheritance
- [Standard Library](docs/stdlib.md) — `libs/` layout, native builtins, `luz.json` requirement
- [C Lexer](docs/c-lexer.md) — `luz/c_lexer/` internals, bridge, build notes
- [GitHub Workflow](docs/github.md) — `gh` CLI usage, issue labels, bug reporting rules
- [Contributing Features](docs/contributing-features.md) — what to update when adding a new feature

## IMPORTANT:
- Any bugs encountered, whether in the code or the language, while adding something else, must be filed as a GitHub issue with `gh issue create` before continuing — read the labels first with `gh label list`.
- When a new feature is implemented, update the docs site (`C:\Users\Eloi\Documents\Proyectos\Python\luzdocs`), the VS Code extension (`C:\Users\Eloi\Documents\Proyectos\Python\vscode-luz`), and the test suite. See [Contributing Features](docs/contributing-features.md).
- When uploading to GitHub, do not include information about Claude, and keep commit messages concise.
