# GitHub Workflow

## GitHub CLI

All GitHub operations use the `gh` CLI. It is available in the terminal.

```bash
gh issue list                        # list open issues
gh issue create                      # create a new issue
gh issue view <number>               # view an issue
gh pr create                         # open a pull request
gh label list                        # list all labels
```

## Reporting bugs

Before creating an issue, always read the existing labels with `gh label list` and apply the most relevant ones. The main labels are:

| Label | Use for |
|---|---|
| `bug` | Something isn't working |
| `regression` | Something that used to work and is now broken |
| `enhancement` | New feature or request |
| `breaking change` | Changes language semantics or breaks backwards compatibility |
| `interpreter` | Core interpreter changes |
| `parser` | Lexer, parser, or AST changes |
| `compiler` | LLVM backend / codegen |
| `runtime` | Native runtime library (C) |
| `stdlib` | Standard library modules |
| `c-lexer` | C lexer implementation |
| `type-system` | Type inference / type checker |
| `performance` | Performance optimizations |
| `language-design` | Language semantics or syntax decisions |
| `testing` | Test suite |
| `needs triage` | New issue not yet classified |

**Rule:** Any bug found while working on something else must be filed as a GitHub issue immediately — do not fix it inline unless it directly blocks the current task. Use `gh issue create` with the correct labels.

Example:
```bash
gh issue create \
  --title "Parser crashes on empty match block" \
  --body "Repro: ..." \
  --label "bug,parser"
```
