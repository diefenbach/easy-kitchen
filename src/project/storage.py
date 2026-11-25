"""Static file storage used in production."""

from django.contrib.staticfiles.storage import ManifestStaticFilesStorage


class HashedStaticFilesStorage(ManifestStaticFilesStorage):
    """Content-hashed static file names, so nginx's `expires max` never serves an outdated file after a deploy.

    `support_js_module_import_aggregation` also rewrites `import … from "./easykitchen.js"` in the ES modules;
    without it a changed module would keep its old, cached name for every importer. Strict like Django's default:
    a CSS url() to a missing file fails collectstatic (in the CI image probe). collectstatic does not read
    templates; test_every_static_path_in_the_templates_is_collected checks their {% static %} paths.
    """

    support_js_module_import_aggregation = True
