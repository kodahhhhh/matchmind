"""Fixture team palette and perceptual kit separation, ported from make_fixtures."""

import math

COLORS = {
    "_default": ["#9AA7B0", "#D9A441"],
    "Albania": ["#E5484D", "#F2C14E"],
    "Argentina": ["#7CB9E8", "#F2C14E"],
    "Augsburg": ["#E5484D", "#3FA06B"],
    "Australia": ["#F2C14E", "#2FA36B"],
    "Austria": ["#E5484D", "#D8DEE4"],
    "Bayer Leverkusen": ["#E8423F", "#B0B8C0"],
    "Bayern Munich": ["#E5354A", "#4C8FE0"],
    "Belgium": ["#E5484D", "#F2C14E"],
    "Bochum": ["#4C7FE0", "#D8DEE4"],
    "Bolivia": ["#3FA06B", "#F2C14E"],
    "Borussia Dortmund": ["#F7D117", "#B0B8C0"],
    "Borussia Mönchengladbach": ["#3FA06B", "#D8DEE4"],
    "Brazil": ["#F7D117", "#3D8BFF"],
    "Cameroon": ["#2FA36B", "#E5484D"],
    "Canada": ["#E5484D", "#D8DEE4"],
    "Charlotte": ["#4FA3E0", "#D8DEE4"],
    "Chile": ["#E5484D", "#4C7FE0"],
    "Cincinnati": ["#F26B3A", "#4C7FE0"],
    "Colombia": ["#F7D117", "#4C7FE0"],
    "Costa Rica": ["#E5484D", "#4C7FE0"],
    "Croatia": ["#E5484D", "#4C7FE0"],
    "Czech Republic": ["#E5484D", "#4C7FE0"],
    "Darmstadt 98": ["#4C7FE0", "#D8DEE4"],
    "Denmark": ["#E5484D", "#D8DEE4"],
    "Ecuador": ["#F7D117", "#4C7FE0"],
    "Eintracht Frankfurt": ["#E5484D", "#B0B8C0"],
    "England": ["#D8DEE4", "#E5484D"],
    "FC Heidenheim": ["#E5484D", "#4C7FE0"],
    "FC Köln": ["#E5484D", "#D8DEE4"],
    "FSV Mainz 05": ["#E5484D", "#D8DEE4"],
    "France": ["#4C7FE0", "#E5484D"],
    "Freiburg": ["#E5484D", "#B0B8C0"],
    "Georgia": ["#E5484D", "#D8DEE4"],
    "Germany": ["#D8DEE4", "#3FA06B"],
    "Ghana": ["#F2C14E", "#E5484D"],
    "Hamburger SV": ["#4C8FE0", "#E5484D"],
    "Hannover 96": ["#3FA06B", "#E5484D"],
    "Hertha Berlin": ["#4C8FE0", "#D8DEE4"],
    "Hoffenheim": ["#4C7FE0", "#D8DEE4"],
    "Hungary": ["#E5484D", "#3FA06B"],
    "Ingolstadt": ["#E5484D", "#B0B8C0"],
    "Inter Miami": ["#F5A3C7", "#B0B8C0"],
    "Iran": ["#D8DEE4", "#E5484D"],
    "Italy": ["#4C8FE0", "#D8DEE4"],
    "Jamaica": ["#F7D117", "#2FA36B"],
    "Japan": ["#4C7FE0", "#E5484D"],
    "LAFC": ["#D4B26A", "#B0B8C0"],
    "Mexico": ["#2FA36B", "#E5484D"],
    "Morocco": ["#E5484D", "#2FA36B"],
    "Nashville SC": ["#F2D04B", "#4C7FE0"],
    "Netherlands": ["#F7882F", "#4C7FE0"],
    "New York Red Bulls": ["#E5484D", "#D8DEE4"],
    "Panama": ["#E5484D", "#4C7FE0"],
    "Paraguay": ["#E5484D", "#4C7FE0"],
    "Peru": ["#E5484D", "#D8DEE4"],
    "Poland": ["#E5484D", "#D8DEE4"],
    "Portugal": ["#E5354A", "#3FA06B"],
    "Qatar": ["#B23A5A", "#D8DEE4"],
    "RB Leipzig": ["#E5484D", "#D8DEE4"],
    "Romania": ["#F7D117", "#4C7FE0"],
    "Saudi Arabia": ["#2FA36B", "#D8DEE4"],
    "Schalke 04": ["#4C7FE0", "#D8DEE4"],
    "Scotland": ["#4C7FE0", "#D8DEE4"],
    "Senegal": ["#D8DEE4", "#2FA36B"],
    "Serbia": ["#E5484D", "#D8DEE4"],
    "Slovakia": ["#4C7FE0", "#E5484D"],
    "Slovenia": ["#D8DEE4", "#3FA06B"],
    "South Korea": ["#E5484D", "#4C7FE0"],
    "Spain": ["#E5354A", "#F2C14E"],
    "Switzerland": ["#E5484D", "#D8DEE4"],
    "Toronto FC": ["#E5484D", "#B0B8C0"],
    "Tunisia": ["#E5484D", "#D8DEE4"],
    "Turkey": ["#E5484D", "#D8DEE4"],
    "Ukraine": ["#F7D117", "#4C7FE0"],
    "Union Berlin": ["#E5484D", "#F2D04B"],
    "United States": ["#D8DEE4", "#4C7FE0"],
    "Uruguay": ["#7CB9E8", "#D8DEE4"],
    "Venezuela": ["#9E2B3A", "#F2C14E"],
    "VfB Stuttgart": ["#D8DEE4", "#E5484D"],
    "Wales": ["#E5484D", "#3FA06B"],
    "Werder Bremen": ["#3FA06B", "#D8DEE4"],
    "Wolfsburg": ["#7DC242", "#D8DEE4"],
}


def team_colors(name: str, table: dict = COLORS) -> dict:
    c = table.get(name) or table["_default"]
    return {"primary": c[0], "alt": c[1]}


def _oklab(hex_: str):
    rgb = [int(hex_[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb]
    ll = 0.4122214708 * lin[0] + 0.5363325363 * lin[1] + 0.0514459929 * lin[2]
    m = 0.2119034982 * lin[0] + 0.6806995451 * lin[1] + 0.1073969566 * lin[2]
    s = 0.0883024619 * lin[0] + 0.2817188376 * lin[1] + 0.6299787005 * lin[2]
    ll, m, s = (v ** (1 / 3) for v in (ll, m, s))
    return (
        0.2104542553 * ll + 0.7936177850 * m - 0.0040720468 * s,
        1.9779984951 * ll - 2.4285922050 * m + 0.4505937099 * s,
        0.0259040371 * ll + 0.7827717662 * m - 0.8086757660 * s,
    )


def match_colors(home: str, away: str, table: dict = COLORS) -> tuple[str, str]:
    """Separate team colours perceptually while preserving kit identity."""
    h, a = team_colors(home, table), team_colors(away, table)

    def dist(x: str, y: str) -> float:
        return 100 * math.dist(_oklab(x), _oklab(y))

    away_c = a["primary"] if dist(h["primary"], a["primary"]) >= 25 else a["alt"]
    if dist(h["primary"], away_c) < 25:  # both away options clash: home falls back too
        return h["alt"], a["primary"]
    return h["primary"], away_c


def short_name(nick: str | None, full: str) -> str:
    base = nick or full
    parts = base.split()
    if nick and len(parts) >= 2:
        return " ".join(parts[1:])
    return parts[-1] if parts else base


def team_short(name: str) -> str:
    return name.replace(" ", "")[:3].upper()
