"""Cálculo de VD1 (constancia al entrenamiento) y VD2 (constancia
nutricional) por miembro del estudio, más sus indicadores secundarios.
Compartido entre `StudyExportView` y la pantalla "Datos del estudio" del panel.

VD1: % sobre `Member.planned_training_days` (puede superar 100%).
VD2: % sobre "días activos en el sistema" (`member_active_window`),
no sobre `planned_nutrition_days`.
"""
import math
from datetime import date, datetime, timedelta

from django.db.models import Avg, Sum
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.members.models import Member


def _parse(value):
    if not value:
        return None
    return value if isinstance(value, date) else parse_date(value)


class InvalidStudyRange(ValueError):
    """El rango de fechas pedido para el reporte del estudio es inválido
    (la fecha de inicio es posterior a la de fin)."""


def parse_study_range(start, end):
    """Parsea y valida (start, end) de un reporte del estudio. Devuelve
    (range_start, range_end) como `date` o `None`; lanza `InvalidStudyRange`
    si el inicio es posterior al fin."""
    range_start = _parse(start)
    range_end = _parse(end)
    if range_start and range_end and range_start > range_end:
        raise InvalidStudyRange(
            "La fecha de inicio no puede ser posterior a la fecha de fin."
        )
    return range_start, range_end


def member_active_window(member, range_start, range_end):
    """Devuelve (comp_start, cutoff): la ventana real de actividad del
    miembro dentro del rango start/end pedido. `activation_date` es
    max(start_date, created_at); `cutoff` no pasa de hoy. Compartida con
    `apps.ml_predictions.services.compute_recent_adherence`."""
    # Normaliza a date: en una instancia recién creada en memoria
    # start_date puede llegar como datetime en vez de date.
    start_date = member.start_date
    if isinstance(start_date, datetime):
        start_date = start_date.date()
    activation_date = max(start_date, member.created_at.date())
    today = timezone.localdate()

    comp_start = max(activation_date, range_start) if range_start else activation_date
    cutoff = min(range_end, today) if range_end else today

    return comp_start, cutoff


def count_distinct_workout_days(queryset):
    """Días distintos con al menos una sesión, no el total de filas:
    varias rutinas el mismo día cuentan una sola vez para VD1/constancia.
    También la usa `apps.ml_predictions.services.compute_recent_adherence`."""
    # * El dedup por día es la regla, no un detalle de implementación.
    return queryset.dates("completed_at", "day").count()


def _week_buckets(comp_start, cutoff, num_weeks):
    """Buckets de 7 días calendario desde comp_start; el último puede
    quedar incompleto si el rango no es múltiplo de 7."""
    buckets = []
    for i in range(num_weeks):
        b_start = comp_start + timedelta(days=7 * i)
        b_end = min(b_start + timedelta(days=6), cutoff)
        buckets.append((b_start, b_end))
    return buckets


def _half_split(comp_start, cutoff, range_days):
    """Divide [comp_start, cutoff] en dos mitades por fecha; el día
    extra en rangos de longitud impar va a la segunda mitad."""
    half_days = range_days // 2
    first_end = comp_start + timedelta(days=half_days - 1)
    second_start = first_end + timedelta(days=1)
    return (comp_start, first_end), (second_start, cutoff)


def _compute_secondary_indicators(member, comp_start, cutoff, planned):
    """6 indicadores secundarios de la matriz operacional (VD1 a/b/c,
    VD2 a/b/c), calculados sobre la ventana [comp_start, cutoff] del miembro."""
    range_days = (cutoff - comp_start).days + 1
    if range_days < 1:
        return {
            "vd1_weekly_freq": 0, "vd1_avg_duration": 0, "vd1_variation": None,
            "vd2_weekly_freq": 0, "vd2_weeks_min_pct": 0, "vd2_variation": None,
        }

    num_weeks = math.ceil(range_days / 7)

    workouts = member.workout_logs.filter(completed_at__date__gte=comp_start, completed_at__date__lte=cutoff)
    nutrition_logs = member.nutrition_logs.filter(date__gte=comp_start, date__lte=cutoff)

    completed = count_distinct_workout_days(workouts)
    vd1_weekly_freq = round(completed / num_weeks, 2)
    avg_duration = workouts.aggregate(avg=Avg("duration_minutes"))["avg"]
    vd1_avg_duration = round(avg_duration, 1) if avg_duration is not None else 0

    days_with_log = nutrition_logs.count()
    vd2_weekly_freq = round(days_with_log / num_weeks, 2)

    buckets = _week_buckets(comp_start, cutoff, num_weeks)
    weeks_with_min = sum(
        1 for b_start, b_end in buckets
        if nutrition_logs.filter(date__gte=b_start, date__lte=b_end).count() >= 3
    )
    vd2_weeks_min_pct = round(weeks_with_min / num_weeks * 100, 1)

    if num_weeks < 2:
        vd1_variation = None
        vd2_variation = None
    else:
        (f_start, f_end), (s_start, s_end) = _half_split(comp_start, cutoff, range_days)

        vd1_first = count_distinct_workout_days(workouts.filter(completed_at__date__gte=f_start, completed_at__date__lte=f_end))
        vd1_second = count_distinct_workout_days(workouts.filter(completed_at__date__gte=s_start, completed_at__date__lte=s_end))
        vd1_pct_first = round(vd1_first / planned * 100, 1) if planned else 0
        vd1_pct_second = round(vd1_second / planned * 100, 1) if planned else 0
        vd1_variation = round(vd1_pct_second - vd1_pct_first, 1)

        vd2_first_days = nutrition_logs.filter(date__gte=f_start, date__lte=f_end).count()
        vd2_second_days = nutrition_logs.filter(date__gte=s_start, date__lte=s_end).count()
        f_active = (f_end - f_start).days + 1
        s_active = (s_end - s_start).days + 1
        vd2_pct_first = round(vd2_first_days / f_active * 100, 1) if f_active else 0
        vd2_pct_second = round(vd2_second_days / s_active * 100, 1) if s_active else 0
        vd2_variation = round(vd2_pct_second - vd2_pct_first, 1)

    return {
        "vd1_weekly_freq": vd1_weekly_freq,
        "vd1_avg_duration": vd1_avg_duration,
        "vd1_variation": vd1_variation,
        "vd2_weekly_freq": vd2_weekly_freq,
        "vd2_weeks_min_pct": vd2_weeks_min_pct,
        "vd2_variation": vd2_variation,
    }


def compute_study_metrics(start=None, end=None):
    """Lista de dicts, uno por miembro con `participates_in_study=True`,
    con VD1, VD2 y sus indicadores secundarios para el rango dado (o desde
    la activación de cada miembro hasta hoy si start/end son None)."""
    range_start = _parse(start)
    range_end = _parse(end)

    results = []
    # * Los miembros desactivados (is_active=False) se excluyen por completo.
    for member in Member.objects.filter(participates_in_study=True, is_active=True):
        workouts = member.workout_logs.all()
        nutrition_logs = member.nutrition_logs.all()
        if range_start:
            workouts = workouts.filter(completed_at__date__gte=range_start)
            nutrition_logs = nutrition_logs.filter(date__gte=range_start)
        if range_end:
            workouts = workouts.filter(completed_at__date__lte=range_end)
            nutrition_logs = nutrition_logs.filter(date__lte=range_end)

        completed = count_distinct_workout_days(workouts)
        planned = member.planned_training_days
        vd1 = round((completed / planned) * 100, 1) if planned else 0

        days_with_log = nutrition_logs.count()
        comp_start, cutoff = member_active_window(member, range_start, range_end)
        active_days = max((cutoff - comp_start).days + 1, 0)
        vd2 = round((days_with_log / active_days) * 100, 1) if active_days else 0

        secondary = _compute_secondary_indicators(member, comp_start, cutoff, planned)

        results.append({
            "member": member,
            "name": member.full_name,
            "planned": planned,
            "completed": completed,
            "vd1": vd1,
            "active_days": active_days,
            "days_with_log": days_with_log,
            "vd2": vd2,
            **secondary,
        })
    return results


def compute_total_calories_burned(member) -> int:
    """Suma de `WorkoutSessionLog.calories_burned` histórica del
    miembro — alimenta la card 'Calorías quemadas en total' del
    dashboard."""
    total = member.workout_logs.aggregate(total=Sum("calories_burned"))["total"]
    return total or 0


def compute_workout_streak(member) -> int:
    """Racha = días consecutivos con al menos una sesión completada. Si
    hoy aún no hay registro, cuenta desde ayer (no se rompe por un día
    todavía en curso)."""
    dates_with_workout = set(
        member.workout_logs.values_list("completed_at__date", flat=True)
    )
    today = timezone.localdate()
    day = today if today in dates_with_workout else today - timedelta(days=1)

    streak = 0
    while day in dates_with_workout:
        streak += 1
        day -= timedelta(days=1)
    return streak
