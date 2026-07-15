from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("members", "0002_member_gender_member_neck_cm"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="member",
            name="email",
        ),
        migrations.AlterField(
            model_name="member",
            name="user",
            field=models.OneToOneField(
                help_text="Cuenta de autenticación ligada a este miembro (login en la app).",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="member_profile",
                to="members.user",
            ),
        ),
        migrations.AddField(
            model_name="member",
            name="planned_training_days",
            field=models.PositiveSmallIntegerField(
                default=20,
                help_text="Meta individual de días de entrenamiento definida por el coach.",
                verbose_name="Días planificados de rutina",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="member",
            name="planned_nutrition_days",
            field=models.PositiveSmallIntegerField(
                default=30,
                help_text="Meta individual de días de seguimiento nutricional definida por el coach.",
                verbose_name="Días planificados de dieta",
            ),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="member",
            name="left_arm_cm",
            field=models.DecimalField(blank=True, decimal_places=1, max_digits=5, null=True, verbose_name="Brazo izquierdo (cm)"),
        ),
        migrations.AlterField(
            model_name="member",
            name="right_arm_cm",
            field=models.DecimalField(blank=True, decimal_places=1, max_digits=5, null=True, verbose_name="Brazo derecho (cm)"),
        ),
        migrations.AlterField(
            model_name="member",
            name="left_leg_cm",
            field=models.DecimalField(blank=True, decimal_places=1, max_digits=5, null=True, verbose_name="Pierna izquierda (cm)"),
        ),
        migrations.AlterField(
            model_name="member",
            name="right_leg_cm",
            field=models.DecimalField(blank=True, decimal_places=1, max_digits=5, null=True, verbose_name="Pierna derecha (cm)"),
        ),
        migrations.AlterField(
            model_name="member",
            name="left_calf_cm",
            field=models.DecimalField(blank=True, decimal_places=1, max_digits=5, null=True, verbose_name="Pantorrilla izquierda (cm)"),
        ),
        migrations.AlterField(
            model_name="member",
            name="right_calf_cm",
            field=models.DecimalField(blank=True, decimal_places=1, max_digits=5, null=True, verbose_name="Pantorrilla derecha (cm)"),
        ),
        migrations.AlterField(
            model_name="member",
            name="hip_cm",
            field=models.DecimalField(blank=True, decimal_places=1, max_digits=5, null=True, verbose_name="Cadera (cm)"),
        ),
        migrations.AlterField(
            model_name="member",
            name="back_cm",
            field=models.DecimalField(blank=True, decimal_places=1, max_digits=5, null=True, verbose_name="Espalda (cm)"),
        ),
        migrations.AlterField(
            model_name="member",
            name="chest_cm",
            field=models.DecimalField(blank=True, decimal_places=1, max_digits=5, null=True, verbose_name="Pecho (cm)"),
        ),
        migrations.AlterField(
            model_name="member",
            name="waist_cm",
            field=models.DecimalField(blank=True, decimal_places=1, max_digits=5, null=True, verbose_name="Cintura (cm)"),
        ),
    ]
