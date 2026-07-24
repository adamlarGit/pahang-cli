"""Interactive CLI selector helpers for Pahang CLI."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Generic, Iterable, Sequence, TypeVar


T = TypeVar("T")


@dataclass(frozen=True)
class SelectOption(Generic[T]):
    """One selectable option in an interactive menu."""

    title: str
    value: T
    shortcut_key: str | None = None


def _load_questionary() -> Any:
    """Dynamically load questionary library if available."""
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


def _load_questionary_select_dependencies() -> SimpleNamespace:
    """Load questionary prompt dependencies into a SimpleNamespace container."""
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
    questionary: Any,
    message: str,
    choices: Any,
    *,
    default_value: Any,
) -> Any:
    """Construct an interactive questionary Question prompt instance."""
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

    def get_prompt_tokens() -> list[tuple[str, str]]:
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
    def abort(event: Any) -> None:
        event.app.exit(exception=KeyboardInterrupt, style="class:aborting")

    for index, choice in enumerate(control.choices):
        if isinstance(choice, deps.Separator) or choice.shortcut_key is None or choice.disabled:
            continue

        def register_binding(bound_index: int, shortcut_key: str) -> None:
            @bindings.add(shortcut_key, eager=True)
            def select_choice(event: Any) -> None:
                control.pointed_at = bound_index

        register_binding(index, choice.shortcut_key)

    def move_cursor_down(event: Any) -> None:
        control.select_next()
        while not control.is_selection_valid():
            control.select_next()

    def move_cursor_up(event: Any) -> None:
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
    def set_answer(event: Any) -> None:
        control.is_answered = True
        event.app.exit(result=control.get_pointed_at().value)

    @bindings.add(deps.Keys.Any)
    def other(event: Any) -> None:
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


def _default_child_title(path: Path, _selectable: bool) -> str:
    return path.name


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
        get_child_title = _default_child_title

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
    children = [child for child in directory.iterdir() if child.is_dir()]

    date_children: list[tuple[tuple[int, int, int], Path]] = []
    other_children: list[Path] = []

    for child in children:
        match = re.match(r"^(\d{2})-(\d{2})-(\d{4})$", child.name)
        if match:
            day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
            date_children.append(((year, month, day), child))
        else:
            other_children.append(child)

    if date_children:
        date_children.sort(key=lambda item: item[0], reverse=True)
        sorted_dates = [child for _, child in date_children]
        other_children.sort(key=lambda path: path.name.lower())
        return sorted_dates + other_children

    return sorted(children, key=lambda path: path.name.lower())


def _relative_parts(root: Path, current: Path) -> tuple[str, ...]:
    if current == root:
        return ()
    return current.relative_to(root).parts


def is_pahang_date_folder(path: Path) -> bool:
    """Return True if path is a daily inspection date folder formatted DD-MM-YYYY."""
    return bool(path.is_dir() and re.match(r"^\d{2}-\d{2}-\d{4}$", path.name))


def select_pahang_date_folder(
    root_dir: Path | str | None = None,
    environment: object | None = None,
    title: str = "Select Pahang Inspection Date Folder",
) -> Path | None:
    """Select a 3-tier Pahang date folder (<STATION>/<MONTH>/<DD-MM-YYYY>/) interactively.

    Supports both Active Project Context (via `environment`) and Standalone Utility Context (via `root_dir`).
    """
    base_dir: Path | None = None
    if environment is not None and hasattr(environment, "storage"):
        base_dir = environment.storage.get_testsheet_dir()
    elif root_dir is not None:
        base_dir = Path(root_dir)

    if base_dir is None or not base_dir.exists():
        if environment is not None and hasattr(environment, "get_base_path"):
            base_dir = environment.get_base_path() / "TESTSHEET"
        if base_dir is None or not base_dir.exists():
            return prompt_directory_path("Enter Pahang date folder path: ")

    return select_directory_tree(
        root_path=base_dir,
        title=title,
        is_selectable=is_pahang_date_folder,
        get_child_title=lambda p, selectable: f"[DATE] {p.name}" if selectable else p.name,
        get_confirmation_lines=lambda p: [f"Selected Pahang Date Folder: {p}"],
    )


def prompt_directory_path(
    message: str = "Enter directory path: ",
    default: Path | str | None = None,
    must_exist: bool = True,
) -> Path | None:
    """Prompt the operator for a directory path input with validation."""
    prompt = message
    if default is not None:
        prompt += f" [{default}]: "
    else:
        prompt += ": "

    while True:
        try:
            raw = input(prompt).strip().strip('"')
        except KeyboardInterrupt:
            print()
            return None

        if not raw:
            if default is not None:
                raw_path = Path(default)
                if not must_exist or raw_path.exists():
                    return raw_path
            print("Path selection required.")
            continue

        entered_path = Path(raw)
        if must_exist and not entered_path.exists():
            print(f"Directory not found: {entered_path}. Please enter a valid path.")
            continue

        if must_exist and not entered_path.is_dir():
            print(f"Path is not a directory: {entered_path}. Please try again.")
            continue

        return entered_path

