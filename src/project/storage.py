from django.contrib.staticfiles.storage import ManifestStaticFilesStorage


class HashedStaticFilesStorage(ManifestStaticFilesStorage):
    """Content-hashed static file names, so nginx's `expires max` never serves an outdated file after a deploy.

    `support_js_module_import_aggregation` also rewrites `import … from "./easykitchen.js"` in the ES modules;
    without it a changed module would keep its old, cached name for every importer. Strict like Django's default:
    a reference to a missing file fails collectstatic (in the CI image probe), not a page in production.
    """

    support_js_module_import_aggregation = True
