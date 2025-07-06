"""
main.py
~~~~~~~
Entry-point that simply starts the Pyrogram client from bot.py.
"""

from bot import app

if __name__ == "__main__":
    print("→ Video-Sort Bot running…")
    app.run()
