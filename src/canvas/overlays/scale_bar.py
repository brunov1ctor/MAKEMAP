"""Distance formatting helper, shared by the grid's axis labels.

Convention: 1 scene unit == 1 meter (matches typical game-engine convention).
"""


def format_distance(meters: float, decimals: int = 0) -> str:
    if abs(meters) >= 1000:
        km = meters / 1000
        return f"{km:g}km"
    return f"{meters:.{decimals}f}m"
