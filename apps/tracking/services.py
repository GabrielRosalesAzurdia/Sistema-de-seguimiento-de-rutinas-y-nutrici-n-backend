"""
Cálculo de VD1 (constancia al entrenamiento) y VD2 (constancia
nutricional) por miembro que participa en el estudio. Compartido entre
el endpoint de exportación CSV (apps.tracking.views.StudyExportView) y
la pantalla del panel "Datos del estudio" (apps.panel.views), para no
duplicar la lógica en dos lugares.

Definición operacional cerrada (ver CLAUDE.md sección 1 y 8): las
"sesiones planificadas" (VD1) y "días planificados" (VD2) son la meta
individual que el coach define por miembro al registrarlo
(`Member.planned_training_days` / `Member.planned_nutrition_days`), no
un valor calculado del calendario semanal. Si el miembro completa más
de lo planificado, el % puede superar 100% (decisión de negocio: se
considera una meta superada, no un error de datos).
"""
from datetime import timedelta
from django.db.models import Sum
from django.utils import timezone

from apps.members.models import Member


def compute_study_metrics(start=None, end=None):
    """
    Devuelve una lista de dicts, uno por miembro con
    `participates_in_study=True`, con VD1 y VD2 para el rango de
    fechas dado (o todo el histórico si start/end son None).
    """
    results = []
    for member in Member.objects.filter(participates_in_study=True):
        workouts = member.workout_logs.all()
        nutrition_logs = member.nutrition_logs.all()
        if start:
            workouts = workouts.filter(completed_at__date__gte=start)
            nutrition_logs = nutrition_logs.filter(date__gte=start)
        if end:
            workouts = workouts.filter(completed_at__date__lte=end)
            nutrition_logs = nutrition_logs.filter(date__lte=end)

        completed = workouts.count()
        planned = member.planned_training_days
        vd1 = round((completed / planned) * 100, 1) if planned else 0

        days_with_log = nutrition_logs.count()
        planned_nutrition = member.planned_nutrition_days
        vd2 = round((days_with_log / planned_nutrition) * 100, 1) if planned_nutrition else 0

        results.append({
            "member": member,
            "name": member.full_name,
            "planned": planned,
            "completed": completed,
            "vd1": vd1,
            "planned_nutrition": planned_nutrition,
            "days_with_log": days_with_log,
            "vd2": vd2,
        })
    return results


def compute_total_calories_burned(member) -> int:
    """Suma de `WorkoutSessionLog.calories_burned` histórica del
    miembro — alimenta la card 'Calorías quemadas en total' del
    dashboard."""
    total = member.workout_logs.aggregate(total=Sum("calories_burned"))["total"]
    return total or 0


def compute_workout_streak(member) -> int:
    """
    Racha = días consecutivos con al menos una `WorkoutSessionLog`
    completada (decisión de negocio: constancia de entrenamiento, no
    de nutrición).

    Si hoy todavía no hay registro, la racha se cuenta desde ayer (no
    se rompe solo porque el día actual no ha terminado) — mismo
    criterio que usan apps de hábitos tipo Duolingo.
    """
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
