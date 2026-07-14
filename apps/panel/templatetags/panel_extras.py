from django import template

register = template.Library()


@register.filter
def get_item(mapping, key):
    """Acceso a dict[key] desde el template (Django no lo permite
    nativamente con variables dinámicas como clave)."""
    if mapping is None:
        return None
    return mapping.get(key)
