"""Build a print-friendly PDF for one recipe."""

from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

import reportlab
from django.utils.translation import gettext as _
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer

from .models import Recipe

_FONT_NAME = "Vera"
_FONT_REGISTERED = False


def _ensure_font():
    global _FONT_REGISTERED
    if _FONT_REGISTERED:
        return
    font_path = Path(reportlab.__file__).resolve().parent / "fonts" / "Vera.ttf"
    pdfmetrics.registerFont(TTFont(_FONT_NAME, str(font_path)))
    _FONT_REGISTERED = True


def _paragraph(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(text).replace("\n", "<br/>"), style)


def _fact_lines(recipe: Recipe) -> list[str]:
    facts = []
    if recipe.calories is not None:
        facts.append(_("%(calories)s kcal") % {"calories": recipe.calories})
    if recipe.protein is not None:
        facts.append(_("%(protein)s g protein") % {"protein": recipe.protein})
    if recipe.carbohydrates is not None:
        facts.append(_("%(carbohydrates)s g carbohydrates") % {"carbohydrates": recipe.carbohydrates})
    if recipe.fat is not None:
        facts.append(_("%(fat)s g fat") % {"fat": recipe.fat})
    if recipe.preparation_minutes is not None:
        facts.append(_("%(minutes)s min") % {"minutes": recipe.preparation_minutes})
    return facts


def build_recipe_pdf(recipe: Recipe) -> bytes:
    """Return PDF bytes for this recipe (ingredients, steps, optional uploaded image)."""
    _ensure_font()
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        name="RecipeTitle",
        parent=styles["Heading1"],
        fontName=_FONT_NAME,
        fontSize=20,
        leading=24,
        spaceAfter=10,
    )
    heading_style = ParagraphStyle(
        name="SectionHeading",
        parent=styles["Heading2"],
        fontName=_FONT_NAME,
        fontSize=14,
        leading=18,
        spaceBefore=14,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        name="RecipeBody",
        parent=styles["BodyText"],
        fontName=_FONT_NAME,
        fontSize=11,
        leading=14,
        spaceAfter=4,
    )

    story = [_paragraph(recipe.title, title_style)]
    if recipe.description.strip():
        story.append(_paragraph(recipe.description.strip(), body_style))
        story.append(Spacer(1, 6))

    facts = _fact_lines(recipe)
    if facts:
        story.append(_paragraph(" · ".join(facts), body_style))
        story.append(Spacer(1, 8))

    if recipe.image:
        image = Image(recipe.image.path)
        max_width = 160 * mm
        if image.imageWidth > max_width:
            scale = max_width / image.imageWidth
            image.drawWidth = max_width
            image.drawHeight = image.imageHeight * scale
        story.extend([image, Spacer(1, 10)])

    story.append(_paragraph(_("Ingredients"), heading_style))
    ingredients = list(recipe.ingredients.all())
    if ingredients:
        for ingredient in ingredients:
            line = ingredient.name
            if ingredient.quantity:
                line = f"{ingredient.name} — {ingredient.quantity}"
            story.append(_paragraph(line, body_style))
    else:
        story.append(_paragraph(_("No ingredients yet."), body_style))

    story.append(_paragraph(_("Steps"), heading_style))
    steps = list(recipe.steps.all())
    if steps:
        for number, step in enumerate(steps, start=1):
            story.append(_paragraph(f"{number}. {step.text.strip()}", body_style))
    else:
        story.append(_paragraph(_("No steps yet."), body_style))

    doc.build(story)
    return buffer.getvalue()
