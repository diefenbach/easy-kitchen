from io import BytesIO

import pytest
from django.core.files.base import ContentFile
from PIL import Image

from easy_kitchen.recipe_pdf import build_recipe_pdf
from easy_kitchen.services import (
    create_recipe,
)


@pytest.mark.django_db
@pytest.mark.parametrize("size", [(100, 1500), (4000, 100), (2000, 3000)])
def test_recipe_pdf_fits_tall_and_wide_images(user, settings, tmp_path, size):
    settings.STORAGES = {"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}}
    settings.MEDIA_ROOT = tmp_path
    recipe = create_recipe(user, title="Image test", steps=["Cook"])
    image = BytesIO()
    Image.new("RGB", size, color="white").save(image, format="PNG")
    recipe.image.save("recipe.png", ContentFile(image.getvalue()))
    assert build_recipe_pdf(recipe).startswith(b"%PDF")

