"""Discovers installed apps under /apps and loads their icons."""

import os
from sprite import Sprite

ICON_SIZE = 32
icon_cache = {}


class App:
    def __init__(self, name, icon_path):
        self.name = name
        self.icon_path = icon_path
        self.icon = self._load_icon(icon_path)

    def _load_icon(self, path):
        if not path:
            return None
        if path in icon_cache:
            return icon_cache[path]
        try:
            sprite = Sprite(path)  # path points at icon.spr
            icon_cache[path] = sprite
            return sprite
        except Exception as e:
            print("Failed to load icon", path, ":", e)
            return None


def list_apps():
    result = []
    try:
        for d in os.listdir("apps"):
            path = "apps/" + d
            try:
                entries = os.listdir(path)
            except:
                continue
            if "main.py" not in entries:
                continue
            icon = path + "/icon.spr" if "icon.spr" in entries else None
            result.append(App(d, icon))
    except:
        pass
    return result
