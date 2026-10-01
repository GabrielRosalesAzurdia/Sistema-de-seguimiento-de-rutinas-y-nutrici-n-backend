"""Cálculo de % de grasa (U.S. Navy Method, Hodgdon & Beckett 1984) y % de agua corporal a partir de las medidas que registra el coach."""
import math

LEAN_MASS_WATER_FACTOR = 0.73


def calculate_body_fat_percentage(*, gender, waist_cm, neck_cm, height_cm, hip_cm=None):
    """Devuelve el % de grasa corporal (U.S. Navy Method) o None si faltan medidas requeridas."""
    if not (gender and waist_cm and neck_cm and height_cm):
        return None

    waist_cm = float(waist_cm)
    neck_cm = float(neck_cm)
    height_cm = float(height_cm)

    if gender == "MUJER":
        if not hip_cm:
            return None
        hip_cm = float(hip_cm)
        circumference_term = waist_cm + hip_cm - neck_cm
        if circumference_term <= 0:
            return None
        body_fat = (
            495
            / (
                1.29579
                - 0.35004 * math.log10(circumference_term)
                + 0.22100 * math.log10(height_cm)
            )
            - 450
        )
    else:
        circumference_term = waist_cm - neck_cm
        if circumference_term <= 0:
            return None
        body_fat = (
            495
            / (
                1.0324
                - 0.19077 * math.log10(circumference_term)
                + 0.15456 * math.log10(height_cm)
            )
            - 450
        )

    return round(body_fat, 1)


def calculate_body_water_percentage(body_fat_percentage):
    """Estima % de agua corporal a partir del % de grasa ya calculado (masa magra ≈ 73% agua)."""
    if body_fat_percentage is None:
        return None
    lean_mass_percentage = 100 - float(body_fat_percentage)
    return round(lean_mass_percentage * LEAN_MASS_WATER_FACTOR, 1)


def calculate_body_composition(member):
    """Calcula (% grasa, % agua) para un Member; devuelve (None, None) si faltan medidas requeridas."""
    body_fat = calculate_body_fat_percentage(
        gender=member.gender,
        waist_cm=member.waist_cm,
        neck_cm=member.neck_cm,
        height_cm=member.height_cm,
        hip_cm=member.hip_cm,
    )
    body_water = calculate_body_water_percentage(body_fat)
    return body_fat, body_water
