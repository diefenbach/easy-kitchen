from django.conf import settings
from django.db import migrations


def verify_existing_user_emails(apps, schema_editor):
    """Let accounts created before email login sign in with the address an admin already set.

    Users without an email address, or whose address another user already claimed, are skipped
    and need an address set in the admin before they can sign in.
    """
    User = apps.get_model(settings.AUTH_USER_MODEL)
    EmailAddress = apps.get_model("account", "EmailAddress")
    claimed = {email.lower() for email in EmailAddress.objects.values_list("email", flat=True)}
    for user in User.objects.exclude(email="").order_by("pk"):
        email = user.email.strip().lower()
        if not email or email in claimed or EmailAddress.objects.filter(user=user).exists():
            continue
        EmailAddress.objects.create(user=user, email=email, verified=True, primary=True)
        claimed.add(email)


class Migration(migrations.Migration):
    dependencies = [
        ("shopping", "0019_require_department_owner"),
        ("account", "0009_emailaddress_unique_primary_email"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [migrations.RunPython(verify_existing_user_emails, migrations.RunPython.noop)]
