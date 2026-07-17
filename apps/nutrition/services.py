"""
Generación automática de planes de nutrición ("dieta sugerida por ML").

Para esta iteración se usa una heurística determinística (Mifflin-St
Jeor + multiplicador de actividad + reparto de macros por objetivo),
marcada con `generated_by_ml=True` como placeholder — el mismo patrón
que ya usa `apps.ml_predictions` con datos sintéticos mientras no haya
datos reales del estudio (oct-nov 2026) para entrenar un modelo real
de generación de dietas. El coach siempre revisa/aprueba antes de que
el plan llegue al miembro, y llena las sugerencias de platillo al
100% — la heurística nunca toca esos campos de texto.
"""
from apps.members.models import ActivityLevel, FitnessGoal, Gender
from .models import MealSuggestion, MealTime, NutritionPlan, NutritionPlanStatus

ACTIVITY_MULTIPLIERS = {
    ActivityLevel.SEDENTARIO: 1.2,
    ActivityLevel.MODERADO: 1.375,
    ActivityLevel.ACTIVO: 1.55,
    ActivityLevel.MUY_ACTIVO: 1.725,
}

# "Tonificar" recibe el mismo trato que "Perder peso" (decisión de
# negocio ya cerrada, ver CLAUDE.md).
GOAL_CALORIE_FACTORS = {
    FitnessGoal.PERDER_PESO: 0.80,
    FitnessGoal.TONIFICAR: 0.80,
    FitnessGoal.MANTENER_PESO: 1.0,
    FitnessGoal.GANAR_PESO: 1.15,
}

# % de calorías totales repartido entre proteína/carbohidratos/grasas.
GOAL_MACRO_SPLIT = {
    FitnessGoal.PERDER_PESO: (0.35, 0.35, 0.30),
    FitnessGoal.TONIFICAR: (0.35, 0.35, 0.30),
    FitnessGoal.MANTENER_PESO: (0.30, 0.40, 0.30),
    FitnessGoal.GANAR_PESO: (0.25, 0.50, 0.25),
}

# % de calorías/macros repartido entre los 5 tiempos de comida. El
# último tiempo (Cena) se calcula por remanente exacto en
# generate_plan_for_member para que la suma siempre cuadre con el
# total del plan (los campos son PositiveSmallIntegerField, sin
# decimales).
MEAL_TIME_SPLIT = [
    (MealTime.DESAYUNO, 0.20),
    (MealTime.REFACCION_I, 0.10),
    (MealTime.ALMUERZO, 0.30),
    (MealTime.REFACCION_II, 0.10),
    (MealTime.CENA, 0.30),
]


class IncompleteProfileError(Exception):
    """El miembro no tiene los datos mínimos (peso, altura, edad,
    género) para calcular una dieta todavía."""

    def __init__(self, member):
        self.member = member
        super().__init__(
            f"Perfil incompleto para generar dieta: {member.full_name}"
        )


def _bmr(member):
    """Mifflin-St Jeor."""
    weight = float(member.current_weight_kg)
    height = float(member.height_cm)
    age = member.age
    if member.gender == Gender.HOMBRE:
        return 10 * weight + 6.25 * height - 5 * age + 5
    return 10 * weight + 6.25 * height - 5 * age - 161


def generate_plan_for_member(member) -> NutritionPlan:
    """Genera (o devuelve, si ya existe uno) un NutritionPlan pendiente
    de revisión para el miembro, con sus 5 MealSuggestion (macros
    calculados, sugerencias de platillo vacías para que el coach las
    llene). Lanza IncompleteProfileError si faltan datos físicos."""
    existing_pending = member.nutrition_plans.filter(
        status=NutritionPlanStatus.PENDING_REVIEW
    ).order_by("-created_at").first()
    if existing_pending:
        return existing_pending

    if not (member.current_weight_kg and member.height_cm and member.age and member.gender):
        raise IncompleteProfileError(member)

    bmr = _bmr(member)
    tdee = bmr * ACTIVITY_MULTIPLIERS.get(member.activity_level, 1.375)
    goal = member.fitness_goal
    target_calories = tdee * GOAL_CALORIE_FACTORS.get(goal, 1.0)
    protein_pct, carbs_pct, fats_pct = GOAL_MACRO_SPLIT.get(goal, (0.30, 0.40, 0.30))

    total_calories = round(target_calories)
    protein_g = round(total_calories * protein_pct / 4)
    carbs_g = round(total_calories * carbs_pct / 4)
    fats_g = round(total_calories * fats_pct / 9)

    plan = NutritionPlan.objects.create(
        member=member,
        status=NutritionPlanStatus.PENDING_REVIEW,
        generated_by_ml=True,
        is_current=False,
        total_calories=total_calories,
        protein_g=protein_g,
        carbs_g=carbs_g,
        fats_g=fats_g,
        ml_suggested_calories=total_calories,
        ml_suggested_protein_g=protein_g,
        ml_suggested_carbs_g=carbs_g,
        ml_suggested_fats_g=fats_g,
    )

    remaining = {"cal": total_calories, "protein": protein_g, "carbs": carbs_g, "fats": fats_g}
    meals = []
    for index, (meal_time, pct) in enumerate(MEAL_TIME_SPLIT):
        is_last = index == len(MEAL_TIME_SPLIT) - 1
        if is_last:
            cal, protein, carbs, fats = (
                remaining["cal"], remaining["protein"], remaining["carbs"], remaining["fats"]
            )
        else:
            cal = round(total_calories * pct)
            protein = round(protein_g * pct)
            carbs = round(carbs_g * pct)
            fats = round(fats_g * pct)
            remaining["cal"] -= cal
            remaining["protein"] -= protein
            remaining["carbs"] -= carbs
            remaining["fats"] -= fats
        meals.append(MealSuggestion(
            plan=plan, meal_time=meal_time,
            calories=max(cal, 0), protein_g=max(protein, 0),
            carbs_g=max(carbs, 0), fats_g=max(fats, 0),
        ))
    MealSuggestion.objects.bulk_create(meals)

    return plan
