"""Interactive CLI selector helpers for Pahang CLI."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Generic, Iterable, Sequence, TypeVar


T = TypeVar("T")


@dataclass(frozen=True)
class SelectOption(Generic[T]):
    """One selectable option in an interactive menu."""

    title: str
    value: T
    shortcut_key: str | None = None


def _load_questionary():
    try:
        import questionary
    except ImportError:
        return None
    return questionary


def _with_shortcuts(options: Sequence[SelectOption[T]]) -> list[SelectOption[T]]:
    updated: list[SelectOption[T]] = []
    used_shortcuts = {
        option.shortcut_key.lower()
        for option in options
        if option.shortcut_key is not None
    }
    next_digit = 1

    for option in options:
        if option.shortcut_key is not None:
            updated.append(option)
            continue

        shortcut_key = None
        while next_digit <= 9:
            candidate = str(next_digit)
            next_digit += 1
            if candidate not in used_shortcuts:
                shortcut_key = candidate
                used_shortcuts.add(candidate)
                break

        updated.append(
            SelectOption(
                title=option.title,
                value=option.value,
                shortcut_key=shortcut_key,
            )
        )

    return updated


def _load_questionary_select_dependencies():
    from prompt_toolkit.application import Application
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.keys import Keys
    from questionary.constants import DEFAULT_QUESTION_PREFIX, DEFAULT_SELECTED_POINTER
    from questionary.prompts import common
    from questionary.prompts.common import InquirerControl, Separator
    from questionary.question import Question
    from questionary.styles import merge_styles_default

    return SimpleNamespace(
        Application=Application,
        DEFAULT_QUESTION_PREFIX=DEFAULT_QUESTION_PREFIX,
        DEFAULT_SELECTED_POINTER=DEFAULT_SELECTED_POINTER,
        InquirerControl=InquirerControl,
        KeyBindings=KeyBindings,
        Keys=Keys,
        Question=Question,
        Separator=Separator,
        common=common,
        merge_styles_default=merge_styles_default,
    )


def _build_questionary_prompt(
    questionary,
    message: str,
    choices,
    *,
    default_value,
):
    deps = _load_questionary_select_dependencies()
    control = deps.InquirerControl(
        choices,
        default=None,
        pointer=deps.DEFAULT_SELECTED_POINTER,
        use_indicator=False,
        use_shortcuts=True,
        show_selected=False,
        show_description=True,
        use_arrow_keys=True,
        initial_choice=default_value,
    )

    def get_prompt_tokens():
        tokens = [
            ("class:qmark", deps.DEFAULT_QUESTION_PREFIX),
            ("class:question", f" {message} "),
        ]

        if control.is_answered:
            title = control.get_pointed_at().title
            if isinstance(title, list):
                tokens.append(("class:answer", "".join(token[1] for token in title)))
            else:
                tokens.append(("class:answer", title))
        else:
            tokens.append(("class:instruction", "(Use shortcuts or arrow keys, Enter/Space to select)"))

        return tokens

    layout = deps.common.create_inquirer_layout(control, get_prompt_tokens)
    bindings = deps.KeyBindings()

    @bindings.add(deps.Keys.ControlQ, eager=True)
    @bindings.add(deps.Keys.ControlC, eager=True)
    def abort(event):
        event.app.exit(exception=KeyboardInterrupt, style="class:aborting")

    for index, choice in enumerate(control.choices):
        if isinstance(choice, deps.Separator) or choice.shortcut_key is None or choice.disabled:
            continue

        def register_binding(bound_index, shortcut_key):
            @bindings.add(shortcut_key, eager=True)
            def select_choice(event):
                control.pointed_at = bound_index

        register_binding(index, choice.shortcut_key)

    def move_cursor_down(event):
        control.select_next()
        while not control.is_selection_valid():
            control.select_next()

    def move_cursor_up(event):
        control.select_previous()
        while not control.is_selection_valid():
            control.select_previous()

    bindings.add(deps.Keys.Down, eager=True)(move_cursor_down)
    bindings.add(deps.Keys.Up, eager=True)(move_cursor_up)
    bindings.add("j", eager=True)(move_cursor_down)
    bindings.add("k", eager=True)(move_cursor_up)
    bindings.add(deps.Keys.ControlN, eager=True)(move_cursor_down)
    bindings.add(deps.Keys.ControlP, eager=True)(move_cursor_up)

    @bindings.add(" ", eager=True)
    @bindings.add(deps.Keys.ControlM, eager=True)
    def set_answer(event):
        control.is_answered = True
        event.app.exit(result=control.get_pointed_at().value)

    @bindings.add(deps.Keys.Any)
    def other(event):
        """Disallow inserting other text."""

    style = deps.merge_styles_default(
        [
            questionary.Style(
                [
                    ("selected", ""),
                    ("highlighted", "reverse"),
                ]
            )
        ]
    )

    return deps.Question(
        deps.Application(
            layout=layout,
            key_bindings=bindings,
            style=style,
        )
    )


def select_one(
    message: str,
    options: Sequence[SelectOption[T]],
    *,
    default_value: T | None = None,
) -> T | None:
    """Return a single selected value, or None when cancelled."""
    if not options:
        raise ValueError("select_one requires at least one option.")

    options_with_shortcuts = _with_shortcuts(options)
    questionary = _load_questionary()
    if questionary is not None:
        choices = [
            questionary.Choice(
                title=option.title,
                value=option.value,
                shortcut_key=option.shortcut_key,
            )
            for option in options_with_shortcuts
        ]
        try:
            return _build_questionary_prompt(
                questionary,
                message,
                choices,
                default_value=default_value,
            ).ask()
        except KeyboardInterrupt:
            return None

    return _fallback_select_one(message, options_with_shortcuts, default_value=default_value)


def _fallback_select_one(
    message: str,
    options: Sequence[SelectOption[T]],
    *,
    default_value: T | None = None,
) -> T | None:
    shortcut_map = {
        option.shortcut_key.lower(): option.value
        for option in options
        if option.shortcut_key is not None
    }

    while True:
        print(message)
        for index, option in enumerate(options, start=1):
            shortcut = f"[{option.shortcut_key}] " if option.shortcut_key else ""
            default_marker = " (default)" if option.value == default_value else ""
            print(f"{index}. {shortcut}{option.title}{default_marker}")

        prompt = "Choose an option"
        if default_value is not None:
            prompt += " [Enter for default]"
        prompt += ": "

        try:
            raw_value = input(prompt).strip()
        except KeyboardInterrupt:
            print()
            return None

        if not raw_value:
            if default_value is not None:
                return default_value
            print("Selection required.")
            continue

        shortcut_value = shortcut_map.get(raw_value.lower())
        if shortcut_value is not None:
            return shortcut_value

        try:
            selected_index = int(raw_value) - 1
            return options[selected_index].value
        except (ValueError, IndexError):
            print("Invalid selection. Please enter a valid number or shortcut.")


def select_multiple(
    message: str,
    options: Sequence[SelectOption[T]],
) -> list[T] | None:
    """Prompt the operator to select one or more options interactively."""
    if not options:
        return []

    questionary = _load_questionary()
    if questionary is not None:
        try:
            choices = [
                questionary.Choice(title=opt.title, value=opt.value)
                for opt in options
            ]
            result = questionary.checkbox(message, choices=choices).ask()
            if result is None:
                return None
            return list(result)
        except KeyboardInterrupt:
            return None

    return _fallback_select_multiple(message, options)


def _fallback_select_multiple(
    message: str,
    options: Sequence[SelectOption[T]],
) -> list[T] | None:
    while True:
        print(f"\n{message}")
        for index, option in enumerate(options, start=1):
            print(f"{index}. {option.title}")

        print("Enter comma-separated numbers (e.g. 1, 3, 4), 'all' to select everything, or 'c' to cancel: ", end="")
        try:
            raw_value = input().strip()
        except KeyboardInterrupt:
            print()
            return None

        if not raw_value or raw_value.lower() in ("c", "cancel"):
            return None
        if raw_value.lower() == "all":
            return [opt.value for opt in options]

        parts = [p.strip() for p in raw_value.split(",") if p.strip()]
        selected: list[T] = []
        invalid = False
        for p in parts:
            try:
                idx = int(p) - 1
                if 0 <= idx < len(options):
                    selected.append(options[idx].value)
                else:
                    invalid = True
                    break
            except ValueError:
                invalid = True
                break

        if invalid or not selected:
            print("Invalid input. Please enter valid option numbers separated by commas.")
            continue

        return selected


def confirm(message: str, *, default: bool = False) -> bool | None:
    """Return confirmation state, or None when cancelled."""
    questionary = _load_questionary()
    if questionary is not None:
        try:
            return questionary.confirm(message, default=default).ask()
        except KeyboardInterrupt:
            return None

    default_prompt = "Y/n" if default else "y/N"
    while True:
        try:
            raw_value = input(f"{message} [{default_prompt}]: ").strip().lower()
        except KeyboardInterrupt:
            print()
            return None

        if not raw_value:
            return default
        if raw_value in {"y", "yes"}:
            return True
        if raw_value in {"n", "no"}:
            return False
        print("Invalid confirmation. Please try again.")


def select_directory_tree(
    root_path: str | Path,
    *,
    title: str,
    is_selectable: Callable[[Path], bool],
    get_child_title: Callable[[Path, bool], str] | None = None,
    get_confirmation_lines: Callable[[Path], Iterable[str]] | None = None,
) -> Path | None:
    """Navigate a directory tree until a selectable folder is confirmed."""
    root = Path(root_path)
    if not root.exists():
        raise FileNotFoundError(f"Directory not found: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {root}")

    if get_child_title is None:
        get_child_title = lambda path, selectable: path.name

    @lru_cache(maxsize=None)
    def has_selectable_descendant(directory: Path) -> bool:
        for child in _iter_directory_children(directory):
            if is_selectable(child) or has_selectable_descendant(child):
                return True
        return False

    current = root
    history: list[Path] = []

    while True:
        selectable = is_selectable(current)
        children = [
            child
            for child in _iter_directory_children(current)
            if is_selectable(child) or has_selectable_descendant(child)
        ]

        breadcrumb = " > ".join((root.name, *_relative_parts(root, current)))
        options: list[SelectOption[tuple[str, Path] | str]] = []
        if selectable:
            options.append(SelectOption("Confirm this batch", ("confirm", current)))

        for child in children:
            options.append(
                SelectOption(
                    get_child_title(child, is_selectable(child)),
                    ("child", child),
                )
            )

        if current != root:
            options.append(SelectOption("Back", "__back__", shortcut_key="b"))
        options.append(SelectOption("Cancel", "__cancel__", shortcut_key="c"))

        selection = select_one(f"{title}\n{breadcrumb}", options)
        if selection is None or selection == "__cancel__":
            return None

        if selection == "__back__":
            current = history.pop()
            continue

        action, path = selection
        if action == "child":
            history.append(current)
            current = path
            continue

        if action == "confirm":
            if get_confirmation_lines is None:
                return current

            confirmation_message = "\n".join(get_confirmation_lines(current))
            confirmed = confirm(confirmation_message, default=True)
            if confirmed is None:
                return None
            if confirmed:
                return current


def _iter_directory_children(directory: Path) -> list[Path]:
    return sorted(
        (child for child in directory.iterdir() if child.is_dir()),
        key=lambda path: path.name.lower(),
    )


def _relative_parts(root: Path, current: Path) -> tuple[str, ...]:
    if current == root:
        return ()
    return current.relative_to(root).parts
