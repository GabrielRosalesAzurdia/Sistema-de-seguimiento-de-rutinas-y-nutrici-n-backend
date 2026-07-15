from django.test import TestCase

from .models import Gender, Member, User
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
