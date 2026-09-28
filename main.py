"""
LEO AI entry point.

    python main.py            typed command shell
    python main.py --voice    microphone mode in the terminal
    python main.py --ui       3D desktop interface (recommended)
"""
import sys

if __name__ == "__main__":
    if "--ui" in sys.argv:
        from app.ui.server import serve

        try:
            serve()
        except RuntimeError as e:
            print(e)
    else:
        from app.ui.cli import main

        main()
