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
from datetime import timedelta
from pathlib import Path

import joblib
import pandas as pd
from django.utils import timezone

from apps.tracking.services import member_active_window

MODEL_DIR = Path(__file__).resolve().parent / "trained_models"

# Ventana reciente (en días) sobre la que se mide la constancia que
# alimenta la predicción. El nombre de los parámetros de
# predict_days_to_goal ya es "recent_*": interesa la constancia
# reciente, no la histórica completa desde el alta.
RECENT_ADHERENCE_WINDOW_DAYS = 30

# Con menos de 3 sesiones registradas, el denominador de constancia que
# alimenta tanto la heurística como el Random Forest (entrenado sobre la
# misma fórmula sin tope, ver ml/training/generate_synthetic_data.py) es
# casi cero y el resultado se dispara a cifras de años. Se cuenta en
# SESIONES registradas, nunca en días transcurridos: si se contara en
# días, el número aparecería solo por dejar pasar el tiempo sin que el
# miembro haga nada, que es justo el caso ruidoso que se quiere evitar.
MIN_SESSIONS_FOR_RELIABLE_PREDICTION = 3

# Tope superior del valor devuelto por predict_days_to_goal. Tanto la
# heurística como el Random Forest (entrenado sobre la misma fórmula sin
# tope) disparan cifras de años para combinaciones de poca constancia +
# mucho peso pendiente. Se acota el resultado final de AMBAS ramas: 730
# días (~2 años) es el máximo que una app de fitness debería presentar
# como estimación creíble. `docs/plan_correcciones.md` deja el valor
# como decisión de producto abierta; se adopta 730.
MAX_DAYS_TO_GOAL = 730


def _load_model(filename: str):
    path = MODEL_DIR / filename
    if not path.exists():
        return None
    return joblib.load(path)


def compute_recent_adherence(member, days: int = RECENT_ADHERENCE_WINDOW_DAYS):
    """
    Devuelve (training_adherence, nutrition_adherence) en [0, 1] para el
    miembro, sobre la ventana reciente de `days` días.

    Usa los mismos denominadores que la definición operacional del
    estudio (ver apps/tracking/services.py), no constantes fijas:
    - entrenamiento: `Member.planned_training_days`, la meta mensual que
      el coach fija por miembro (0.0 si esa meta es 0).
    - nutrición: los "días activos en el sistema" del miembro dentro de
      la ventana, vía `member_active_window` (misma lógica que VD2).

    Ambos ratios se recortan a 1.0 antes de devolverlos: la meta de
    entrenamiento se puede superar (VD1 no tiene tope), pero el modelo
    se entrenó con constancias en [0, 1] y un valor fuera de ese rango
    degrada la predicción.
    """
    today = timezone.localdate()
    window_start = today - timedelta(days=days)
    comp_start, cutoff = member_active_window(member, window_start, today)

    recent_workouts = member.workout_logs.filter(
        completed_at__date__gte=window_start, completed_at__date__lte=today
    ).count()
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
        # DataFrame de una fila con los mismos nombres/orden de columnas
        # que ml/training/train_progress_model.py::build_features(),
        # para que sklearn no emita el warning de "missing feature names"
        # y quede explícito qué columna es cuál.
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

    # El tope y el piso se aplican sobre el resultado final, sin importar
    # qué rama lo produjo: el Random Forest reproduce la misma explosión
    # que la heurística para combinaciones de poca constancia + mucho
    # peso pendiente (entrenó sobre esa misma fórmula), así que un fix
    # que solo tocara el `else` dejaría el problema vivo en la rama que
    # corre casi siempre hoy.
    days = min(days, MAX_DAYS_TO_GOAL)

    # Con menos de MIN_SESSIONS_FOR_RELIABLE_PREDICTION sesiones el
    # denominador de constancia es casi cero y cualquier número es ruido:
    # se devuelve None y el dashboard muestra un guion en su lugar.
    if member.workout_logs.count() < MIN_SESSIONS_FOR_RELIABLE_PREDICTION:
        days = None

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
