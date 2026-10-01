"""Inferencia de los modelos de progreso del usuario: carga el artefacto
entrenado en /ml (joblib) y expone la predicción para las vistas del API.

# TODO: reemplazar la heurística de `predict_days_to_goal` por el modelo
entrenado con datos reales una vez termine el período de implementación.
"""
from datetime import timedelta
from pathlib import Path

import joblib
import pandas as pd
from django.utils import timezone

from apps.tracking.services import count_distinct_workout_days, member_active_window

MODEL_DIR = Path(__file__).resolve().parent / "trained_models"

# Ventana reciente (días) sobre la que se mide la constancia para la predicción.
RECENT_ADHERENCE_WINDOW_DAYS = 30

# * Mínimo de sesiones registradas para confiar en la predicción; por debajo,
# el denominador de constancia es casi cero y el resultado se dispara.
MIN_SESSIONS_FOR_RELIABLE_PREDICTION = 3

# * Tope superior de predict_days_to_goal (~1 año), aplica a ambas ramas.
MAX_DAYS_TO_GOAL = 365


def _load_model(filename: str):
    path = MODEL_DIR / filename
    if not path.exists():
        return None
    return joblib.load(path)


def compute_recent_adherence(member, days: int = RECENT_ADHERENCE_WINDOW_DAYS):
    """Constancia reciente (training, nutrition) en [0, 1], misma definición
    operacional que VD1/VD2 (ver apps/tracking/services.py), recortada a 1.0."""
    today = timezone.localdate()
    window_start = today - timedelta(days=days)
    comp_start, cutoff = member_active_window(member, window_start, today)

    recent_workouts = count_distinct_workout_days(member.workout_logs.filter(
        completed_at__date__gte=window_start, completed_at__date__lte=today
    ))
    training_adherence = (
        min(recent_workouts / member.planned_training_days, 1.0)
        if member.planned_training_days
        else 0.0
    )

    active_days = max((cutoff - comp_start).days + 1, 0)
    recent_nutrition_days = member.nutrition_logs.filter(
        date__gte=comp_start, date__lte=cutoff
    ).count()
    nutrition_adherence = (
        min(recent_nutrition_days / active_days, 1.0) if active_days else 0.0
    )

    return training_adherence, nutrition_adherence


def predict_days_to_goal(member, recent_training_adherence: float, recent_nutrition_adherence: float):
    """Estima días restantes para la meta de peso del miembro. Devuelve
    dict con days_to_goal, model_type e input_features."""
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
        # DataFrame de una fila con el mismo orden de columnas que
        # ml/training/train_progress_model.py::build_features().
        X = pd.DataFrame([_vectorize(features)], columns=[
            "age", "imc", "activity_level", "fitness_goal",
            "weight_diff_kg", "training_adherence", "nutrition_adherence",
        ])
        prediction = model.predict(X)[0]
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

    # * Tope aplicado a ambas ramas (Random Forest y heurística).
    days = min(days, MAX_DAYS_TO_GOAL)

    # Con muy pocas sesiones el resultado es ruido: se omite y el
    # dashboard muestra un guion en su lugar.
    if member.workout_logs.count() < MIN_SESSIONS_FOR_RELIABLE_PREDICTION:
        days = None

    return {"days_to_goal": days, "model_type": model_type, "input_features": features}


def _vectorize(features: dict):
    """Convierte el diccionario de features a un vector numérico, en el
    mismo orden/codificación usado al entrenar el modelo."""
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
