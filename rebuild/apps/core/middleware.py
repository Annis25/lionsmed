class PrivateHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response["X-Robots-Tag"] = "noindex, nofollow"
        response["Cache-Control"] = "private, no-store"
        # Ne pas transmettre de jetons reset à un site tiers.
        response["Referrer-Policy"] = "same-origin"
        return response
