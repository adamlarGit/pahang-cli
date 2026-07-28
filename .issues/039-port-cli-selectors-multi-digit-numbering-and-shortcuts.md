# Ticket 039: Port CLI Selectors Multi-Digit Numbering and Shortcuts

## Parent Map

[Map 036: Port Johor JBU CLI Features (v2.9.0 -> v2.12.2) to Pahang CLI](file:///.issues/036-port-johor-v2-9-to-latest-features-map.md)

## Type

`task` (AFK)

## Question

How should we overhaul `src/cli_selectors.py` and `tests/test_cli_selectors.py` to support multi-digit numeric menu shortcuts (1..10..11), clean bracketed shortcuts (`[C] Cancel`), custom prompt_toolkit keybindings, and regex title cleaning?

## Source Commits

- `73264dc`: `fix(cli): support sequential multi-digit menu shortcuts (10, 11)`
- `c669826`: `fix(cli): enforce single-character shortcuts for questionary choices`
- `85fd62f`: `feat(cli): modularize option selection with multi-digit numbering`

## Summary of Work

1. Refactor `_with_shortcuts` in `src/cli_selectors.py` to format titles as `1) Option`, `2) Option` ... `10) Option` for numeric options and `[C] Cancel` for bracketed shortcuts.
2. Support multi-digit number sequences beyond 9 by generating sequential number strings and mapping multi-key sequences (`*keys`) in questionary keybindings.
3. Set `use_shortcuts=False` on questionary `InquirerControl` to prevent questionary runtime crashes on single-char shortcut constraints.
4. Clean existing numeric prefixes (`re.sub(r"^\d+[\.\)]\s*", "", title)`) before formatting.
5. Update `tests/test_cli_selectors.py` with multi-digit numbering tests.
