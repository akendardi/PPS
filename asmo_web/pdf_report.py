from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Image,
    Table,
    TableStyle,
)


def _register_fonts():
    candidates_regular = [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]

    candidates_bold = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ]

    regular_path = None
    bold_path = None

    for path in candidates_regular:
        if Path(path).exists():
            regular_path = path
            break

    for path in candidates_bold:
        if Path(path).exists():
            bold_path = path
            break

    if not regular_path:
        raise RuntimeError("Не найден шрифт с поддержкой кириллицы для PDF.")

    pdfmetrics.registerFont(TTFont("AppRegular", regular_path))
    pdfmetrics.registerFont(TTFont("AppBold", bold_path or regular_path))


def _styles():
    base = getSampleStyleSheet()

    return {
        "title": ParagraphStyle(
            "title",
            parent=base["Title"],
            fontName="AppBold",
            fontSize=15,
            leading=17,
            alignment=1,
            spaceAfter=4,
        ),
        "subtitle": ParagraphStyle(
            "subtitle",
            parent=base["Normal"],
            fontName="AppRegular",
            fontSize=8.5,
            leading=10,
            alignment=1,
            textColor=colors.HexColor("#444444"),
        ),
        "card_title": ParagraphStyle(
            "card_title",
            parent=base["Normal"],
            fontName="AppBold",
            fontSize=10,
            leading=12,
        ),
        "card_text": ParagraphStyle(
            "card_text",
            parent=base["Normal"],
            fontName="AppRegular",
            fontSize=8.5,
            leading=10.5,
        ),
        "section_title": ParagraphStyle(
            "section_title",
            parent=base["Heading2"],
            fontName="AppBold",
            fontSize=11.5,
            leading=13,
            spaceAfter=4,
        ),
    }


def _make_card_table(title: str, rows: list[list[Paragraph]], width: float):
    styles = _styles()
    data = [[Paragraph(f"<b>{title}</b>", styles["card_title"])]] + rows

    table = Table(data, colWidths=[width])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#cfcfcf")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, 0), 7),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
                ("TOPPADDING", (0, 1), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 2),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


def build_pdf(report: dict, graph_buffers: dict):
    _register_fonts()
    styles = _styles()

    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.0 * cm,
        rightMargin=1.0 * cm,
        topMargin=0.8 * cm,
        bottomMargin=0.8 * cm,
    )

    elements = []

    # Заголовок
    elements.append(Paragraph("Отчёт по расчёту опциона", styles["title"]))
    elements.append(
        Paragraph(
            f"Инструмент: {report['instrument_name']} ({report['ticker']})",
            styles["subtitle"],
        )
    )
    elements.append(Spacer(1, 0.18 * cm))

    # Графики 2x2 - компактнее
    img_w = 8.1 * cm
    img_h = 4.9 * cm

    delta_img = Image(graph_buffers["delta_chart"], width=img_w, height=img_h)
    vega_img = Image(graph_buffers["vega_chart"], width=img_w, height=img_h)
    time_img = Image(graph_buffers["time_chart"], width=img_w, height=img_h)
    price_img = Image(graph_buffers["price_chart"], width=img_w, height=img_h)

    graphs_table = Table(
        [
            [delta_img, vega_img],
            [time_img, price_img],
        ],
        colWidths=[8.35 * cm, 8.35 * cm],
        rowHeights=[5.15 * cm, 5.15 * cm],
        hAlign="CENTER",
    )
    graphs_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 2),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    elements.append(graphs_table)
    elements.append(Spacer(1, 0.2 * cm))

    # Карточки
    card_width = 5.25 * cm

    card_1 = _make_card_table(
        "Данные отчёта",
        [
            [Paragraph(f"ID: {report['id']}", styles["card_text"])],
            [Paragraph(f"Тикер: {report['ticker']}", styles["card_text"])],
            [Paragraph(f"Инструмент: {report['instrument_name']}", styles["card_text"])],
            [Paragraph(f"Интервал: {report['interval_label']}", styles["card_text"])],
            [Paragraph(f"Дата: {report['created_at']}", styles["card_text"])],
        ],
        card_width,
    )

    card_2 = _make_card_table(
        "Параметры модели",
        [
            [Paragraph(f"S: {report['S']}", styles["card_text"])],
            [Paragraph(f"K: {report['K']}", styles["card_text"])],
            [Paragraph(f"T: {report['T']}", styles["card_text"])],
            [Paragraph(f"r: {report['r']}", styles["card_text"])],
            [Paragraph(f"sigma: {report['sigma']}", styles["card_text"])],
        ],
        card_width,
    )

    card_3 = _make_card_table(
        "Результат расчёта",
        [
            [Paragraph(f"Call: {report['call_price']}", styles["card_text"])],
            [Paragraph(f"Put: {report['put_price']}", styles["card_text"])],
            [Paragraph(f"Gamma: {report['gamma']}", styles["card_text"])],
            [Paragraph(f"Vega: {report['vega']}", styles["card_text"])],
        ],
        card_width,
    )

    cards_table = Table(
        [[card_1, card_2, card_3]],
        colWidths=[5.55 * cm, 5.55 * cm, 5.55 * cm],
        hAlign="CENTER",
    )
    cards_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    elements.append(cards_table)
    elements.append(Spacer(1, 0.18 * cm))

    # Таблица
    elements.append(Paragraph("Таблица расчётных показателей", styles["section_title"]))

    metrics_data = [
        ["Call", f"{report['call_price']}", "Put", f"{report['put_price']}"],
        ["Delta Call", f"{report['delta_call']}", "Delta Put", f"{report['delta_put']}"],
        ["Gamma", f"{report['gamma']}", "Vega", f"{report['vega']}"],
        ["Theta Call", f"{report['theta_call']}", "Theta Put", f"{report['theta_put']}"],
        ["Rho Call", f"{report['rho_call']}", "Rho Put", f"{report['rho_put']}"],
    ]

    metrics_table = Table(
        metrics_data,
        colWidths=[3.95 * cm, 4.35 * cm, 3.95 * cm, 4.35 * cm],
        hAlign="CENTER",
    )
    metrics_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.7, colors.HexColor("#d0d0d0")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("FONTNAME", (0, 0), (-1, -1), "AppRegular"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.8),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    elements.append(metrics_table)

    doc.build(elements)
    buffer.seek(0)
    return buffer