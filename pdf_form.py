"""ReportLab generator for the ZURITT motor repair `BON DE TRAVAIL` form.

The layout is hand-tuned to reproduce the printed paper form: same boxes,
same red label colour, same french text. The only thing that changes between
PDFs is the typed-in values that come from the nameplate photo and the
operator's manual entries.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from reportlab.lib.colors import Color, black
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

# Same dark red as the printed labels.
LABEL = Color(0.55, 0.10, 0.13)
LINE = Color(0.65, 0.20, 0.22)

PAGE_W, PAGE_H = letter  # 612 x 792
M = 22  # outer margin

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class FormData:
    # Header
    bon_de_travail: str = ""           # e.g. "A 31703"
    date_j: str = ""
    date_m: str = ""
    date_a: str = ""
    autorise_par: str = ""

    # Identification block
    client: str = ""
    req: str = ""
    po: str = ""
    marque: str = ""
    hp: str = ""
    rpm: str = ""
    volts: str = ""
    cy: str = ""
    phase: str = ""
    amps: str = ""
    bati: str = ""
    modele: str = ""
    type: str = ""
    serie: str = ""
    spec: str = ""
    special: str = ""
    tag: str = ""

    # Enclosure checkbox (one of: TEFC, DP, WPI, WPII)
    enclosure: str = ""

    # Work-type checkboxes (set of strings matching CHECKBOX_WORK keys)
    work_types: set = field(default_factory=set)

    # Free notes
    exigence: str = ""
    pieces: str = ""

    # Header strip (left blank by default; intake operator fills later)
    piece_le: str = ""
    retour_bureau_le: str = ""
    soumission_donnee_le: str = ""
    recu_ok_client_le: str = ""
    ok_donne_usine_le: str = ""
    date_retour: str = ""


# work-type checkbox labels in the order they appear, in two rows
CHECKBOX_WORK_ROW1 = [
    ("STATOR", "stator"),
    ("STATOR/POMPE", "stator_pompe"),
    ("STATOR/MOTEUR", "stator_moteur"),
    ("ROTOR", "rotor"),
    ("POMPE", "pompe"),
    ("MOTEUR", "moteur"),
    ("SYNCH.", "synch"),
    ("ROTOR BOBINE", "rotor_bobine"),
]
CHECKBOX_WORK_ROW2 = [
    ("DRIVE", "drive"),
    ("SOUDEUSE", "soudeuse"),
    ("APPEL DE SERVICE", "appel_service"),
    ("ECHANT. HUILE", "echant_huile"),
    ("AUTRE", "autre_work"),
]

ENCLOSURES = ["TEFC", "DP", "WPI", "WPII"]


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------


def _box(c: canvas.Canvas, x: float, y: float, w: float, h: float) -> None:
    c.setStrokeColor(LINE)
    c.setLineWidth(0.6)
    c.rect(x, y, w, h, stroke=1, fill=0)


def _label(c: canvas.Canvas, x: float, y: float, text: str, size: float = 6.5) -> None:
    c.setFillColor(LABEL)
    c.setFont("Helvetica-Bold", size)
    c.drawString(x, y, text)


def _value(c: canvas.Canvas, x: float, y: float, text: str, size: float = 9) -> None:
    if not text:
        return
    c.setFillColor(black)
    c.setFont("Helvetica", size)
    c.drawString(x, y, text)


def _underline(c: canvas.Canvas, x: float, y: float, w: float) -> None:
    c.setStrokeColor(LINE)
    c.setLineWidth(0.4)
    c.line(x, y, x + w, y)


def _checkbox(c: canvas.Canvas, x: float, y: float, checked: bool, size: float = 7) -> None:
    c.setStrokeColor(LINE)
    c.setLineWidth(0.6)
    c.rect(x, y, size, size, stroke=1, fill=0)
    if checked:
        c.setFillColor(black)
        c.setFont("Helvetica-Bold", size + 2)
        c.drawString(x + 0.8, y + 0.6, "X")


# ---------------------------------------------------------------------------
# Section drawers
# ---------------------------------------------------------------------------


def _draw_top_strip(c: canvas.Canvas, top: float, data: FormData) -> float:
    """Draws the two thin strips at the very top of the form.

    Returns the y coordinate of the bottom edge of the strip.
    """
    h = 12
    w = PAGE_W - 2 * M
    # row 1
    y1 = top - h
    _box(c, M, y1, w, h)
    col = w / 3
    _label(c, M + 3, y1 + h - 7, "PIECE LE :")
    _label(c, M + col + 3, y1 + h - 7, "SOUMISSION DONNEE AU CLIENT LE :")
    _label(c, M + 2 * col + 3, y1 + h - 7, "OK DONNE A L'USINE LE :")
    # vertical dividers
    c.line(M + col, y1, M + col, y1 + h)
    c.line(M + 2 * col, y1, M + 2 * col, y1 + h)
    _value(c, M + 55, y1 + 2, data.piece_le, 8)
    _value(c, M + col + 140, y1 + 2, data.soumission_donnee_le, 8)
    _value(c, M + 2 * col + 105, y1 + 2, data.ok_donne_usine_le, 8)

    # row 2
    y2 = y1 - h
    _box(c, M, y2, w, h)
    _label(c, M + 3, y2 + h - 7, "RETOUR AU BUREAU LE :")
    _label(c, M + col + 3, y2 + h - 7, "RECU LE OK DU CLIENT LE :")
    _label(c, M + 2 * col + 3, y2 + h - 7, "DATE DE RETOUR :")
    c.line(M + col, y2, M + col, y2 + h)
    c.line(M + 2 * col, y2, M + 2 * col, y2 + h)
    _value(c, M + 95, y2 + 2, data.retour_bureau_le, 8)
    _value(c, M + col + 105, y2 + 2, data.recu_ok_client_le, 8)
    _value(c, M + 2 * col + 75, y2 + 2, data.date_retour, 8)
    return y2


def _draw_header(c: canvas.Canvas, top: float, data: FormData) -> float:
    """Logo, date box, authorize line, bon de travail number."""
    band_h = 54
    y = top - band_h
    # ZURITT logo placeholder (circle + text)
    cx, cy = M + 28, y + band_h / 2
    c.setStrokeColor(LABEL)
    c.setLineWidth(1.2)
    c.circle(cx, cy, 17, stroke=1, fill=0)
    c.setFillColor(LABEL)
    c.setFont("Helvetica-Bold", 11)
    c.drawCentredString(cx, cy - 3.5, "ZURITT")
    # subtle globe meridian
    c.setLineWidth(0.4)
    c.line(cx - 17, cy, cx + 17, cy)
    c.ellipse(cx - 6, cy - 17, cx + 6, cy + 17, stroke=1, fill=0)

    # DATE box
    date_x = M + 70
    date_y = y + 18
    date_w, date_h = 110, 22
    _box(c, date_x, date_y, date_w, date_h)
    _label(c, date_x - 32, date_y + date_h - 12, "DATE :", 8)
    col_w = date_w / 3
    c.line(date_x + col_w, date_y, date_x + col_w, date_y + date_h)
    c.line(date_x + 2 * col_w, date_y, date_x + 2 * col_w, date_y + date_h)
    _label(c, date_x + col_w / 2 - 2, date_y - 8, "J", 7)
    _label(c, date_x + col_w + col_w / 2 - 3, date_y - 8, "M", 7)
    _label(c, date_x + 2 * col_w + col_w / 2 - 2, date_y - 8, "A", 7)
    _value(c, date_x + 8, date_y + 6, data.date_j, 11)
    _value(c, date_x + col_w + 8, date_y + 6, data.date_m, 11)
    _value(c, date_x + 2 * col_w + 8, date_y + 6, data.date_a, 11)

    # AUTORISE PAR underline
    auth_x = date_x + date_w + 20
    auth_y = date_y + 4
    auth_w = 220
    _underline(c, auth_x, auth_y, auth_w)
    _label(c, auth_x + auth_w - 70, auth_y - 8, "AUTORISE PAR", 7)
    _value(c, auth_x + 4, auth_y + 2, data.autorise_par, 9)

    # Circle stamp area (empty oval right of authorise)
    stamp_cx = auth_x + auth_w + 22
    stamp_cy = y + band_h / 2 + 2
    c.setStrokeColor(LINE)
    c.setLineWidth(0.6)
    c.circle(stamp_cx, stamp_cy, 14, stroke=1, fill=0)

    # N° BON DE TRAVAIL
    bdtv_x = PAGE_W - M - 130
    _label(c, bdtv_x, y + 28, "N°", 12)
    _label(c, bdtv_x + 14, y + 28, "BON DE TRAVAIL", 9)
    c.setFillColor(LABEL)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(bdtv_x + 6, y + 6, data.bon_de_travail or "")

    return y


def _draw_id_block(c: canvas.Canvas, top: float, data: FormData) -> float:
    """6 rows of underlined fields (CLIENT, MARQUE, AMPS, TYPE, SPECIAL)."""
    row_h = 16
    rows = 6
    block_h = row_h * rows
    y_bottom = top - block_h
    w = PAGE_W - 2 * M
    _box(c, M, y_bottom, w, block_h)

    def field(row: int, x: float, label: str, w: float, value: str, label_size: float = 7) -> None:
        y = top - row * row_h
        _label(c, x, y - 9, label, label_size)
        lw = c.stringWidth(label, "Helvetica-Bold", label_size)
        ux = x + lw + 4
        uw = w - (lw + 4)
        _underline(c, ux, y - 11, uw)
        _value(c, ux + 2, y - 9, value, 10)

    # Row 1: CLIENT (wide) | REQ | PO
    field(1, M + 4, "CLIENT", 280, data.client)
    field(1, M + 300, "REQ", 130, data.req)
    field(1, M + 440, "PO", 120, data.po)
    # Row 2: MARQUE | HP/KW/KVA | RPM | VOLTS/CY/PHASE
    field(2, M + 4, "MARQUE", 180, data.marque)
    field(2, M + 200, "HP / KW / KVA", 120, data.hp)
    field(2, M + 335, "RPM", 90, data.rpm)
    volts_combined = "/".join(v for v in [data.volts, data.cy, data.phase] if v)
    field(2, M + 435, "VOLTS / CY / PHASE", 125, volts_combined)
    # Row 3: AMPS | BATI | MODELE | enclosure checkboxes
    field(3, M + 4, "AMPS", 90, data.amps)
    field(3, M + 110, "BATI", 90, data.bati)
    field(3, M + 215, "MODELE", 200, data.modele)
    # enclosure checkboxes
    encx = M + 425
    ency = top - 3 * row_h - 9
    for i, name in enumerate(ENCLOSURES):
        cx = encx + i * 35
        _checkbox(c, cx, ency + 2, data.enclosure.upper() == name)
        _label(c, cx + 9, ency + 4, name, 6.5)
    # Row 4: TYPE | SERIE | SPEC
    field(4, M + 4, "TYPE", 200, data.type)
    field(4, M + 220, "SERIE", 220, data.serie)
    field(4, M + 460, "SPEC", 100, data.spec)
    # Row 5: SPECIAL (full width) | TAG (right)
    field(5, M + 4, "SPECIAL", 380, data.special)
    field(5, M + 415, "TAG", 145, data.tag)
    # Row 6 left blank intentionally - this is the separator before checkboxes
    return y_bottom


def _draw_work_checkboxes(c: canvas.Canvas, top: float, data: FormData) -> float:
    """Two rows of work-type checkboxes."""
    row_h = 14
    block_h = row_h * 2
    y_bottom = top - block_h
    w = PAGE_W - 2 * M
    _box(c, M, y_bottom, w, block_h)

    def draw_row(items: list[tuple[str, str]], y: float) -> None:
        col = w / len(items)
        for i, (label, key) in enumerate(items):
            x = M + i * col + 2
            _checkbox(c, x, y - 9, key in data.work_types)
            _label(c, x + 10, y - 8, label, 6.5)

    draw_row(CHECKBOX_WORK_ROW1, top - 2)
    draw_row(CHECKBOX_WORK_ROW2, top - 2 - row_h)
    return y_bottom


def _draw_hours_grid(c: canvas.Canvas, top: float) -> float:
    """4-column grid of work codes with HR underlines plus checkbox column."""
    rows = [
        ("ESTIME", "LAMINATION", "MACHINAGE ARBRE", "LAVER SECHER", "EQUILIBRAGE"),
        ("NETTOYAGE", "ASSEMBLAGE", "COUV.D.E", "TREMPAGE", "RESTACK"),
        ("MECANIQUE", "PEINTURE", "COUV.N.D.E", "EPOXY", "DEBOSSELAGE"),
        ("JET SABLE", "AUTRE", "SOUDURE", "ZEP", "BOBINAGE"),
    ]
    row_h = 13
    block_h = row_h * len(rows)
    y_bottom = top - block_h
    w = PAGE_W - 2 * M
    _box(c, M, y_bottom, w, block_h)
    col_w = w / 5

    for r, row in enumerate(rows):
        y = top - (r + 1) * row_h + 3
        for cidx, label in enumerate(row):
            x = M + cidx * col_w + 3
            _label(c, x, y, label, 6.5)
            if cidx < 4:
                # HR field
                _underline(c, x + 50, y - 1, 30)
                _label(c, x + 82, y, "HR", 6)
            else:
                # rightmost column has a checkbox to the right of label
                _checkbox(c, x + col_w - 14, y - 2, False)
    return y_bottom


def _draw_pieces_box(c: canvas.Canvas, top: float, data: FormData) -> float:
    h = 80
    y_bottom = top - h
    w = PAGE_W - 2 * M
    _box(c, M, y_bottom, w, h)
    _label(c, M + 4, top - 10, "PIECES :", 7)
    if data.pieces:
        text = c.beginText(M + 4, top - 22)
        text.setFillColor(black)
        text.setFont("Helvetica", 9)
        for line in data.pieces.splitlines():
            text.textLine(line)
        c.drawText(text)
    return y_bottom


def _draw_exigence(c: canvas.Canvas, top: float, data: FormData) -> float:
    h = 24
    y_bottom = top - h
    w = PAGE_W - 2 * M
    _box(c, M, y_bottom, w, h)
    _label(c, M + 4, top - 10, "EXIGENCE DU CLIENT :", 7)
    _value(c, M + 130, top - 14, data.exigence, 10)
    return y_bottom


def _draw_branchement(c: canvas.Canvas, top: float) -> float:
    h = 16
    y_bottom = top - h
    w = PAGE_W - 2 * M
    _box(c, M, y_bottom, w, h)
    col = w / 4
    headings = ["FIL DE BRANCHEMENT :", "GROSSEUR :", "NOMBRE :", "LONGUEUR :"]
    for i, lab in enumerate(headings):
        x = M + i * col
        if i > 0:
            c.line(x, y_bottom, x, y_bottom + h)
        _label(c, x + 4, y_bottom + 4, lab, 6.5)
    return y_bottom


def _draw_coils_grid(c: canvas.Canvas, top: float) -> float:
    """Two-row coils data grid."""
    row_h = 16
    block_h = row_h * 2
    y_bottom = top - block_h
    w = PAGE_W - 2 * M
    _box(c, M, y_bottom, w, block_h)
    c.line(M, top - row_h, M + w, top - row_h)

    # Row 1 columns (8): STATOR(R/B) | PROTECTION | COUR.D.E | COUR.N.D.E | CORE LOSS TEST | AUTRE | LB FIL | PITCH OF COILS
    cols1 = [
        ("STATOR", 70),
        ("PROTECTION", 65),
        ("COUR. D.E", 60),
        ("COUR. N.D.E", 60),
        ("CORE LOSS TEST", 120),
        ("AUTRE", 50),
        ("LB FIL", 50),
        ("PITCH OF COILS", 80),
    ]
    x = M
    for label, cw in cols1:
        if x > M:
            c.line(x, y_bottom, x, top)
        _label(c, x + 3, top - 9, label, 6.5)
        x += cw

    # STATOR R/B checkboxes
    _label(c, M + 5, top - 18, "R", 6)
    _checkbox(c, M + 14, top - 22, False, 6)
    _label(c, M + 28, top - 18, "B", 6)
    _checkbox(c, M + 37, top - 22, False, 6)

    # CORE LOSS TEST sub-cells (W/V/R) inside
    clt_x = M + 70 + 65 + 60 + 60
    sub = 120 / 3
    for i, lab in enumerate(["W :", "V :", "R :"]):
        sx = clt_x + i * sub
        _label(c, sx + 3, top - 18, lab, 6.5)

    # Row 2 columns
    cols2 = [
        ("N° OF COILS", 70),
        ("N° OF SLOTS", 65),
        ("CONNECTION", 60),
        ("SIZE WIRE", 60),
        ("N° OF TURNS", 120),
        ("N° OF GROUPS", 50),
        ("COILS/GROUP", 50),
        ("N° OF POLES", 80),
    ]
    x = M
    y = y_bottom
    for label, cw in cols2:
        if x > M:
            c.line(x, y, x, y + row_h)
        _label(c, x + 3, y + row_h - 9, label, 6.5)
        x += cw

    # CORE LOSS extra labels under first row (DIA, PWL, A/Ti, OK) on its lower half - drawn between rows
    return y_bottom


def _draw_test_blocks(c: canvas.Canvas, top: float) -> float:
    """Three side-by-side test boxes at the bottom."""
    h = 150
    y_bottom = top - h
    w = (PAGE_W - 2 * M)
    col1 = w * 0.32
    col2 = w * 0.38
    col3 = w - col1 - col2
    # outer boxes
    _box(c, M, y_bottom, col1, h)
    _box(c, M + col1, y_bottom, col2, h)
    _box(c, M + col1 + col2, y_bottom, col3, h)

    # red header bars
    def header(x: float, w: float, text: str) -> None:
        c.setFillColor(LABEL)
        c.rect(x, top - 18, w, 18, stroke=0, fill=1)
        c.setFillColor(Color(1, 1, 1))
        c.setFont("Helvetica-Bold", 10)
        c.drawCentredString(x + w / 2, top - 13, text)

    header(M, col1, "TEST A L'ARRIVEE")
    header(M + col1, col2, "TEST APRES ASSEMBLAGE")
    header(M + col1 + col2, col3, "AUTRE TEST")

    # Left box content
    left = M + 4
    yy = top - 30
    _label(c, left, yy, "Essai, comparaison", 6.5)
    _label(c, left, yy - 8, "electronique a :", 6.5)
    _underline(c, left + 80, yy - 8, 40)
    _label(c, left + 122, yy - 8, "Volts", 6.5)
    _label(c, left + 145, yy - 8, "CONFORME", 6)
    _label(c, left + 145, yy - 16, "OUI", 6); _checkbox(c, left + 160, yy - 18, False, 6)
    _label(c, left + 145, yy - 24, "NON", 6); _checkbox(c, left + 160, yy - 26, False, 6)

    yy -= 36
    _label(c, left, yy, "Essai Megger :", 6.5)
    _underline(c, left + 60, yy, 25)
    _label(c, left + 87, yy, "GΩ a", 6.5)
    _underline(c, left + 105, yy, 30)
    _label(c, left + 140, yy, "Volts", 6.5)

    yy -= 14
    _label(c, left, yy, "Essai sans charge :", 6.5)
    yy -= 12
    _label(c, left, yy, "PHASE 1", 6.5)
    _label(c, left + 50, yy, "PHASE 2", 6.5)
    _label(c, left + 100, yy, "PHASE 3", 6.5)
    yy -= 12
    _label(c, left, yy, "Volts :", 6); _underline(c, left + 20, yy, 25)
    _underline(c, left + 50, yy, 40); _underline(c, left + 100, yy, 40)
    yy -= 10
    _label(c, left, yy, "Amps :", 6); _underline(c, left + 20, yy, 25)
    _underline(c, left + 50, yy, 40); _underline(c, left + 100, yy, 40)
    yy -= 14
    _label(c, left, yy, "Autre :", 6.5); _underline(c, left + 25, yy, 110)
    yy -= 14
    _label(c, left, yy, "VERIFIE PAR :", 6.5); _underline(c, left + 60, yy, 70)

    # Middle box content
    mid = M + col1 + 4
    yy = top - 30
    _label(c, mid, yy, "Essai, comparaison", 6.5)
    _label(c, mid, yy - 8, "electronique a :", 6.5)
    _underline(c, mid + 80, yy - 8, 40)
    _label(c, mid + 122, yy - 8, "Volts", 6.5)
    _label(c, mid + 145, yy - 8, "CONFORME", 6)
    _label(c, mid + 145, yy - 16, "OUI", 6); _checkbox(c, mid + 160, yy - 18, False, 6)
    _label(c, mid + 145, yy - 24, "NON", 6); _checkbox(c, mid + 160, yy - 26, False, 6)
    _label(c, mid + 180, yy - 8, "Vibration", 6.5)
    _label(c, mid + 180, yy - 16, "D.E.", 6); _underline(c, mid + 195, yy - 16, 20)
    _label(c, mid + 218, yy - 16, "N.D.E.", 6); _underline(c, mid + 240, yy - 16, 20)
    _label(c, mid + 180, yy - 24, "Rotation anti-hor.", 6); _checkbox(c, mid + 240, yy - 26, False, 6); _label(c, mid + 250, yy - 24, "OK", 6)

    yy -= 36
    _label(c, mid, yy, "Essai Megger :", 6.5)
    _underline(c, mid + 60, yy, 30); _label(c, mid + 92, yy, "GΩ a", 6.5)
    _underline(c, mid + 110, yy, 30); _label(c, mid + 145, yy, "Volts", 6.5)

    yy -= 12
    _label(c, mid, yy, "Essai Hi-Pot :", 6.5)
    _underline(c, mid + 55, yy, 20); _label(c, mid + 77, yy, "V.", 6.5)
    _underline(c, mid + 95, yy, 30); _label(c, mid + 128, yy, "μA pour 1 min.", 6)

    yy -= 14
    _label(c, mid + 50, yy, "Champs", 6.5); _label(c, mid + 120, yy, "Arm", 6.5)
    yy -= 10
    _label(c, mid, yy, "Volts", 6.5); _underline(c, mid + 25, yy, 60); _underline(c, mid + 90, yy, 60)
    yy -= 10
    _label(c, mid, yy, "Amps", 6.5); _underline(c, mid + 25, yy, 60); _label(c, mid + 130, yy, "RPM", 6.5); _underline(c, mid + 155, yy, 35)
    yy -= 14
    _label(c, mid, yy, "PHASE 1", 6.5); _label(c, mid + 50, yy, "PHASE 2", 6.5); _label(c, mid + 100, yy, "PHASE 3", 6.5)
    yy -= 10
    _label(c, mid, yy, "Volts :", 6); _underline(c, mid + 25, yy, 25); _underline(c, mid + 55, yy, 40); _underline(c, mid + 100, yy, 40)
    yy -= 10
    _label(c, mid, yy, "Amps :", 6); _underline(c, mid + 25, yy, 25); _underline(c, mid + 55, yy, 40); _underline(c, mid + 100, yy, 40)
    yy -= 14
    _label(c, mid, yy, "VERIFIE PAR :", 6.5); _underline(c, mid + 60, yy, 110)

    # Right box content: blank free area + VERIFIE PAR at bottom
    right = M + col1 + col2 + 4
    _label(c, right, top - 30, "", 6.5)  # placeholder
    _label(c, right, y_bottom + 14, "VERIFIE PAR :", 6.5)
    _underline(c, right + 60, y_bottom + 14, col3 - 70)

    return y_bottom


def _draw_footer(c: canvas.Canvas, top: float) -> None:
    h = 14
    y_bottom = top - h
    w = PAGE_W - 2 * M
    _label(c, M + 4, y_bottom + 4, "VERIFIE EN USINE PAR :", 7)
    _label(c, M + w / 2 - 30, y_bottom + 4, "APP. PAR :", 7)
    _label(c, PAGE_W - M - 30, y_bottom + 4, "M 313", 6.5)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def render(data: FormData, output: str | Path) -> Path:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(output), pagesize=letter)
    y = PAGE_H - M
    y = _draw_top_strip(c, y, data)
    y = _draw_header(c, y, data)
    y = _draw_id_block(c, y, data)
    y = _draw_work_checkboxes(c, y, data)
    y = _draw_hours_grid(c, y)
    y = _draw_pieces_box(c, y, data)
    y = _draw_exigence(c, y, data)
    y = _draw_branchement(c, y)
    y = _draw_coils_grid(c, y)
    y = _draw_test_blocks(c, y)
    _draw_footer(c, y)
    c.showPage()
    c.save()
    return output


if __name__ == "__main__":
    sample = FormData(
        bon_de_travail="A 31703",
        date_j="04", date_m="05", date_a="26",
        client="Agnico Eagle Canadian Malartic",
        req="OR-937926-S",
        marque="WEG",
        hp="600", rpm="1787",
        volts="4000", cy="60", phase="3",
        amps="77.2", bati="5810/11/12T",
        modele="HV600404HGF5810",
        serie="1016380644",
        tag="CM-8258",
        special="avec la cle",
        enclosure="TEFC",
        work_types={"moteur"},
        exigence="Estimation",
    )
    out = render(sample, "out/sample.pdf")
    print(f"wrote {out}")
