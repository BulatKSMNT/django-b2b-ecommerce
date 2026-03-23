from .services import get_active_profile


class ActiveProfileMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.profile = None

        if request.user.is_authenticated:
            request.profile = get_active_profile(request)

        response = self.get_response(request)
        return response
