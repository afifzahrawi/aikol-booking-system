from .models import SiteContent


def site_content(request):
    """Header and footer wording, available to every template."""
    return {"site": SiteContent.load()}
