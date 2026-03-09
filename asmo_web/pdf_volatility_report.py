import io
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm


def build_volatility_pdf(report, forecast_rows):

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)

    width, height = A4
    y = height - 2 * cm

    c.setFont("Helvetica-Bold", 16)
    c.drawString(2 * cm, y, "Отчет прогноза волатильности")
    y -= 1.5 * cm

    c.setFont("Helvetica", 11)

    c.drawString(2 * cm, y, f"Инструмент: {report['instrument_name']}")
    y -= 0.7 * cm

    c.drawString(2 * cm, y, f"Тикер: {report['ticker']}")
    y -= 0.7 * cm

    c.drawString(2 * cm, y, f"Горизонт: {report['horizon_code']}")
    y -= 0.7 * cm

    c.drawString(2 * cm, y, f"Текущая IV/HV: {report['current_hv']:.6f}")
    y -= 0.7 * cm

    c.drawString(2 * cm, y, f"Прогноз: {report['predicted_iv']:.6f}")
    y -= 0.7 * cm

    c.drawString(2 * cm, y, f"Нижняя граница: {report['lower_bound']:.6f}")
    y -= 0.7 * cm

    c.drawString(2 * cm, y, f"Верхняя граница: {report['upper_bound']:.6f}")
    y -= 1.2 * cm

    c.setFont("Helvetica-Bold", 12)
    c.drawString(2 * cm, y, "Таблица прогноза")
    y -= 1 * cm

    c.setFont("Helvetica", 9)

    headers = ["Дата", "IV факт", "IV прогноз", "Нижняя", "Верхняя"]
    x_positions = [2 * cm, 6 * cm, 9 * cm, 12 * cm, 15 * cm]

    for i, h in enumerate(headers):
        c.drawString(x_positions[i], y, h)

    y -= 0.5 * cm

    for row in forecast_rows[:25]:

        if y < 2 * cm:
            c.showPage()
            c.setFont("Helvetica", 9)
            y = height - 2 * cm

        c.drawString(x_positions[0], y, row["date"])

        if row["iv_fact"] is not None:
            c.drawString(x_positions[1], y, f"{row['iv_fact']:.4f}")

        if row["iv_forecast"] is not None:
            c.drawString(x_positions[2], y, f"{row['iv_forecast']:.4f}")

        if row["lower"] is not None:
            c.drawString(x_positions[3], y, f"{row['lower']:.4f}")

        if row["upper"] is not None:
            c.drawString(x_positions[4], y, f"{row['upper']:.4f}")

        y -= 0.5 * cm

    c.showPage()
    c.save()

    buffer.seek(0)
    return buffer