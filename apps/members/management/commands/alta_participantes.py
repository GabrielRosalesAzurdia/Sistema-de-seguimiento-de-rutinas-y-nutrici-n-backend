"""
Alta masiva de participantes reales del estudio.

No existe un endpoint de API que cree un `User` (cuenta de login) con
contraseña propia — esa lógica vive solo en la vista HTML del panel
(`apps.panel.views.MemberFormActionMixin`, sesión + CSRF). Este comando
replica la misma lógica vía ORM y corre localmente contra la base que
tenga activo el shell (local/Docker o Neon, ver CLAUDE.md sección 11
para apuntar a Neon con variables DB_*) — no hace peticiones HTTP.

Uso:
    python manage.py alta_participantes ruta/participantes.json
    python manage.py alta_participantes ruta/participantes.json --ejecutar

Por defecto corre en dry-run (no escribe nada, solo reporta lo que
haría). Con --ejecutar sí crea usuarios/miembros/mediciones reales.
"""
import csv
import json
import unicodedata
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.members.models import ActivityLevel, FitnessGoal, Gender, Member, User
from apps.nutrition.services import IncompleteProfileError, generate_plan_for_member
from apps.panel.utils import add_one_month
from apps.tracking.models import BodyMeasurementLog

# Fallback cuando el registro no trae dias_comidas (algunos sí lo
# traen, otros no) — decisión del coach: dejarlo fijo en 3 en ese caso.
DEFAULT_PLANNED_NUTRITION_DAYS = 3

# dias_entreno y dias_comidas pueden venir como ritmo semanal (<=7) o
# ya como total mensual (>7) — decisión del coach: si es semanal,
# multiplicar para cubrir un mes (~4 semanas); si ya es mensual, usarlo
# tal cual.
WEEKS_PER_MONTH = 4

# Las 10 circunferencias del JSON no incluyen cuello (neck_cm) — sin
# eso, %grasa/%agua quedan en None hasta que el coach mida el cuello
# (Member.save() ya maneja ese caso, no hace falta lógica extra acá).
MEASUREMENT_FIELD_MAP = {
    "brazo_izq": "left_arm_cm",
    "brazo_der": "right_arm_cm",
    "pierna_izq": "left_leg_cm",
    "pierna_der": "right_leg_cm",
    "pantorrilla_izq": "left_calf_cm",
    "pantorrilla_der": "right_calf_cm",
    "cintura": "waist_cm",
    "pecho": "chest_cm",
    "cadera": "hip_cm",
    "espalda": "back_cm",
}

REQUIRED_RAW_FIELDS = [
    "correo_app", "password_temporal", "nombre_completo", "edad", "estatura_cm", "dias_entreno",
]


def _normalize(value):
    if value is None:
        return ""
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return text.strip().upper().replace(" ", "_")


GENDER_MAP = {
    "HOMBRE": Gender.HOMBRE, "MASCULINO": Gender.HOMBRE, "M": Gender.HOMBRE,
    "MUJER": Gender.MUJER, "FEMENINO": Gender.MUJER, "F": Gender.MUJER,
}

GOAL_MAP = {
    "GANAR_PESO": FitnessGoal.GANAR_PESO,
    "AUMENTAR_PESO": FitnessGoal.GANAR_PESO,
    "SUBIR_DE_PESO": FitnessGoal.GANAR_PESO,
    # "Ganar masa muscular" no tiene opción propia en el modelo — se
    # acerca más a Ganar peso (calóricamente) que a Mantener (decisión
    # confirmada con el coach).
    "GANAR_MASA_MUSCULAR": FitnessGoal.GANAR_PESO,
    "PERDER_PESO": FitnessGoal.PERDER_PESO,
    "BAJAR_DE_PESO": FitnessGoal.PERDER_PESO,
    "ADELGAZAR": FitnessGoal.PERDER_PESO,
    "MANTENER_PESO": FitnessGoal.MANTENER_PESO,
    "MANTENIMIENTO": FitnessGoal.MANTENER_PESO,
    "TONIFICAR": FitnessGoal.TONIFICAR,
    # "Perder peso y ganar masa muscular" (recomposición corporal) se
    # trata como Tonificar — que ya recibe el mismo tratamiento que
    # Perder peso en el cálculo de macros (decisión confirmada con el coach).
    "PERDER_PESO_Y_GANAR_MASA_MUSCULAR": FitnessGoal.TONIFICAR,
}

ACTIVITY_MAP = {
    "SEDENTARIO": ActivityLevel.SEDENTARIO,
    "MODERADO": ActivityLevel.MODERADO,
    "ACTIVO": ActivityLevel.ACTIVO,
    "MUY_ACTIVO": ActivityLevel.MUY_ACTIVO,
}


class RecordError(Exception):
    """Datos insuficientes o inválidos para procesar el registro — se
    reporta y se sigue con el siguiente participante."""


def _decimal(value):
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        raise RecordError(f"valor numérico inválido: {value!r}")


def _scale_weekly_to_month(value):
    """dias_entreno/dias_comidas pueden venir como ritmo semanal (<=7)
    o ya como total mensual (>7) — si es semanal, se multiplica para
    cubrir un mes (~4 semanas); si ya es mensual, se usa tal cual.
    Devuelve (valor_mensual: int, fue_escalado: bool)."""
    if value <= 7:
        return int(round(value * WEEKS_PER_MONTH)), True
    return int(round(value)), False


def build_plan(record):
    """Calcula, sin tocar la base, todo lo que se crearía para un
    participante. Devuelve (payload: dict, warnings: list[str])."""

    warnings = []

    missing = [f for f in REQUIRED_RAW_FIELDS if record.get(f) in (None, "")]
    if missing:
        raise RecordError(f"faltan campos requeridos: {', '.join(missing)}")

    correo = record["correo_app"].strip()
    password = record["password_temporal"]

    nombre_completo = record["nombre_completo"].strip()
    words = nombre_completo.split()
    if len(words) == 4:
        first_name, second_name, first_last_name, second_last_name = words
    else:
        first_name, second_name, first_last_name, second_last_name = nombre_completo, "", "", ""
        warnings.append(
            "nombre_completo no tiene 4 palabras — revisar y partir manualmente en el panel"
        )

    genero_norm = _normalize(record.get("genero"))
    gender = GENDER_MAP.get(genero_norm)
    if record.get("genero") and gender is None:
        warnings.append(f"género no reconocido ({record['genero']!r}) — se dejó sin asignar")

    objetivo_norm = _normalize(record.get("objetivo"))
    fitness_goal = GOAL_MAP.get(objetivo_norm)
    if fitness_goal is None:
        if record.get("objetivo"):
            warnings.append(
                f"objetivo no reconocido ({record['objetivo']!r}) — se usó MANTENER_PESO"
            )
        fitness_goal = FitnessGoal.MANTENER_PESO

    nivel_norm = _normalize(record.get("nivel_actividad"))
    activity_level = ACTIVITY_MAP.get(nivel_norm)
    if activity_level is None:
        if record.get("nivel_actividad"):
            warnings.append(
                f"nivel_actividad no reconocido ({record['nivel_actividad']!r}) — se usó MODERADO"
            )
        activity_level = ActivityLevel.MODERADO

    dias_entreno = _decimal(record["dias_entreno"])
    planned_training_days, scaled = _scale_weekly_to_month(dias_entreno)
    if scaled:
        warnings.append(
            f"dias_entreno={dias_entreno} tratado como ritmo semanal -> "
            f"planned_training_days={planned_training_days} (x{WEEKS_PER_MONTH} semanas)"
        )

    dias_comidas_raw = record.get("dias_comidas")
    if dias_comidas_raw is not None:
        dias_comidas = _decimal(dias_comidas_raw)
        planned_nutrition_days, scaled_comidas = _scale_weekly_to_month(dias_comidas)
        if scaled_comidas:
            warnings.append(
                f"dias_comidas={dias_comidas} tratado como ritmo semanal -> "
                f"planned_nutrition_days={planned_nutrition_days} (x{WEEKS_PER_MONTH} semanas)"
            )
    else:
        planned_nutrition_days = DEFAULT_PLANNED_NUTRITION_DAYS
        warnings.append(
            f"sin dias_comidas — planned_nutrition_days se dejó en {DEFAULT_PLANNED_NUTRITION_DAYS} (valor por defecto)"
        )

    fecha_medicion_raw = record.get("fecha_medicion")
    fecha_medicion = parse_date(fecha_medicion_raw) if fecha_medicion_raw else None
    if fecha_medicion_raw and fecha_medicion is None:
        warnings.append(f"fecha_medicion inválida ({fecha_medicion_raw!r}), se ignoró")

    start_date = fecha_medicion or timezone.localdate()
    if fecha_medicion is None:
        warnings.append(f"sin fecha_medicion utilizable — start_date se puso en hoy ({start_date})")

    ultima_mensualidad_raw = record.get("ultima_mensualidad")
    last_payment_date = parse_date(ultima_mensualidad_raw) if ultima_mensualidad_raw else None
    if ultima_mensualidad_raw and last_payment_date is None:
        warnings.append(f"ultima_mensualidad inválida ({ultima_mensualidad_raw!r}), se ignoró")

    is_paid = last_payment_date is not None
    next_payment_date = add_one_month(last_payment_date or start_date)
    if last_payment_date:
        warnings.append(f"ultima_mensualidad={last_payment_date} -> is_paid=True, próximo pago {next_payment_date}")

    member_fields = {
        "first_name": first_name,
        "second_name": second_name,
        "first_last_name": first_last_name,
        "second_last_name": second_last_name,
        "phone": (record.get("telefono") or "").strip(),
        "age": int(record["edad"]),
        "height_cm": _decimal(record["estatura_cm"]),
        "gender": gender,
        "goal_weight_kg": _decimal(record.get("peso_meta_kg")),
        "fitness_goal": fitness_goal,
        "activity_level": activity_level,
        "start_date": start_date,
        "next_payment_date": next_payment_date,
        "last_payment_date": last_payment_date,
        "is_paid": is_paid,
        "planned_training_days": planned_training_days,
        "planned_nutrition_days": planned_nutrition_days,
        "participates_in_study": bool(record.get("en_estudio", True)),
        "informed_consent_signed": bool(record.get("consentimiento", False)),
    }

    circumferences = {}
    for json_key, model_field in MEASUREMENT_FIELD_MAP.items():
        value = record.get(json_key)
        if value is not None:
            circumferences[model_field] = _decimal(value)
    if len(circumferences) < len(MEASUREMENT_FIELD_MAP):
        faltantes = [k for k in MEASUREMENT_FIELD_MAP if record.get(k) is None]
        warnings.append(f"circunferencias sin dato (quedan pendientes): {', '.join(faltantes)}")
    warnings.append("cuello (neck_cm) no viene en el JSON — %grasa/%agua quedan en None hasta que el coach lo mida")

    peso_kg = record.get("peso_kg")
    current_weight_kg = _decimal(peso_kg)

    measurement = None
    if fecha_medicion is not None and current_weight_kg is not None:
        measurement = {"date": fecha_medicion, "weight_kg": current_weight_kg}
    else:
        warnings.append("medición inicial pendiente (falta fecha_medicion o peso_kg)")

    return {
        "correo": correo,
        "password": password,
        "member_fields": member_fields,
        "circumferences": circumferences,
        "current_weight_kg": current_weight_kg,
        "measurement": measurement,
        "notas_salud": record.get("notas_salud") or "",
    }, warnings


def apply_plan(payload):
    """Ejecuta el plan calculado por build_plan(): crea User, Member y,
    si hay datos suficientes, el BodyMeasurementLog inicial — mismo
    orden de efectos que el flujo del panel (Agregar Miembro + primera
    Actualización de datos fitness)."""

    user = User(
        username=payload["correo"],
        email=payload["correo"],
        is_staff=False,
        must_change_password=True,
    )
    user.set_password(payload["password"])
    user.save()

    member = Member.objects.create(user=user, **payload["member_fields"])

    if payload["circumferences"] or payload["current_weight_kg"] is not None:
        for field, value in payload["circumferences"].items():
            setattr(member, field, value)
        if payload["current_weight_kg"] is not None:
            member.current_weight_kg = payload["current_weight_kg"]
        member.save()

    if payload["measurement"]:
        BodyMeasurementLog.objects.create(
            member=member,
            recorded_by=None,
            date=payload["measurement"]["date"],
            weight_kg=payload["measurement"]["weight_kg"],
            body_fat_percentage=member.body_fat_percentage,
            body_water_percentage=member.body_water_percentage,
        )
        try:
            generate_plan_for_member(member)
        except IncompleteProfileError:
            pass

    return member


# Nunca se tocan en una actualización: start_date es inmutable una vez
# creado el miembro (regla de negocio), y las credenciales de acceso
# (User.password/must_change_password/email) solo cambian por el flujo
# dedicado de "Generar nueva contraseña" del panel, no por este script.
UPDATE_PROTECTED_FIELDS = {"start_date"}


def compute_diff(member, payload):
    """Compara member_fields/circunferencias/peso del payload contra los
    valores ya guardados en `member`. No escribe nada — devuelve
    (diffs: {campo: (viejo, nuevo)}, necesita_medicion_nueva: bool)."""

    diffs = {}
    for field, new_value in {**payload["member_fields"], **payload["circumferences"]}.items():
        if field in UPDATE_PROTECTED_FIELDS:
            continue
        old_value = getattr(member, field)
        if old_value != new_value:
            diffs[field] = (old_value, new_value)

    if payload["current_weight_kg"] is not None and member.current_weight_kg != payload["current_weight_kg"]:
        diffs["current_weight_kg"] = (member.current_weight_kg, payload["current_weight_kg"])

    needs_new_measurement = False
    if payload["measurement"]:
        exists = BodyMeasurementLog.objects.filter(
            member=member, date=payload["measurement"]["date"]
        ).exists()
        needs_new_measurement = not exists

    return diffs, needs_new_measurement


def describe_diff(diffs, needs_new_measurement, payload):
    parts = [f"{field}: {old!r} -> {new!r}" for field, (old, new) in diffs.items()]
    if needs_new_measurement:
        parts.append(
            f"nueva medición {payload['measurement']['date']} "
            f"({payload['measurement']['weight_kg']}kg)"
        )
    return "; ".join(parts)


def apply_update(member, payload, diffs, needs_new_measurement):
    """Aplica lo que ya calculó compute_diff(): actualiza solo los
    campos que cambiaron y, si corresponde, agrega un BodyMeasurementLog
    nuevo (nunca sobreescribe uno existente en la misma fecha) — mismo
    patrón que 'Actualizar datos fitness' del panel, incluida la dieta
    automática si es el primer peso real que se le registra."""

    is_first_weight = needs_new_measurement and not member.nutrition_plans.exists()

    if diffs:
        for field, (_old, new_value) in diffs.items():
            setattr(member, field, new_value)
        member.save()

    if needs_new_measurement:
        BodyMeasurementLog.objects.create(
            member=member,
            recorded_by=None,
            date=payload["measurement"]["date"],
            weight_kg=payload["measurement"]["weight_kg"],
            body_fat_percentage=member.body_fat_percentage,
            body_water_percentage=member.body_water_percentage,
        )
        if is_first_weight:
            try:
                generate_plan_for_member(member)
            except IncompleteProfileError:
                pass


def _json_default(value):
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


class Command(BaseCommand):
    help = (
        "Da de alta (User + Member + medición inicial) a los participantes reales "
        "del JSON con crear_cuenta=true. Dry-run por defecto; usa --ejecutar para "
        "escribir de verdad. No pega contra ningún API: corre vía ORM contra la base "
        "que tenga activo el shell (ver CLAUDE.md sección 11 para apuntar a Neon)."
    )

    def add_arguments(self, parser):
        parser.add_argument("json_path", help="Ruta al JSON de participantes")
        parser.add_argument(
            "--ejecutar", action="store_true",
            help="Escribe de verdad. Sin esta bandera, solo reporta (dry-run).",
        )
        parser.add_argument(
            "--reporte", default="reporte_alta.csv",
            help="Ruta del CSV de salida (default: reporte_alta.csv)",
        )
        parser.add_argument(
            "--mostrar", default=None,
            help="En dry-run, imprime el payload completo (JSON) del correo_app indicado.",
        )
        parser.add_argument(
            "--actualizar", action="store_true",
            help=(
                "Para correos que ya tienen cuenta, compara sus datos contra el JSON y "
                "actualiza los campos que cambiaron (nunca start_date ni la contraseña). "
                "Sin esta bandera, un correo existente se reporta como 'ya existía' y no se toca."
            ),
        )

    def handle(self, *args, json_path, ejecutar, reporte, mostrar, actualizar, **options):
        try:
            with open(json_path, encoding="utf-8") as fh:
                data = json.load(fh)
        except FileNotFoundError as exc:
            raise CommandError(f"No se encontró el archivo: {json_path}") from exc
        except json.JSONDecodeError as exc:
            raise CommandError(f"JSON inválido en {json_path}: {exc}") from exc

        # El archivo real es un objeto con metadata (generado, criterio_de_alta,
        # resumen, unidades) + la lista de participantes bajo "participantes" —
        # no una lista plana.
        records = data["participantes"] if isinstance(data, dict) else data

        modo = "EJECUTAR (escribiendo en la base)" if ejecutar else "DRY-RUN (no se escribe nada)"
        self.stdout.write(self.style.WARNING(f"Modo: {modo}"))

        rows = []
        for record in records:
            correo = record.get("correo_app", "")
            nombre = record.get("nombre_completo", "")
            notas_salud = record.get("notas_salud") or ""

            # El JSON puede traer "accion" ("crear"/"actualizar"/"sin cambios"/
            # "pendiente") — cuando viene, es la fuente de verdad y manda por
            # encima de crear_cuenta/--actualizar (el coach ya decidió qué
            # hacer con cada quien). Si no viene (JSON más viejo), se cae al
            # comportamiento legado basado en crear_cuenta + --actualizar.
            accion = record.get("accion")

            if accion in ("sin cambios", "pendiente"):
                rows.append([correo, nombre, "omitido", f"accion={accion}", notas_salud])
                continue

            if accion is not None and accion not in ("crear", "actualizar"):
                rows.append([correo, nombre, "error", f"accion desconocida: {accion!r}", notas_salud])
                continue

            if accion is None and not record.get("crear_cuenta"):
                rows.append([correo, nombre, "omitido", "crear_cuenta=false", notas_salud])
                continue

            if not record.get("consentimiento"):
                rows.append([
                    correo, nombre, "omitido",
                    "sin consentimiento firmado (consentimiento=false) — no se crea/actualiza la cuenta",
                    notas_salud,
                ])
                continue

            existing_user = User.objects.filter(email=correo).first() if correo else None

            if accion == "crear" and existing_user:
                rows.append([
                    correo, nombre, "error",
                    "accion=crear pero el correo ya tiene cuenta — revisar el JSON", notas_salud,
                ])
                continue

            if accion == "actualizar" and not existing_user:
                rows.append([
                    correo, nombre, "error",
                    "accion=actualizar pero el correo todavía no tiene cuenta — revisar el JSON", notas_salud,
                ])
                continue

            if existing_user and accion is None and not actualizar:
                rows.append([correo, nombre, "ya existía", "", notas_salud])
                continue

            try:
                payload, warnings = build_plan(record)
            except RecordError as exc:
                rows.append([correo, nombre, "error", str(exc), notas_salud])
                self.stdout.write(self.style.ERROR(f"{correo or nombre}: {exc}"))
                continue

            if mostrar and correo == mostrar:
                self.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False, default=_json_default))

            detalle = "; ".join(warnings)

            if existing_user:
                member = existing_user.member_profile
                diffs, needs_new_measurement = compute_diff(member, payload)
                if not diffs and not needs_new_measurement:
                    rows.append([correo, nombre, "sin cambios", detalle, notas_salud])
                    continue

                cambios = describe_diff(diffs, needs_new_measurement, payload)
                if not ejecutar:
                    rows.append([correo, nombre, "actualizaría", cambios, notas_salud])
                    continue

                try:
                    with transaction.atomic():
                        apply_update(member, payload, diffs, needs_new_measurement)
                    rows.append([correo, nombre, "actualizado", cambios, notas_salud])
                    self.stdout.write(self.style.SUCCESS(f"{correo}: actualizado ({cambios})"))
                except Exception as exc:  # noqa: BLE001 - no abortar la corrida por un registro
                    rows.append([correo, nombre, "error", str(exc), notas_salud])
                    self.stdout.write(self.style.ERROR(f"{correo}: {exc}"))
                continue

            if not ejecutar:
                rows.append([correo, nombre, "dry-run", detalle, notas_salud])
                continue

            try:
                with transaction.atomic():
                    apply_plan(payload)
                rows.append([correo, nombre, "creado", detalle, notas_salud])
                self.stdout.write(self.style.SUCCESS(f"{correo}: creado"))
            except Exception as exc:  # noqa: BLE001 - no abortar la corrida por un registro
                rows.append([correo, nombre, "error", str(exc), notas_salud])
                self.stdout.write(self.style.ERROR(f"{correo}: {exc}"))

        with open(reporte, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["correo", "nombre_completo", "resultado", "detalle", "notas_salud"])
            writer.writerows(rows)

        self.stdout.write(self.style.SUCCESS(f"Reporte escrito en {reporte} ({len(rows)} filas)"))
