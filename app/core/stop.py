"""Global emergency stop flag (spec: CTRL+SHIFT+L or voice 'LEO STOP')."""
import threading

_STOP = threading.Event()


def request_stop() -> None:
    _STOP.set()


def clear_stop() -> None:
    _STOP.clear()


def stop_requested() -> bool:
    return _STOP.is_set()


def install_hotkey(hotkey: str = "ctrl+shift+l") -> bool:
    """Register the global hotkey if the optional 'keyboard' package works here."""
    try:
        import keyboard

        keyboard.add_hotkey(hotkey, request_stop)
        return True
    except Exception:  # noqa: BLE001 - missing package / no permission / no display
        return False
