from .runtime import sync_if_due


class TranslationSyncMiddleware:
    """Load newly published translations before the request's language is activated.

    Place it before ``LocaleMiddleware``.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        sync_if_due()
        return self.get_response(request)
