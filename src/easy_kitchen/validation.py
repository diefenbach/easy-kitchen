"""Business input rules shared by Django services, DRF and MCP adapters."""

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator, URLValidator
from django.utils.translation import gettext as _

from .errors import ServiceError

NAME_LIMIT = 255
QUANTITY_LIMIT = 100
DESCRIPTION_LIMIT = 5000
STEP_LIMIT = 2000
IMAGE_URL_LIMIT = 500
COUNT_LIMIT = 2147483647
DEFAULT_LIST_LIMIT = 50
MAX_LIST_LIMIT = 200
NUTRITION_FIELDS = ("calories", "protein", "carbohydrates", "fat", "preparation_minutes")
RECIPE_FIELDS = ("title", "description", "image_url", *NUTRITION_FIELDS)


def clean_text(value, *, field, limit, required=False, normalize=False):
    if not isinstance(value, str):
        raise ServiceError(_("Invalid request."), field=field)
    value = " ".join(value.split()) if normalize else value.strip()
    if required and not value:
        message = _("Enter a title.") if field == "title" else _("This field cannot be blank.")
        raise ServiceError(message, field=field)
    try:
        MaxLengthValidator(limit)(value)
    except ValidationError as error:
        raise ServiceError(error.messages[0], field=field) from None
    return value


def clean_count(value):
    if value is None or value == "":
        return None
    try:
        if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
            raise ValueError
        number = Decimal(str(value))
        if not number.is_finite() or number != number.to_integral_value() or not 0 <= number <= COUNT_LIMIT:
            raise ValueError
        return int(number)
    except (ValueError, InvalidOperation):
        raise ServiceError(_("Enter zero or a positive whole number.")) from None


def clean_image_url(value):
    value = clean_text(value, field="image_url", limit=IMAGE_URL_LIMIT)
    if value:
        try:
            URLValidator(schemes=["http", "https"])(value)
        except ValidationError:
            raise ServiceError(_("Enter a valid image URL."), field="image_url") from None
    return value


def clean_recipe_changes(changes):
    allowed = {*RECIPE_FIELDS, "ingredients", "steps"}
    if set(changes) - allowed:
        raise ServiceError(_("Unsupported recipe field."))
    result = dict(changes)
    for field in ("title", "description"):
        if field in result:
            result[field] = clean_text(result[field], field=field,
                limit=NAME_LIMIT if field == "title" else DESCRIPTION_LIMIT,
                required=field == "title", normalize=field == "title")
    if "image_url" in result:
        result["image_url"] = clean_image_url(result["image_url"])
    for field in NUTRITION_FIELDS:
        if field in result:
            result[field] = clean_count(result[field])
    for field in ("ingredients", "steps"):
        if field not in result:
            continue
        if not isinstance(result[field], (list, tuple)):
            raise ServiceError(_("Invalid request."), field=field)
        lines = []
        for line in result[field]:
            if isinstance(line, str) and field == "steps":
                line = {"text": line}
            if not isinstance(line, dict):
                raise ServiceError(_("Invalid request."), field=field)
            line = dict(line)
            key = "name" if field == "ingredients" else "text"
            line[key] = clean_text(line.get(key, ""), field=key, required=True,
                                  normalize=True, limit=NAME_LIMIT if key == "name" else STEP_LIMIT)
            if field == "ingredients":
                line["quantity"] = clean_text(line.get("quantity", ""), field="quantity", limit=QUANTITY_LIMIT)
            lines.append(line)
        result[field] = lines
    return result
