# Adding New Features

When a new language feature, builtin, or standard library module is implemented, three places must be updated:

## 1. Luz documentation site

Path: `C:\Users\Eloi\Documents\Proyectos\Python\luzdocs`

The site is built with MkDocs. Add or edit pages under `docs/`. Typical locations:

- New syntax / language feature → `docs/language/`
- New builtin function → `docs/builtins.md`
- New standard library module → `docs/stdlib/`
- Architecture changes → `docs/architecture.md`

Reference the live site for current structure: https://luz-lang.github.io/luzdocs/

## 2. VS Code extension

Path: `C:\Users\Eloi\Documents\Proyectos\Python\vscode-luz`

Depending on what changed:

- New keyword or operator → `syntaxes/` (TextMate grammar)
- New builtin function → `snippets/` and/or the completion provider in `src/`
- New syntax construct → `language-configuration.json` if it affects brackets/comments

## 3. Test suite

Add at least one test in `tests/test_suite.py` covering the happy path and relevant edge cases.
