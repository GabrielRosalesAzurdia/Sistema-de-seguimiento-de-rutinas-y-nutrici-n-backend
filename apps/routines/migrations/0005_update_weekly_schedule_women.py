from django.db import migrations

# Corrige, en el calendario ya sembrado por 0003_seed_weekly_schedule, las
# dos filas de mujeres que ahora usan las categorías exclusivas agregadas en
# 0004_add_new_routine_categories (2026-09-23): miércoles pasa de
# PIERNA_CUADRICEPS a PIERNA_CUADRICEPS_CIRCUITO, y jueves de PECHO a
# PECHO_HOMBRO_TRICEPS. No se edita 0003 (ya aplicada en Neon) — esto es una
# migración de datos nueva, idempotente: usa update_or_create, así que si la
# fila ya tiene la categoría correcta (como ya ocurre en Neon, actualizado a
# mano fuera del repo) no cambia nada.
UPDATED_ROWS = [
    # (day_of_week, gender, category)
    (2, "MUJER", "PIERNA_CUADRICEPS_CIRCUITO"),  # Miércoles
    (3, "MUJER", "PECHO_HOMBRO_TRICEPS"),        # Jueves
]

# Valores que 0003 dejó originalmente en esas mismas filas, para poder
# revertir la migración de forma simétrica.
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
