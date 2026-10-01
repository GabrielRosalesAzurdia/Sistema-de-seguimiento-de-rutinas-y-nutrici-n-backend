from django.db import migrations

# * Calendario semanal real del gimnasio. Sábado/domingo sin fila = día de descanso, no un error.
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
