import calendar
import datetime


def add_one_month(d: datetime.date) -> datetime.date:
    """Suma un mes calendario a `d`, ajustando el día si el mes
    destino tiene menos días (ej. 31/ene -> 28 o 29/feb)."""
    month = d.month + 1
    year = d.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return d.replace(year=year, month=month, day=day)
