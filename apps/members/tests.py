import csv
import json
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from .management.commands.alta_participantes import RecordError, apply_plan, build_plan, compute_diff
from .models import ActivityLevel, FitnessGoal, Gender, Member, User
from .services import calculate_body_fat_percentage, calculate_body_composition


def _make_user(email):
    return User.objects.create_user(username=email, email=email, password="pass1234")


class NavyMethodFormulaTests(TestCase):
    """Lógica de cálculo pura (Track C) — fácil de romper sin darse
    cuenta si se toca la fórmula o el orden de los parámetros."""

    def test_missing_neck_cm_returns_none(self):
        result = calculate_body_fat_percentage(
            gender=Gender.MUJER, waist_cm=78, neck_cm=None, height_cm=165, hip_cm=98,
        )
        self.assertIsNone(result)

    def test_female_formula_requires_hip(self):
        result = calculate_body_fat_percentage(
            gender=Gender.MUJER, waist_cm=78, neck_cm=32, height_cm=165, hip_cm=None,
        )
        self.assertIsNone(result)

    def test_male_formula_known_value(self):
        result = calculate_body_fat_percentage(
            gender=Gender.HOMBRE, waist_cm=90, neck_cm=40, height_cm=175, hip_cm=None,
        )
        self.assertAlmostEqual(result, 19.2, places=1)

    def test_female_formula_known_value(self):
        result = calculate_body_fat_percentage(
            gender=Gender.MUJER, waist_cm=78, neck_cm=32, height_cm=165, hip_cm=98,
        )
        self.assertAlmostEqual(result, 30.4, places=1)


class MemberSaveAutoCalculationTests(TestCase):
    """Member.save() debe calcular automáticamente cuando hay medidas
    suficientes, y NUNCA sobreescribir con None cuando faltan."""

    def test_save_computes_body_composition_when_measurements_present(self):
        member = Member.objects.create(
            user=_make_user("mujer@test.com"),
            first_name="Test", first_last_name="Mujer", age=25, height_cm="165.0",
            gender=Gender.MUJER, neck_cm="32.0", waist_cm="78.0", hip_cm="98.0",
            planned_training_days=20, planned_nutrition_days=30,
        )
        self.assertIsNotNone(member.body_fat_percentage)
        self.assertIsNotNone(member.body_water_percentage)

    def test_save_preserves_manual_value_when_measurements_incomplete(self):
        member = Member.objects.create(
            user=_make_user("sincuello@test.com"),
            first_name="Test", first_last_name="SinCuello", age=25, height_cm="165.0",
            body_fat_percentage="99.9",  # valor manual, sin neck_cm/gender todavía
            planned_training_days=20, planned_nutrition_days=30,
        )
        member.refresh_from_db()
        self.assertEqual(float(member.body_fat_percentage), 99.9)


def _base_participant_record(**overrides):
    record = {
        "crear_cuenta": True,
        "correo_app": "participante@test.com",
        "password_temporal": "Temporal-123",
        "nombre_completo": "Ana Lucia Perez Lopez",
        "edad": 28,
        "genero": "Femenino",
        "telefono": "55511111",
        "estatura_cm": 162,
        "objetivo": "Bajar de peso",
        "peso_meta_kg": 58,
        "nivel_actividad": "Activo",
        "dias_entreno": 4,
        "notas_salud": "",
        "peso_kg": 65.2,
        "fecha_medicion": "2026-09-05",
        "brazo_izq": 27, "brazo_der": 27.5, "pierna_izq": 52, "pierna_der": 52.5,
        "pantorrilla_izq": 33, "pantorrilla_der": 33.2, "cintura": 80, "pecho": 90,
        "cadera": 95, "espalda": 40,
        "en_estudio": True,
        "consentimiento": True,
    }
    record.update(overrides)
    return record


class AltaParticipantesBuildPlanTests(TestCase):
    """build_plan() no toca la base — cubre el mapeo de campos del JSON
    del estudio contra Member, incluidas las ambigüedades resueltas con
    el coach (dias_entreno semanal vs. mensual, nombres sin 4 palabras,
    enums no reconocidos)."""

    def test_four_word_name_splits_into_the_four_member_fields(self):
        payload, warnings = build_plan(_base_participant_record())
        fields = payload["member_fields"]
        self.assertEqual(
            (fields["first_name"], fields["second_name"],
             fields["first_last_name"], fields["second_last_name"]),
            ("Ana", "Lucia", "Perez", "Lopez"),
        )
        self.assertFalse(any("nombre_completo" in w for w in warnings))

    def test_non_four_word_name_goes_to_manual_review(self):
        payload, warnings = build_plan(
            _base_participant_record(nombre_completo="Ana Perez")
        )
        fields = payload["member_fields"]
        self.assertEqual(fields["first_name"], "Ana Perez")
        self.assertEqual(fields["first_last_name"], "")
        self.assertTrue(any("nombre_completo" in w for w in warnings))

    def test_dias_entreno_weekly_is_multiplied_to_a_month(self):
        payload, _ = build_plan(_base_participant_record(dias_entreno=4))
        self.assertEqual(payload["member_fields"]["planned_training_days"], 16)

    def test_dias_entreno_already_monthly_is_used_as_is(self):
        payload, _ = build_plan(_base_participant_record(dias_entreno=16))
        self.assertEqual(payload["member_fields"]["planned_training_days"], 16)

    def test_planned_nutrition_days_defaults_to_three_when_dias_comidas_missing(self):
        payload, warnings = build_plan(_base_participant_record())
        self.assertEqual(payload["member_fields"]["planned_nutrition_days"], 3)
        self.assertTrue(any("sin dias_comidas" in w for w in warnings))

    def test_dias_comidas_weekly_is_multiplied_to_a_month(self):
        payload, _ = build_plan(_base_participant_record(dias_comidas=4))
        self.assertEqual(payload["member_fields"]["planned_nutrition_days"], 16)

    def test_dias_comidas_already_monthly_is_used_as_is(self):
        payload, _ = build_plan(_base_participant_record(dias_comidas=20))
        self.assertEqual(payload["member_fields"]["planned_nutrition_days"], 20)

    def test_missing_required_field_raises_record_error(self):
        record = _base_participant_record()
        del record["estatura_cm"]
        with self.assertRaises(RecordError):
            build_plan(record)

    def test_unrecognized_objetivo_falls_back_to_mantener_peso_with_warning(self):
        payload, warnings = build_plan(_base_participant_record(objetivo="No sé"))
        self.assertEqual(payload["member_fields"]["fitness_goal"], FitnessGoal.MANTENER_PESO)
        self.assertTrue(any("objetivo no reconocido" in w for w in warnings))

    def test_ganar_masa_muscular_maps_to_ganar_peso(self):
        payload, _ = build_plan(_base_participant_record(objetivo="Ganar masa muscular"))
        self.assertEqual(payload["member_fields"]["fitness_goal"], FitnessGoal.GANAR_PESO)

    def test_perder_peso_y_ganar_masa_muscular_maps_to_tonificar(self):
        payload, _ = build_plan(
            _base_participant_record(objetivo="Perder peso y ganar masa muscular")
        )
        self.assertEqual(payload["member_fields"]["fitness_goal"], FitnessGoal.TONIFICAR)

    def test_ultima_mensualidad_marks_as_paid_and_sets_next_payment(self):
        payload, warnings = build_plan(
            _base_participant_record(ultima_mensualidad="2026-08-23")
        )
        fields = payload["member_fields"]
        self.assertTrue(fields["is_paid"])
        self.assertEqual(str(fields["last_payment_date"]), "2026-08-23")
        self.assertEqual(str(fields["next_payment_date"]), "2026-09-23")
        self.assertTrue(any("ultima_mensualidad" in w for w in warnings))

    def test_missing_ultima_mensualidad_leaves_unpaid(self):
        payload, _ = build_plan(_base_participant_record())
        fields = payload["member_fields"]
        self.assertFalse(fields["is_paid"])
        self.assertIsNone(fields["last_payment_date"])

    def test_consentimiento_true_maps_to_informed_consent_signed(self):
        payload, _ = build_plan(_base_participant_record(consentimiento=True))
        self.assertTrue(payload["member_fields"]["informed_consent_signed"])

    def test_unrecognized_nivel_actividad_falls_back_to_moderado_with_warning(self):
        payload, warnings = build_plan(_base_participant_record(nivel_actividad="Turbo"))
        self.assertEqual(payload["member_fields"]["activity_level"], ActivityLevel.MODERADO)
        self.assertTrue(any("nivel_actividad no reconocido" in w for w in warnings))

    def test_missing_fecha_medicion_leaves_measurement_pending(self):
        payload, warnings = build_plan(_base_participant_record(fecha_medicion=None))
        self.assertIsNone(payload["measurement"])
        self.assertTrue(any("medición inicial pendiente" in w for w in warnings))

    def test_en_estudio_false_maps_to_participates_in_study_false(self):
        payload, _ = build_plan(_base_participant_record(en_estudio=False))
        self.assertFalse(payload["member_fields"]["participates_in_study"])


class AltaParticipantesApplyPlanTests(TestCase):
    """apply_plan() sí escribe — cubre RNF06 (must_change_password) y
    que la medición inicial + circunferencias queden donde el modelo
    real las espera (Member = snapshot actual, BodyMeasurementLog =
    historial de peso, sin las circunferencias)."""

    def test_apply_plan_creates_user_with_must_change_password(self):
        payload, _ = build_plan(_base_participant_record())
        member = apply_plan(payload)
        member.user.refresh_from_db()
        self.assertTrue(member.user.must_change_password)
        self.assertTrue(member.user.check_password("Temporal-123"))
        self.assertFalse(member.user.is_staff)

    def test_apply_plan_sets_current_snapshot_and_creates_measurement_log(self):
        payload, _ = build_plan(_base_participant_record())
        member = apply_plan(payload)
        self.assertEqual(float(member.waist_cm), 80.0)
        self.assertEqual(float(member.current_weight_kg), 65.2)
        log = member.measurement_logs.get()
        self.assertEqual(str(log.date), "2026-09-05")
        self.assertEqual(float(log.weight_kg), 65.2)


class AltaParticipantesCommandTests(TestCase):
    """Corrida end-to-end del management command contra un JSON chico,
    igual al que se usará con el JSON real de participantes."""

    def _write_json(self, records):
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        json.dump(records, tmp)
        tmp.close()
        self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True))
        return tmp.name

    def test_dry_run_does_not_write_to_the_database(self):
        json_path = self._write_json([_base_participant_record()])
        report_path = json_path + ".csv"
        self.addCleanup(lambda: Path(report_path).unlink(missing_ok=True))

        call_command("alta_participantes", json_path, reporte=report_path)

        self.assertFalse(User.objects.filter(email="participante@test.com").exists())
        with open(report_path, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(rows[0]["resultado"], "dry-run")

    def test_ejecutar_is_idempotent_on_second_run(self):
        json_path = self._write_json([_base_participant_record()])
        report_path = json_path + ".csv"
        self.addCleanup(lambda: Path(report_path).unlink(missing_ok=True))

        call_command("alta_participantes", json_path, "--ejecutar", reporte=report_path)
        call_command("alta_participantes", json_path, "--ejecutar", reporte=report_path)

        self.assertEqual(User.objects.filter(email="participante@test.com").count(), 1)
        with open(report_path, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(rows[0]["resultado"], "ya existía")

    def test_crear_cuenta_false_is_skipped(self):
        json_path = self._write_json([
            _base_participant_record(correo_app="no.entra@test.com", crear_cuenta=False)
        ])
        report_path = json_path + ".csv"
        self.addCleanup(lambda: Path(report_path).unlink(missing_ok=True))

        call_command("alta_participantes", json_path, "--ejecutar", reporte=report_path)

        self.assertFalse(User.objects.filter(email="no.entra@test.com").exists())
        with open(report_path, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(rows[0]["resultado"], "omitido")

    def test_crear_cuenta_true_but_no_consentimiento_is_skipped(self):
        """Caso real detectado en el JSON del estudio: alguien marcado
        crear_cuenta=true pero sin consentimiento firmado todavía — no
        se crea la cuenta aunque crear_cuenta lo permita."""
        json_path = self._write_json([
            _base_participant_record(
                correo_app="sin.firma@test.com", crear_cuenta=True, consentimiento=False,
            )
        ])
        report_path = json_path + ".csv"
        self.addCleanup(lambda: Path(report_path).unlink(missing_ok=True))

        call_command("alta_participantes", json_path, "--ejecutar", reporte=report_path)

        self.assertFalse(User.objects.filter(email="sin.firma@test.com").exists())
        with open(report_path, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(rows[0]["resultado"], "omitido")
        self.assertIn("consentimiento", rows[0]["detalle"])

    def test_real_json_top_level_object_with_participantes_key_is_supported(self):
        """El JSON real del estudio no es una lista plana: es un objeto
        con metadata (generado, criterio_de_alta, resumen, unidades) y
        la lista bajo la clave "participantes"."""
        json_path = self._write_json({
            "generado": "2026-09-12",
            "criterio_de_alta": "texto libre",
            "unidades": {"medidas": "centimetros", "peso": "kilogramos"},
            "resumen": {"total_personas": 1},
            "participantes": [_base_participant_record()],
        })
        report_path = json_path + ".csv"
        self.addCleanup(lambda: Path(report_path).unlink(missing_ok=True))

        call_command("alta_participantes", json_path, reporte=report_path)

        with open(report_path, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["resultado"], "dry-run")


class AltaParticipantesActualizarTests(TestCase):
    """--actualizar: para correos que ya existen, sincroniza los campos
    que cambiaron en el JSON. Caso real que motivó esto: el JSON de
    participantes se corrigió después del alta inicial (ej. una meta de
    peso mal cargada, medidas que llegaron después)."""

    def _write_json(self, records):
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        json.dump(records, tmp)
        tmp.close()
        self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True))
        return tmp.name

    def _create_existing_member(self, **overrides):
        payload, _ = build_plan(_base_participant_record(**overrides))
        return apply_plan(payload)

    def test_without_actualizar_flag_existing_email_is_left_untouched(self):
        self._create_existing_member(peso_meta_kg=58)
        json_path = self._write_json([_base_participant_record(peso_meta_kg=99)])
        report_path = json_path + ".csv"
        self.addCleanup(lambda: Path(report_path).unlink(missing_ok=True))

        call_command("alta_participantes", json_path, "--ejecutar", reporte=report_path)

        member = Member.objects.get(user__email="participante@test.com")
        self.assertEqual(float(member.goal_weight_kg), 58.0)
        with open(report_path, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(rows[0]["resultado"], "ya existía")

    def test_actualizar_dry_run_reports_change_without_writing(self):
        self._create_existing_member(peso_meta_kg=58)
        json_path = self._write_json([_base_participant_record(peso_meta_kg=99)])
        report_path = json_path + ".csv"
        self.addCleanup(lambda: Path(report_path).unlink(missing_ok=True))

        call_command("alta_participantes", json_path, "--actualizar", reporte=report_path)

        member = Member.objects.get(user__email="participante@test.com")
        self.assertEqual(float(member.goal_weight_kg), 58.0)  # sin tocar, es dry-run
        with open(report_path, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(rows[0]["resultado"], "actualizaría")
        self.assertIn("goal_weight_kg", rows[0]["detalle"])

    def test_actualizar_ejecutar_writes_changed_fields_only(self):
        self._create_existing_member(peso_meta_kg=58, nivel_actividad="Activo")
        json_path = self._write_json(
            [_base_participant_record(peso_meta_kg=99, nivel_actividad="Activo")]
        )
        report_path = json_path + ".csv"
        self.addCleanup(lambda: Path(report_path).unlink(missing_ok=True))

        call_command(
            "alta_participantes", json_path, "--ejecutar", "--actualizar", reporte=report_path
        )

        member = Member.objects.get(user__email="participante@test.com")
        self.assertEqual(float(member.goal_weight_kg), 99.0)
        with open(report_path, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(rows[0]["resultado"], "actualizado")
        self.assertIn("goal_weight_kg", rows[0]["detalle"])
        self.assertNotIn("activity_level", rows[0]["detalle"])  # no cambió, no se reporta

    def test_actualizar_never_touches_start_date(self):
        member = self._create_existing_member()
        original_start_date = member.start_date
        json_path = self._write_json([_base_participant_record(fecha_medicion="2020-01-01")])
        report_path = json_path + ".csv"
        self.addCleanup(lambda: Path(report_path).unlink(missing_ok=True))

        call_command(
            "alta_participantes", json_path, "--ejecutar", "--actualizar", reporte=report_path
        )

        member.refresh_from_db()
        self.assertEqual(member.start_date, original_start_date)

    def test_actualizar_never_touches_password_or_must_change_password(self):
        member = self._create_existing_member()
        member.user.must_change_password = False
        member.user.save(update_fields=["must_change_password"])

        json_path = self._write_json(
            [_base_participant_record(password_temporal="OtraClaveNueva-999")]
        )
        report_path = json_path + ".csv"
        self.addCleanup(lambda: Path(report_path).unlink(missing_ok=True))

        call_command(
            "alta_participantes", json_path, "--ejecutar", "--actualizar", reporte=report_path
        )

        member.user.refresh_from_db()
        self.assertTrue(member.user.check_password("Temporal-123"))
        self.assertFalse(member.user.must_change_password)

    def test_actualizar_adds_new_measurement_log_on_new_date_only(self):
        member = self._create_existing_member(fecha_medicion="2026-09-05", peso_kg=70)
        self.assertEqual(member.measurement_logs.count(), 1)

        json_path = self._write_json(
            [_base_participant_record(fecha_medicion="2026-09-05", peso_kg=70)]
        )
        report_path = json_path + ".csv"
        self.addCleanup(lambda: Path(report_path).unlink(missing_ok=True))
        call_command(
            "alta_participantes", json_path, "--ejecutar", "--actualizar", reporte=report_path
        )
        self.assertEqual(member.measurement_logs.count(), 1)  # misma fecha, no duplica

        json_path_2 = self._write_json(
            [_base_participant_record(fecha_medicion="2026-10-05", peso_kg=68)]
        )
        report_path_2 = json_path_2 + ".csv"
        self.addCleanup(lambda: Path(report_path_2).unlink(missing_ok=True))
        call_command(
            "alta_participantes", json_path_2, "--ejecutar", "--actualizar", reporte=report_path_2
        )
        self.assertEqual(member.measurement_logs.count(), 2)  # fecha nueva, sí agrega

    def test_actualizar_reports_sin_cambios_when_nothing_changed(self):
        self._create_existing_member()
        json_path = self._write_json([_base_participant_record()])
        report_path = json_path + ".csv"
        self.addCleanup(lambda: Path(report_path).unlink(missing_ok=True))

        call_command(
            "alta_participantes", json_path, "--ejecutar", "--actualizar", reporte=report_path
        )

        with open(report_path, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        self.assertEqual(rows[0]["resultado"], "sin cambios")

    def test_compute_diff_ignores_start_date(self):
        member = self._create_existing_member()
        payload, _ = build_plan(_base_participant_record(fecha_medicion="2020-01-01"))
        diffs, _ = compute_diff(member, payload)
        self.assertNotIn("start_date", diffs)


class AltaParticipantesAccionFieldTests(TestCase):
    """El JSON real empezó a traer "accion" ("crear"/"actualizar"/
    "sin cambios"/"pendiente") — cuando viene, manda por encima de
    crear_cuenta y de la bandera --actualizar (el coach ya decidió qué
    hacer con cada participante)."""

    def _write_json(self, records):
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        json.dump(records, tmp)
        tmp.close()
        self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True))
        return tmp.name

    def _run(self, records, *extra_args):
        json_path = self._write_json(records)
        report_path = json_path + ".csv"
        self.addCleanup(lambda: Path(report_path).unlink(missing_ok=True))
        call_command("alta_participantes", json_path, *extra_args, reporte=report_path)
        with open(report_path, newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))

    def test_accion_sin_cambios_is_skipped_even_if_crear_cuenta_true(self):
        rows = self._run(
            [_base_participant_record(accion="sin cambios")], "--ejecutar", "--actualizar"
        )
        self.assertEqual(rows[0]["resultado"], "omitido")
        self.assertIn("accion=sin cambios", rows[0]["detalle"])
        self.assertFalse(User.objects.filter(email="participante@test.com").exists())

    def test_accion_pendiente_is_skipped(self):
        rows = self._run([_base_participant_record(accion="pendiente")], "--ejecutar")
        self.assertEqual(rows[0]["resultado"], "omitido")
        self.assertIn("accion=pendiente", rows[0]["detalle"])

    def test_accion_unknown_value_is_reported_as_error(self):
        rows = self._run([_base_participant_record(accion="lo que sea")], "--ejecutar")
        self.assertEqual(rows[0]["resultado"], "error")
        self.assertIn("accion desconocida", rows[0]["detalle"])
        self.assertFalse(User.objects.filter(email="participante@test.com").exists())

    def test_accion_crear_creates_account_without_needing_crear_cuenta_flag(self):
        rows = self._run(
            [_base_participant_record(accion="crear", crear_cuenta=False)], "--ejecutar"
        )
        self.assertEqual(rows[0]["resultado"], "creado")
        self.assertTrue(User.objects.filter(email="participante@test.com").exists())

    def test_accion_crear_conflicts_when_email_already_has_account(self):
        payload, _ = build_plan(_base_participant_record())
        apply_plan(payload)

        rows = self._run([_base_participant_record(accion="crear")], "--ejecutar")
        self.assertEqual(rows[0]["resultado"], "error")
        self.assertIn("accion=crear pero el correo ya tiene cuenta", rows[0]["detalle"])

    def test_accion_actualizar_updates_without_needing_actualizar_flag(self):
        payload, _ = build_plan(_base_participant_record(peso_meta_kg=58))
        apply_plan(payload)

        rows = self._run(
            [_base_participant_record(accion="actualizar", peso_meta_kg=99)], "--ejecutar"
        )
        self.assertEqual(rows[0]["resultado"], "actualizado")
        member = Member.objects.get(user__email="participante@test.com")
        self.assertEqual(float(member.goal_weight_kg), 99.0)
        member.user.refresh_from_db()
        self.assertTrue(member.user.check_password("Temporal-123"))  # contraseña intacta

    def test_accion_actualizar_errors_when_account_does_not_exist_yet(self):
        rows = self._run([_base_participant_record(accion="actualizar")], "--ejecutar")
        self.assertEqual(rows[0]["resultado"], "error")
        self.assertIn("accion=actualizar pero el correo todavía no tiene cuenta", rows[0]["detalle"])

    def test_accion_crear_still_blocked_without_consentimiento(self):
        rows = self._run(
            [_base_participant_record(accion="crear", consentimiento=False)], "--ejecutar"
        )
        self.assertEqual(rows[0]["resultado"], "omitido")
        self.assertIn("consentimiento", rows[0]["detalle"])
        self.assertFalse(User.objects.filter(email="participante@test.com").exists())
