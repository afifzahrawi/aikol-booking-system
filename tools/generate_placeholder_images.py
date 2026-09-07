#!/usr/bin/env python3
"""
Generate placeholder resource images for the AIKOL Booking System prototype.

Covers venues and vehicles. Cars only in the first release.

Why this exists
---------------
The prototype must not copy photographs or brand assets from the internet, and
it must run entirely offline. This script produces simple, clearly-artificial
SVG illustrations that stand in for real venue photographs during design review.

Every generated image is watermarked "PLACEHOLDER" so that no one mistakes it
for an actual photograph of an AIKOL facility. Replace these files with real
photographs supplied by the Kulliyyah before any production deployment.

Usage:
    python tools/generate_placeholder_images.py
"""

import os

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "prototype", "assets", "images")

# slug, display name, venue code, accent colour
VENUES = [
    ("moot-court",  "Moot Court Room",   "AIKOL-MC-01", "#0e4732"),
    ("seminar-a",   "Seminar Room 1",    "AIKOL-SR-01", "#1f4e79"),
    ("seminar-b",   "Seminar Room 2",    "AIKOL-SR-02", "#255f8a"),
    ("meeting-a",   "Meeting Room A",    "AIKOL-MR-01", "#5a4a86"),
    ("meeting-b",   "Meeting Room B",    "AIKOL-MR-02", "#6b5a2e"),
    ("lecture",     "Lecture Room 1",    "AIKOL-LR-01", "#8a3a3a"),
    ("discussion",  "Discussion Room 1", "AIKOL-DR-01", "#2f6b63"),
    ("conference",  "Conference Room",   "AIKOL-CR-01", "#3d5a80"),
]

W, H = 800, 450


def header(accent, light):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img">
  <defs>
    <linearGradient id="wall" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="{light}"/>
      <stop offset="1" stop-color="#ffffff"/>
    </linearGradient>
    <pattern id="hatch" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
      <rect width="8" height="8" fill="none"/>
      <line x1="0" y1="0" x2="0" y2="8" stroke="{accent}" stroke-opacity=".13" stroke-width="3"/>
    </pattern>
  </defs>
  <rect width="{W}" height="{H}" fill="url(#wall)"/>'''


def watermark(name, code, variant, accent):
    return f'''  <rect x="0" y="{H-46}" width="{W}" height="46" fill="{accent}" fill-opacity=".92"/>
  <text x="24" y="{H-18}" font-family="Georgia, serif" font-size="19" fill="#ffffff">{name}</text>
  <text x="{W-24}" y="{H-18}" text-anchor="end" font-family="Segoe UI, Arial, sans-serif"
        font-size="12" fill="#ffffff" fill-opacity=".85" letter-spacing="1.5">PLACEHOLDER IMAGE · {code} · VIEW {variant}</text>
</svg>
'''


def seats(x0, y0, cols, rows, dx, dy, shrink, accent):
    out = []
    for r in range(rows):
        w = 46 - r * shrink
        h = 14 - r * (shrink / 4.0)
        for c in range(cols):
            x = x0 + c * dx + r * (dx * 0.18)
            y = y0 + r * dy
            out.append(f'    <rect x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h:.0f}" rx="3" '
                       f'fill="{accent}" fill-opacity="{0.20 + r * 0.07:.2f}"/>')
    return "\n".join(out)


def view1(name, code, accent, light):
    """Front-of-room view: presentation screen, bench/table, seating rows."""
    return header(accent, light) + f'''
  <rect x="0" y="300" width="{W}" height="{H-300}" fill="{accent}" fill-opacity=".07"/>
  <rect x="60" y="52" width="330" height="180" rx="4" fill="#ffffff" stroke="{accent}" stroke-opacity=".35"/>
  <rect x="72" y="64" width="306" height="156" rx="2" fill="url(#hatch)"/>
  <text x="225" y="150" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif"
        font-size="13" fill="{accent}" fill-opacity=".55">PRESENTATION SCREEN</text>
  <rect x="440" y="90" width="300" height="14" rx="3" fill="{accent}" fill-opacity=".30"/>
  <rect x="470" y="104" width="240" height="120" rx="3" fill="{accent}" fill-opacity=".14"/>
  <text x="590" y="172" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif"
        font-size="12" fill="{accent}" fill-opacity=".55">FRONT BENCH</text>
  <rect x="60" y="252" width="680" height="6" rx="3" fill="{accent}" fill-opacity=".22"/>
{seats(70, 278, 11, 3, 62, 34, 4, accent)}
''' + watermark(name, code, 1, accent)


def view2(name, code, accent, light):
    """Seating layout, viewed from the rear of the room."""
    return header(accent, light) + f'''
  <rect x="0" y="0" width="{W}" height="150" fill="{accent}" fill-opacity=".05"/>
  <rect x="250" y="34" width="300" height="86" rx="4" fill="#ffffff" stroke="{accent}" stroke-opacity=".3"/>
  <rect x="262" y="46" width="276" height="62" fill="url(#hatch)"/>
{seats(60, 176, 10, 5, 68, 44, 3, accent)}
  <circle cx="700" cy="60" r="20" fill="{accent}" fill-opacity=".16"/>
  <rect x="686" y="80" width="28" height="60" rx="4" fill="{accent}" fill-opacity=".12"/>
  <text x="700" y="160" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif"
        font-size="11" fill="{accent}" fill-opacity=".5">LECTERN</text>
''' + watermark(name, code, 2, accent)


def view3(name, code, accent, light):
    """Facilities detail: projector, whiteboard, network and climate control."""
    tiles = [
        (60, 90, "PROJECTOR"),
        (270, 90, "WHITEBOARD"),
        (480, 90, "AIR CONDITIONING"),
        (60, 220, "INTERNET ACCESS"),
        (270, 220, "SOUND SYSTEM"),
        (480, 220, "POWER OUTLETS"),
    ]
    body = []
    for x, y, label in tiles:
        body.append(f'''  <rect x="{x}" y="{y}" width="260" height="110" rx="5" fill="#ffffff"
        stroke="{accent}" stroke-opacity=".25"/>
  <rect x="{x+18}" y="{y+20}" width="44" height="44" rx="6" fill="{accent}" fill-opacity=".16"/>
  <text x="{x+18}" y="{y+90}" font-family="Segoe UI, Arial, sans-serif" font-size="12"
        fill="{accent}" fill-opacity=".7" letter-spacing="1">{label}</text>''')
    return header(accent, light) + f'''
  <text x="60" y="56" font-family="Georgia, serif" font-size="20" fill="{accent}">Facilities</text>
''' + "\n".join(body) + watermark(name, code, 3, accent)


def view4(name, code, accent, light):
    """Entrance and signage plate."""
    return header(accent, light) + f'''
  <rect x="0" y="330" width="{W}" height="{H-330}" fill="{accent}" fill-opacity=".08"/>
  <rect x="120" y="60" width="230" height="330" rx="4" fill="#ffffff" stroke="{accent}" stroke-opacity=".35"/>
  <rect x="140" y="80" width="190" height="120" rx="3" fill="url(#hatch)"/>
  <circle cx="318" cy="240" r="7" fill="{accent}" fill-opacity=".45"/>
  <rect x="430" y="110" width="280" height="150" rx="5" fill="#ffffff" stroke="{accent}" stroke-opacity=".3"/>
  <rect x="430" y="110" width="280" height="10" rx="5" fill="{accent}" fill-opacity=".5"/>
  <text x="570" y="180" text-anchor="middle" font-family="Georgia, serif" font-size="20" fill="{accent}">{name}</text>
  <text x="570" y="208" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" font-size="13"
        fill="{accent}" fill-opacity=".65">{code}</text>
  <text x="570" y="236" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" font-size="11"
        fill="{accent}" fill-opacity=".5" letter-spacing="1.5">AHMAD IBRAHIM KULLIYYAH OF LAWS</text>
''' + watermark(name, code, 4, accent)


# ---------------------------------------------------------------------------
# Vehicles. Cars only in the first release, matching the confirmed scope.
# Slugs must not end in a digit - variants are suffixed -v2, -v3, -v4.
# ---------------------------------------------------------------------------

# slug, display name, resource code, registration, accent colour
VEHICLES = [
    ("car-saga",   "Kulliyyah Car 1", "AIKOL-CAR-01", "WXY 1234", "#1f4e79"),
    ("car-bezza",  "Kulliyyah Car 2", "AIKOL-CAR-02", "WXY 5678", "#2f6b63"),
    ("car-innova", "Kulliyyah MPV",   "AIKOL-CAR-03", "WXY 9012", "#0e4732"),
    ("car-exora",  "Kulliyyah Car 3", "AIKOL-CAR-04", "WXY 3456", "#6b5a2e"),
]


def car_body(accent, x, w, ground, mpv):
    """A plainly diagrammatic side profile, sitting on the ground line.

    Geometry is measured upward from `ground` so the wheels always touch it,
    whatever roof height the body uses.
    """
    roof = 96 if mpv else 78
    wheel_r = 34
    wheel_cy = ground - wheel_r
    body_h = 86
    body_y = wheel_cy - body_h
    roof_y = body_y - roof
    cx = x + w * 0.18
    cw = w * (0.62 if mpv else 0.52)
    return f"""  <rect x="{x}" y="{body_y}" width="{w}" height="{body_h}" rx="26"
        fill="{accent}" fill-opacity=".22" stroke="{accent}" stroke-opacity=".45"/>
  <path d="M {cx:.0f} {body_y} q {cw * 0.14:.0f} -{roof} {cw * 0.5:.0f} -{roof}
           q {cw * 0.42:.0f} 0 {cw * 0.5:.0f} {roof} Z"
        fill="{accent}" fill-opacity=".16" stroke="{accent}" stroke-opacity=".4"/>
  <rect x="{cx + cw * 0.10:.0f}" y="{roof_y + 18}" width="{cw * 0.34:.0f}" height="{roof - 28:.0f}" rx="5"
        fill="#ffffff" fill-opacity=".55"/>
  <rect x="{cx + cw * 0.52:.0f}" y="{roof_y + 18}" width="{cw * 0.32:.0f}" height="{roof - 28:.0f}" rx="5"
        fill="#ffffff" fill-opacity=".55"/>
  <circle cx="{x + w * 0.22:.0f}" cy="{wheel_cy}" r="{wheel_r}" fill="#ffffff"
        stroke="{accent}" stroke-opacity=".5" stroke-width="3"/>
  <circle cx="{x + w * 0.22:.0f}" cy="{wheel_cy}" r="14" fill="{accent}" fill-opacity=".3"/>
  <circle cx="{x + w * 0.79:.0f}" cy="{wheel_cy}" r="{wheel_r}" fill="#ffffff"
        stroke="{accent}" stroke-opacity=".5" stroke-width="3"/>
  <circle cx="{x + w * 0.79:.0f}" cy="{wheel_cy}" r="14" fill="{accent}" fill-opacity=".3"/>"""


def vview1(name, code, reg, accent, light, mpv):
    """Side profile."""
    return header(accent, light) + f"""
  <rect x="0" y="322" width="{W}" height="{H-322}" fill="{accent}" fill-opacity=".07"/>
  <line x1="0" y1="322" x2="{W}" y2="322" stroke="{accent}" stroke-opacity=".25" stroke-width="2"/>
{car_body(accent, 110, 580, 322, mpv)}
  <text x="{W//2}" y="66" text-anchor="middle" font-family="Georgia, serif" font-size="21"
        fill="{accent}">{name}</text>
  <text x="{W//2}" y="376" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif"
        font-size="12" fill="{accent}" fill-opacity=".55" letter-spacing="1.5">SIDE PROFILE - NOT AN ACTUAL VEHICLE</text>
""" + watermark(name, code, 1, accent)


def vview2(name, code, reg, accent, light, mpv):
    """Registration plate and road-legal documentation panel."""
    return header(accent, light) + f"""
  <rect x="150" y="86" width="500" height="140" rx="10" fill="#ffffff"
        stroke="{accent}" stroke-opacity=".45" stroke-width="3"/>
  <text x="400" y="180" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif"
        font-size="58" font-weight="bold" letter-spacing="6" fill="{accent}" fill-opacity=".8">{reg}</text>
  <rect x="150" y="256" width="240" height="110" rx="6" fill="#ffffff" stroke="{accent}" stroke-opacity=".25"/>
  <text x="170" y="288" font-family="Segoe UI, Arial, sans-serif" font-size="11"
        fill="{accent}" fill-opacity=".6" letter-spacing="1">ROAD TAX</text>
  <rect x="170" y="300" width="200" height="10" rx="5" fill="{accent}" fill-opacity=".18"/>
  <rect x="170" y="320" width="140" height="10" rx="5" fill="{accent}" fill-opacity=".18"/>
  <rect x="410" y="256" width="240" height="110" rx="6" fill="#ffffff" stroke="{accent}" stroke-opacity=".25"/>
  <text x="430" y="288" font-family="Segoe UI, Arial, sans-serif" font-size="11"
        fill="{accent}" fill-opacity=".6" letter-spacing="1">INSURANCE</text>
  <rect x="430" y="300" width="200" height="10" rx="5" fill="{accent}" fill-opacity=".18"/>
  <rect x="430" y="320" width="160" height="10" rx="5" fill="{accent}" fill-opacity=".18"/>
  <text x="400" y="62" text-anchor="middle" font-family="Georgia, serif" font-size="19"
        fill="{accent}">{name} - {code}</text>
""" + watermark(name, code, 2, accent)


def vview3(name, code, reg, accent, light, mpv):
    """Vehicle features, mirroring the venue facilities view."""
    tiles = [
        (60, 90, "AIR CONDITIONING"),
        (270, 90, "GPS NAVIGATION"),
        (480, 90, "DASHCAM"),
        (60, 220, "SEAT BELTS"),
        (270, 220, "SPARE TYRE"),
        (480, 220, "FIRST AID KIT"),
    ]
    body = []
    for x, y, label in tiles:
        body.append(f"""  <rect x="{x}" y="{y}" width="260" height="110" rx="5" fill="#ffffff"
        stroke="{accent}" stroke-opacity=".25"/>
  <rect x="{x+18}" y="{y+20}" width="44" height="44" rx="6" fill="{accent}" fill-opacity=".16"/>
  <text x="{x+18}" y="{y+90}" font-family="Segoe UI, Arial, sans-serif" font-size="12"
        fill="{accent}" fill-opacity=".7" letter-spacing="1">{label}</text>""")
    return header(accent, light) + f"""
  <text x="60" y="56" font-family="Georgia, serif" font-size="20" fill="{accent}">Vehicle features</text>
""" + "\n".join(body) + watermark(name, code, 3, accent)


def vview4(name, code, reg, accent, light, mpv):
    """Interior seating plan - how many people the vehicle actually carries."""
    rows = 3 if mpv else 2
    seats_svg = []
    for r in range(rows):
        per = 2 if r == 0 else 3
        for c in range(per):
            x = 360 + c * 78 - (per - 1) * 39
            y = 120 + r * 88
            seats_svg.append(
                f"""  <rect x="{x}" y="{y}" width="62" height="64" rx="10" fill="{accent}" fill-opacity=".16"
        stroke="{accent}" stroke-opacity=".4"/>
  <rect x="{x+8}" y="{y+8}" width="46" height="24" rx="6" fill="{accent}" fill-opacity=".22"/>""")
    total = 7 if mpv else 5
    return header(accent, light) + f"""
  <text x="60" y="56" font-family="Georgia, serif" font-size="20" fill="{accent}">Seating layout</text>
  <rect x="272" y="86" width="300" height="{110 + rows * 88}" rx="18" fill="none"
        stroke="{accent}" stroke-opacity=".3" stroke-width="2"/>
  <text x="60" y="150" font-family="Segoe UI, Arial, sans-serif" font-size="13"
        fill="{accent}" fill-opacity=".65">DRIVER + {total - 1} PASSENGERS</text>
  <text x="60" y="176" font-family="Segoe UI, Arial, sans-serif" font-size="11"
        fill="{accent}" fill-opacity=".5">The requester drives.</text>
""" + "\n".join(seats_svg) + watermark(name, code, 4, accent)


# ---------------------------------------------------------------------------
# The Kulliyyah building, shown behind the pointed arch on the landing screen.
# Flat and diagrammatic on purpose — it must never be mistaken for a photograph
# of the real building. Replace with the Kulliyyah's own photograph.
# ---------------------------------------------------------------------------

BW, BH = 900, 400
B_ACCENT = "#14675b"
B_GOLD = "#d99b28"


def _arcade():
    """A row of five pointed arches across the facade."""
    out = []
    for i in range(5):
        x = 150 + i * 122
        out.append(
            '  <path d="M %d 330 L %d 250 Q %d 205 %d 200 Q %d 205 %d 250 L %d 330 Z" '
            'fill="#f2efe6" stroke="%s" stroke-opacity=".38" stroke-width="1.6"/>'
            % (x, x, x, x + 44, x + 88, x + 88, x + 88, B_ACCENT))
        out.append(
            '  <path d="M %d 330 L %d 256 Q %d 222 %d 218 Q %d 222 %d 256 L %d 330 Z" '
            'fill="%s" fill-opacity=".13"/>'
            % (x + 16, x + 16, x + 16, x + 44, x + 72, x + 72, x + 72, B_ACCENT))
    return "\n".join(out)


def _palms():
    """Two palms, because they are the first thing you see on that approach."""
    import math
    out = []
    for px, scale in ((78, 1.0), (836, 0.86)):
        out.append('  <rect x="%d" y="150" width="8" height="185" fill="%s" fill-opacity=".42"/>'
                   % (px - 4, B_ACCENT))
        for ang in (-64, -34, -6, 22, 52):
            r = math.radians(ang)
            ex = px + math.cos(r) * 66 * scale
            ey = 150 - math.sin(r) * 46 * scale
            out.append(
                '  <path d="M %d 150 Q %d %d %d %d" fill="none" stroke="%s" '
                'stroke-opacity=".5" stroke-width="3" stroke-linecap="round"/>'
                % (px, (px + ex) / 2, (150 + ey) / 2 - 20, ex, ey, B_ACCENT))
    return "\n".join(out)


def building_view():
    """The whole scene: sky, facade, gable with a khatam, arcade, palms."""
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" '
        'width="%d" height="%d" role="img">\n'
        '  <defs>\n'
        '    <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">\n'
        '      <stop offset="0" stop-color="#dcebf4"/>\n'
        '      <stop offset="1" stop-color="#f4f1e7"/>\n'
        '    </linearGradient>\n'
        '  </defs>\n'
        '  <rect width="%d" height="%d" fill="url(#sky)"/>\n'
        '  <rect x="110" y="150" width="680" height="185" fill="#faf7ee" '
        'stroke="%s" stroke-opacity=".3"/>\n'
        '  <path d="M 330 150 L 450 96 L 570 150 Z" fill="#faf7ee" '
        'stroke="%s" stroke-opacity=".34" stroke-width="1.6"/>\n'
        '  <circle cx="450" cy="136" r="9" fill="none" stroke="%s" stroke-width="2"/>\n'
        '  <polygon points="450,127 459,136 450,145 441,136" fill="%s" fill-opacity=".8"/>\n'
        '%s\n%s\n'
        '  <rect x="0" y="335" width="%d" height="65" fill="%s" fill-opacity=".09"/>\n'
        '  <rect x="0" y="%d" width="%d" height="34" fill="%s" fill-opacity=".92"/>\n'
        '  <text x="20" y="%d" font-family="Georgia, serif" font-size="15" '
        'fill="#ffffff">Ahmad Ibrahim Kulliyyah of Laws</text>\n'
        '  <text x="%d" y="%d" text-anchor="end" font-family="Segoe UI, Arial, sans-serif" '
        'font-size="10.5" fill="#ffffff" fill-opacity=".85" letter-spacing="1.4">'
        'PLACEHOLDER IMAGE</text>\n'
        '</svg>\n'
        % (BW, BH, BW, BH, BW, BH, B_ACCENT, B_ACCENT, B_GOLD, B_GOLD,
           _arcade(), _palms(), BW, B_ACCENT, BH - 34, BW, B_ACCENT,
           BH - 12, BW - 20, BH - 12))


def tint(hexcolor, amount=0.92):
    """Lighten a hex colour towards white for the wall gradient."""
    r = int(hexcolor[1:3], 16); g = int(hexcolor[3:5], 16); b = int(hexcolor[5:7], 16)
    f = lambda c: int(c + (255 - c) * amount)
    return "#%02x%02x%02x" % (f(r), f(g), f(b))


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    written = 0

    venue_views = [view1, view2, view3, view4]
    for slug, name, code, accent in VENUES:
        light = tint(accent)
        for i, fn in enumerate(venue_views, start=1):
            # "-v2" style suffixes keep variant names unambiguous for slugs that
            # already end in a letter/number (e.g. seminar-a, seminar-b).
            suffix = "" if i == 1 else "-v%d" % i
            path = os.path.join(OUT_DIR, "%s%s.svg" % (slug, suffix))
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(fn(name, code, accent, light))
            written += 1

    vehicle_views = [vview1, vview2, vview3, vview4]
    for slug, name, code, reg, accent in VEHICLES:
        light = tint(accent)
        mpv = ("innova" in slug) or ("exora" in slug)
        for i, fn in enumerate(vehicle_views, start=1):
            suffix = "" if i == 1 else "-v%d" % i
            path = os.path.join(OUT_DIR, "%s%s.svg" % (slug, suffix))
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(fn(name, code, reg, accent, light, mpv))
            written += 1

    with open(os.path.join(OUT_DIR, "aikol-building.svg"), "w", encoding="utf-8") as fh:
        fh.write(building_view())
    written += 1

    print("Wrote %d placeholder images to %s" % (written, OUT_DIR))


if __name__ == "__main__":
    main()
