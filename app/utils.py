MINIMUM_PASSWORD_LENGTH = 8


def parse_coordinate(raw_value):
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return None


def parse_int(raw_value):
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return None
