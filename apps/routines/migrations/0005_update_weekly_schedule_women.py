from django.db import migrations

# Cambia el calendario de mujeres a las categorías exclusivas de miércoles/jueves. Idempotente (update_or_create).
UPDATED_ROWS = [
    # (day_of_week, gender, category)
    (2, "MUJER", "PIERNA_CUADRICEPS_CIRCUITO"),  # Miércoles
    (3, "MUJER", "PECHO_HOMBRO_TRICEPS"),        # Jueves
]

# Valores previos de esas filas, para poder revertir la migración.
PREVIOUS_ROWS = [
    (2, "MUJER", "PIERNA_CUADRICEPS"),
    (3, "MUJER", "PECHO"),
]


def _apply(apps, rows):
    ScheduledRoutineDay = apps.get_model("routines", "ScheduledRoutineDay")
    for day_of_week, gender, category in rows:
        ScheduledRoutineDay.objects.update_or_create(
            day_of_week=day_of_week, gender=gender, defaults={"category": category}
        )


def update_women_schedule(apps, schema_editor):
    _apply(apps, UPDATED_ROWS)


def revert_women_schedule(apps, schema_editor):
    _apply(apps, PREVIOUS_ROWS)


class Migration(migrations.Migration):

    dependencies = [
        ("routines", "0004_add_new_routine_categories"),
    ]

    operations = [
        migrations.RunPython(update_women_schedule, revert_women_schedule),
    ]
