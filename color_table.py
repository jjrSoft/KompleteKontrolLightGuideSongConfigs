import yaml



class ColorTable:
    def __init__(self, colors_file):
        with open(colors_file, "r") as f:
            colors = yaml.safe_load(f)

        self.colors = {
            k.lower(): v
            for k, v in colors.items()
        }

    def color_to_rgb(self, color):
        value = self.colors.get(color.lower()) if isinstance(color, str) else color

        if value is None and isinstance(color, str):
            hex_value = color.lstrip("#")
            if len(hex_value) != 6:
                raise ValueError(f"Invalid RGB color: {color}")
            try:
                value = int(hex_value, 16)
            except ValueError as ex:
                raise ValueError(f"Invalid RGB color: {color}") from ex

        if isinstance(value, list):
            if (len(value) != 3
                    or any(not isinstance(channel, int)
                           or isinstance(channel, bool)
                           or not 0 <= channel <= 255
                           for channel in value)):
                raise ValueError(f"Invalid RGB color: {color}")
            return value

        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 0xFFFFFF:
            raise ValueError(f"Invalid RGB color: {color}")

        return [
            (value >> 16) & 0xFF,
            (value >> 8) & 0xFF,
            value & 0xFF,
        ]
