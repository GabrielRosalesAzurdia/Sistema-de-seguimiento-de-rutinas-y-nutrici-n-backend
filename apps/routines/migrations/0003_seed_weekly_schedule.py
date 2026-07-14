from django.db import migrations

# Calendario semanal real del gimnasio (confirmado con el desarrollador
# a cargo, no es un supuesto). Sábado/domingo quedan sin fila = sin
# rutina asignada ese día (descanso), no un error.
#
# Nota: la regla de negocio dice "Pierna" sin especificar Cuádriceps vs
# Glúteos (el catálogo tiene ambas categorías) — se asume
# PIERNA_CUADRICEPS como default razonable; el coach puede corregirlo
# desde el panel admin una vez construido (Track E.3) si prefiere
# Glúteos en algún día.
SCHEDULE = [
    # (day_of_week, gender, category)
    (0, "HOMBRE", "PECHO"),              # Lunes
    (1, "HOMBRE", "PIERNA_CUADRICEPS"),   # Martes
    (2, "HOMBRE", "BRAZOS_ESPALDA"),      # Miércoles
    (3, "HOMBRE", "PIERNA_CUADRICEPS"),   # Jueves
    (4, "HOMBRE", "PECHO"),              # Viernes
    (0, "MUJER", "PIERNA_CUADRICEPS"),    # Lunes
    (1, "MUJER", "BRAZOS_ESPALDA"),       # Martes
    (2, "MUJER", "PIERNA_CUADRICEPS"),    # Miércoles
    (3, "MUJER", "PECHO"),               # Jueves
    (4, "MUJER", "PIERNA_CUADRICEPS"),    # Viernes
]


def seed_schedule(apps, schema_editor):
    ScheduledRoutineDay = apps.get_model("routines", "ScheduledRoutineDay")
    for day_of_week, gender, category in SCHEDULE:
        ScheduledRoutineDay.objects.get_or_create(
            day_of_week=day_of_week, gender=gender, defaults={"category": category}
        )


def remove_schedule(apps, schema_editor):
    ScheduledRoutineDay = apps.get_model("routines", "ScheduledRoutineDay")
    ScheduledRoutineDay.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("routines", "0002_scheduledroutineday"),
    ]

    operations = [
        migrations.RunPython(seed_schedule, remove_schedule),
    ]
