"""
Phase 1/2 shell: typed mode (default) or voice mode (--voice).
Both drive the same real pipeline (planner -> tools -> verification -> memory).
"""
from __future__ import annotations

import sys

from rich.console import Console
from rich.panel import Panel

from app.core.orchestrator import Leo
from app.core.stop import clear_stop, install_hotkey, request_stop

console = Console()

BANNER = "[bold cyan]LEO AI[/bold cyan] [dim]— your desktop assistant[/dim]"


def confirm_action(tool_name: str, reason: str) -> bool:
    console.print(f"[yellow]⚠ Confirmation needed[/yellow] for [bold]{tool_name}[/bold]: {reason}")
    return console.input("Proceed? [y/N] ").strip().lower() in {"y", "yes"}


def _show(outcome, speaker=None):
    style = "green" if outcome.success else "red"
    text = outcome.summary() or "(no response)"
    console.print(Panel(text, border_style=style, title="LEO"))
    if speaker:
        speaker.speak(text.replace("✅", "").replace("❌", "")[:400])


def run_typed(leo: Leo) -> None:
    while True:
        try:
            instruction = console.input("[bold cyan]LEO>[/bold cyan] ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not instruction:
            continue
        if instruction.lower() in {"exit", "quit"}:
            break
        if instruction.lower() in {"stop", "leo stop"}:
            request_stop()
            console.print("[red]Stopped.[/red]")
            continue
        clear_stop()
        _show(leo.handle(instruction))


def run_voice(leo: Leo) -> None:
    from app.voice.engine import Listener, Speaker, VoiceUnavailable, strip_wake_word

    try:
        speaker, listener = Speaker(), Listener()
    except VoiceUnavailable as e:
        console.print(Panel(str(e), title="Voice unavailable", border_style="red"))
        return
    console.print("[green]Listening.[/green] Say 'LEO, <command>'. Say 'LEO stop' to halt, 'LEO exit' to quit.")
    while True:
        try:
            heard = listener.listen_once()
        except VoiceUnavailable as e:
            console.print(f"[red]{e}[/red]")
            break
        if not heard:
            continue
        command = strip_wake_word(heard)
        if command is None:
            continue
        console.print(f"[dim]Heard:[/dim] {heard}")
        if not command:
            speaker.speak("Yes?")
            command = listener.listen_once()
            if not command:
                continue
        if command.lower() in {"stop", "cancel"}:
            request_stop()
            speaker.stop()
            speaker.speak("Stopped.")
            continue
        if command.lower() in {"exit", "quit", "goodbye"}:
            speaker.speak("Goodbye.")
            break
        clear_stop()
        _show(leo.handle(command), speaker)


def main() -> None:
    console.print(BANNER)
    try:
        leo = Leo.bootstrap(confirm_callback=confirm_action)
    except RuntimeError as e:
        console.print(Panel(str(e), title="Configuration error", border_style="red"))
        return
    hotkey_ok = install_hotkey()
    console.print(
        f"Provider: [bold]{leo.provider.name}[/bold] | Mode: [bold]{leo.task_manager.permissions.mode}[/bold] | "
        f"Emergency stop hotkey: {'CTRL+SHIFT+L' if hotkey_ok else 'unavailable (type/say stop)'}"
    )
    if "--voice" in sys.argv:
        run_voice(leo)
    else:
        console.print("Type a command, or 'exit'. (Run with --voice for microphone mode.)")
        run_typed(leo)
    console.print("[dim]Goodbye.[/dim]")


if __name__ == "__main__":
    main()
