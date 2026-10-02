"""Exportación diaria por participante para las fichas de observación del
estudio (solo lectura). Reutiliza el cálculo de `services.py` sin modificarlo:
las hojas diarias y la hoja Resumen salen de las mismas funciones que el CSV.

El .xlsx identifica a cada participante solo por código (P01, P02...); la
relación código-nombre sale aparte en `build_key_rows` (clave_participantes).
"""
import calendar
import io
from collections import defaultdict
from datetime import date, datetime, time, timedelta

from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

from apps.members.models import Member
from .models import DailyNutritionLog, NutritionCheckStatus, WorkoutSessionLog
from .services import (
    InvalidStudyRange,
    compute_study_metrics,
    member_active_window,
    parse_study_range,
)

DEFAULT_START = date(2026, 10, 1)
DEFAULT_END = date(2026, 10, 31)
INACTIVE_DAY = "-"

NUTRITION_LETTERS = {
    NutritionCheckStatus.HECHO: "C",
    NutritionCheckStatus.PARCIALMENTE: "P",
    NutritionCheckStatus.SE_ME_FUE: "N",
}

# * Mismos nombres y orden que el CSV de StudyExportView; "Nombre" pasa a "Participante".
SUMMARY_HEADERS = [
    "Participante", "Sesiones planificadas", "Sesiones completadas", "VD1 %",
    "Días activos", "Días con registro nutricional", "VD2 %",
    "VD1 - Frecuencia semanal", "VD1 - Duración promedio (min)", "VD1 - Variación %",
    "VD2 - Frecuencia semanal", "VD2 - % semanas con mínimo", "VD2 - Variación %",
    "Nº sesiones (control)", "Minutos totales (control)",
]


def resolve_daily_range(start, end):
    """(start, end) como `date`: por defecto 1-31 de octubre de 2026. Con un
    solo extremo, el otro se completa con el inicio/fin de ese mismo mes.
    Lanza `InvalidStudyRange` si el rango es inválido o cruza meses."""
    range_start, range_end = parse_study_range(start, end)
    if range_start is None and range_end is None:
        range_start, range_end = DEFAULT_START, DEFAULT_END
    elif range_start is None:
        range_start = range_end.replace(day=1)
    elif range_end is None:
        range_end = range_start.replace(
            day=calendar.monthrange(range_start.year, range_start.month)[1]
        )
    if (range_start.year, range_start.month) != (range_end.year, range_end.month):
        raise InvalidStudyRange(
            "La exportación diaria cubre un solo mes: el inicio y el fin del "
            "rango deben estar dentro del mismo mes calendario."
        )
    return range_start, range_end


def month_halves(range_start):
    """((1, 15), (16, último día)) del mes de `range_start`."""
    last_day = calendar.monthrange(range_start.year, range_start.month)[1]
    return (1, 15), (16, last_day)


def build_participant_codes():
    """[(código, Member)] de TODOS los participantes del estudio (activos e
    inactivos), por fecha de alta y luego id: el código no se corre al
    desactivar a alguien ni cambia entre descargas."""
    members = list(
        Member.objects.filter(participates_in_study=True).order_by("start_date", "id")
    )
    width = max(2, len(str(len(members))))
    return [(f"P{i:0{width}d}", m) for i, m in enumerate(members, start=1)]


def build_key_rows():
    """Filas de clave_participantes: código, nombre, fecha de alta, estado."""
    return [
        (code, m.full_name, m.start_date.isoformat(), "activo" if m.is_active else "inactivo")
        for code, m in build_participant_codes()
    ]


def _local_day_bounds(range_start, range_end):
    tz = timezone.get_current_timezone()
    lower = timezone.make_aware(datetime.combine(range_start, time.min), tz)
    upper = timezone.make_aware(datetime.combine(range_end + timedelta(days=1), time.min), tz)
    return lower, upper


def _collect_workouts(member_ids, range_start, range_end):
    """{member_id: {día local: [minutos por sesión]}}. El día se toma en la
    zona horaria del proyecto (America/Guatemala), no en UTC."""
    lower, upper = _local_day_bounds(range_start, range_end)
    rows = WorkoutSessionLog.objects.filter(
        member_id__in=member_ids, completed_at__gte=lower, completed_at__lt=upper
    ).values_list("member_id", "completed_at", "duration_minutes")
    data = defaultdict(lambda: defaultdict(list))
    for member_id, completed_at, minutes in rows:
        data[member_id][timezone.localtime(completed_at).date()].append(minutes)
    return data


def _collect_nutrition(member_ids, range_start, range_end):
    rows = DailyNutritionLog.objects.filter(
        member_id__in=member_ids, date__gte=range_start, date__lte=range_end
    ).values_list("member_id", "date", "status")
    data = defaultdict(dict)
    for member_id, day, status in rows:
        data[member_id][day] = status
    return data


def _write_header(ws, first_col_title, days, extra_headers):
    ws.append([first_col_title, *days, *extra_headers])
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")
    ws.freeze_panes = "B2"
    ws.column_dimensions["A"].width = 14
    for col in range(2, 2 + len(days)):
        ws.column_dimensions[get_column_letter(col)].width = 5
    for col in range(2 + len(days), 2 + len(days) + len(extra_headers)):
        ws.column_dimensions[get_column_letter(col)].width = 18


def _center_body(ws):
    for row in ws.iter_rows(min_row=2):
        for cell in row[1:]:
            cell.alignment = Alignment(horizontal="center")


def build_daily_workbook(start=None, end=None):
    """Genera el .xlsx (bytes) con las hojas Entrenamiento 1-15 / 16-N,
    Nutricion 1-15 / 16-N y Resumen, solo con miembros activos. Lanza
    `InvalidStudyRange` si el rango no es válido."""
    range_start, range_end = resolve_daily_range(start, end)
    halves = month_halves(range_start)
    year, month = range_start.year, range_start.month

    coded = [(code, m) for code, m in build_participant_codes() if m.is_active]
    member_ids = [m.id for _, m in coded]
    workouts = _collect_workouts(member_ids, range_start, range_end)
    nutrition = _collect_nutrition(member_ids, range_start, range_end)
    windows = {m.id: member_active_window(m, range_start, range_end) for _, m in coded}

    wb = Workbook()
    wb.remove(wb.active)

    for first, last in halves:
        ws = wb.create_sheet(f"Entrenamiento {first}-{last}")
        _write_header(ws, "Participante", range(first, last + 1), ["Días entrenados", "Minutos totales"])
        for code, m in coded:
            comp_start, cutoff = windows[m.id]
            cells, trained_days, total_minutes = [], 0, 0
            for d in range(first, last + 1):
                day = date(year, month, d)
                minutes = sum(workouts[m.id].get(day, []))
                if day in workouts[m.id]:
                    cells.append(minutes)
                    trained_days += 1
                    total_minutes += minutes
                elif day < comp_start or day > cutoff:
                    cells.append(INACTIVE_DAY)
                else:
                    cells.append(None)
            ws.append([code, *cells, trained_days, total_minutes])
        _center_body(ws)

    for first, last in halves:
        ws = wb.create_sheet(f"Nutricion {first}-{last}")
        _write_header(
            ws, "Participante", range(first, last + 1),
            ["Días con registro", "C (HECHO)", "P (PARCIALMENTE)", "N (SE_ME_FUE)"],
        )
        for code, m in coded:
            comp_start, cutoff = windows[m.id]
            cells, counts = [], {"C": 0, "P": 0, "N": 0}
            for d in range(first, last + 1):
                day = date(year, month, d)
                status = nutrition[m.id].get(day)
                if status is not None:
                    letter = NUTRITION_LETTERS[status]
                    cells.append(letter)
                    counts[letter] += 1
                elif day < comp_start or day > cutoff:
                    cells.append(INACTIVE_DAY)
                else:
                    cells.append(None)
            ws.append([code, *cells, sum(counts.values()), counts["C"], counts["P"], counts["N"]])
        _center_body(ws)

    ws = wb.create_sheet("Resumen")
    ws.append(SUMMARY_HEADERS)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    code_by_member = {m.id: code for code, m in coded}
    metrics = compute_study_metrics(range_start, range_end)
    for row in sorted(metrics, key=lambda r: code_by_member[r["member"].id]):
        member_id = row["member"].id
        minutes_by_day = workouts[member_id]
        n_sessions = sum(len(v) for v in minutes_by_day.values())
        total_minutes = sum(sum(v) for v in minutes_by_day.values())
        ws.append([
            code_by_member[member_id], row["planned"], row["completed"], row["vd1"],
            row["active_days"], row["days_with_log"], row["vd2"],
            row["vd1_weekly_freq"], row["vd1_avg_duration"],
            row["vd1_variation"],
            row["vd2_weekly_freq"], row["vd2_weeks_min_pct"],
            row["vd2_variation"],
            n_sessions, total_minutes,
        ])
    for col in range(1, len(SUMMARY_HEADERS) + 1):
        ws.column_dimensions[get_column_letter(col)].width = 22
    ws.freeze_panes = "B2"

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
