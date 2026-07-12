"""
Servicio de inferencia para los modelos de progreso del usuario.

Los modelos se entrenan offline con los scripts en /ml (fuera del
backend, para no acoplar el entrenamiento al ciclo de despliegue) y se
serializan con joblib. Este módulo solo carga el artefacto entrenado y
expone una función de predicción sencilla que las vistas del API
pueden invocar.

TODO (fase de desarrollo, Capítulo 5): reemplazar la lógica heurística
de `predict_days_to_goal` por la carga real de un modelo entrenado
(joblib.load) una vez se cuente con datos históricos suficientes del
período de implementación (oct-nov 2026). Mientras no hay datos reales
de uso, se deja un cálculo determinístico razonable como placeholder
para no bloquear el desarrollo del resto del sistema.
"""
from pathlib import Path
import joblib

MODEL_DIR = Path(__file__).resolve().parent / "trained_models"


def _load_model(filename: str):
    path = MODEL_DIR / filename
    if not path.exists():
        return None
    return joblib.load(path)


def predict_days_to_goal(member, recent_training_adherence: float, recent_nutrition_adherence: float):
    """
    Estima días restantes para alcanzar la meta de peso del miembro.

    Parameters
    ----------
    member: apps.members.models.Member
    recent_training_adherence: float (0-1) % reciente de sesiones completadas
    recent_nutrition_adherence: float (0-1) % reciente de días con registro nutricional

    Returns
    -------
    dict con las llaves: days_to_goal, model_type, input_features
    """
    model = _load_model("random_forest_progress_v1.joblib")

    current_weight = float(member.current_weight_kg or 0)
    goal_weight = float(member.goal_weight_kg or current_weight)
    weight_diff = abs(current_weight - goal_weight)

    features = {
        "age": member.age,
        "imc": member.imc,
        "activity_level": member.activity_level,
        "fitness_goal": member.fitness_goal,
        "weight_diff_kg": weight_diff,
        "training_adherence": recent_training_adherence,
        "nutrition_adherence": recent_nutrition_adherence,
    }

    if model is not None:
        # El modelo real espera un vector numérico ya codificado; ver
        # ml/training/train_progress_model.py para el preprocesamiento
        # exacto (one-hot de activity_level/fitness_goal, escalado, etc.)
        prediction = model.predict([_vectorize(features)])[0]
        days = max(int(round(prediction)), 0)
        model_type = "RANDOM_FOREST"
    else:
        # Heurística placeholder: a mayor constancia, menor tiempo estimado.
        adherence_factor = max(
            0.2, (recent_training_adherence + recent_nutrition_adherence) / 2
        )
        base_days_per_kg = 14  # ~0.5kg/semana como referencia conservadora
        days = int(round((weight_diff * base_days_per_kg) / adherence_factor)) if weight_diff else 0
        model_type = "HEURISTIC_PLACEHOLDER"

    return {"days_to_goal": days, "model_type": model_type, "input_features": features}


def _vectorize(features: dict):
    """Convierte el diccionario de features a un vector numérico. Debe
    mantenerse en sincronía con el preprocesamiento usado al entrenar."""
    activity_map = {"SEDENTARIO": 0, "MODERADO": 1, "ACTIVO": 2, "MUY_ACTIVO": 3}
    goal_map = {"GANAR_PESO": 0, "PERDER_PESO": 1, "MANTENER_PESO": 2, "TONIFICAR": 1}
    return [
        features["age"],
        features["imc"] or 0,
        activity_map.get(features["activity_level"], 1),
        goal_map.get(features["fitness_goal"], 1),
        features["weight_diff_kg"],
        features["training_adherence"],
        features["nutrition_adherence"],
    ]
