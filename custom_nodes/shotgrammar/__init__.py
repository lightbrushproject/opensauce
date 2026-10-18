"""ShotGrammar node pack. Node modules load lazily so the pure modules work without ComfyUI."""


class _LazyMap(dict):
    """Dict that fills itself from nodes_recipe on first access."""

    def __init__(self, attr):
        super().__init__()
        self._attr = attr
        self._loaded = False

    def _fill(self):
        if not self._loaded:
            self._loaded = True
            from . import (
                nodes_camera_move,
                nodes_disintegrate,
                nodes_earth_zoom,
                nodes_grade_chip,
                nodes_recipe,
                nodes_reproject,
                nodes_speed_ramp,
                nodes_title_card,
            )

            self.update(getattr(nodes_recipe, self._attr))
            self.update(getattr(nodes_reproject, self._attr))
            self.update(getattr(nodes_speed_ramp, self._attr))
            self.update(getattr(nodes_grade_chip, self._attr))
            self.update(getattr(nodes_title_card, self._attr))
            self.update(getattr(nodes_earth_zoom, self._attr))
            self.update(getattr(nodes_camera_move, self._attr))
            self.update(getattr(nodes_disintegrate, self._attr))

    def __getitem__(self, k):
        self._fill()
        return super().__getitem__(k)

    def __iter__(self):
        self._fill()
        return super().__iter__()

    def __len__(self):
        self._fill()
        return super().__len__()

    def __contains__(self, k):
        self._fill()
        return super().__contains__(k)

    def items(self):
        self._fill()
        return super().items()

    def keys(self):
        self._fill()
        return super().keys()

    def values(self):
        self._fill()
        return super().values()

    def get(self, k, default=None):
        self._fill()
        return super().get(k, default)


NODE_CLASS_MAPPINGS = _LazyMap("NODE_CLASS_MAPPINGS")
NODE_DISPLAY_NAME_MAPPINGS = _LazyMap("NODE_DISPLAY_NAME_MAPPINGS")

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
