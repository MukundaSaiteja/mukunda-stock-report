"""Draw the small Kronos prediction section (section 11) at the end of the research PDF."""

from __future__ import annotations

from outlook import text

W = (22, 30, 50, 34, 54)  # column widths as a share of the page


def draw(pdf, result, san, palette) -> None:
    navy, grey, lgrey, white, teal = palette
    epw = pdf.w - 2 * pdf.l_margin

    def para(t, size=7.6, style="", color=None):
        pdf.set_x(pdf.l_margin); pdf.set_font("Helvetica", style, size)
        pdf.set_text_color(*(color or (0, 0, 0))); pdf.multi_cell(epw, 4.0, san(t)); pdf.set_text_color(0, 0, 0)

    o = getattr(result, "outlook", None)
    if pdf.get_y() > pdf.h - 55:
        pdf.add_page()
    pdf.ln(1); pdf.set_x(pdf.l_margin); pdf.set_font("Helvetica", "B", 10); pdf.set_text_color(*teal)
    pdf.multi_cell(epw, 5, san(text.TITLE)); pdf.set_text_color(0, 0, 0)
    if o is None:
        para(f"Kronos prediction unavailable this run: {getattr(result, 'note', '') or 'no result'}.", 8, "I", grey)
        return
    para(text.subtitle(o), 7.8, color=grey)
    pdf.ln(0.8)
    total = sum(W)
    for i, row in enumerate(text.table_rows(o)):
        pdf.set_x(pdf.l_margin)
        pdf.set_fill_color(*(navy if i == 0 else (lgrey if i % 2 == 0 else white)))
        pdf.set_text_color(*(white if i == 0 else (0, 0, 0)))
        pdf.set_font("Helvetica", "B" if i == 0 else "", 7.8)
        for w, cell in zip(W, row):
            pdf.cell(epw * w / total, 5.2, san(cell), fill=True)
        pdf.ln(5.2)
    pdf.set_text_color(0, 0, 0)
    for line in text.notes(o):
        para(line)
