from django.test import TestCase, RequestFactory
from django.conf import settings
from django.contrib.sessions.middleware import SessionMiddleware
from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse

from .middleware import VisitorMiddleware, PageVisitMiddleware
from .models import Visitor, PageVisit

class TrackingMiddlewareTests(TestCase):

    def setUp(self):
        self.factory = RequestFactory()
        # Временно переопределим исключенные пути, чтобы протестировать исключение API
        self.original_prefixes = getattr(settings, 'TRACKING_EXCLUDED_PATH_PREFIXES', [])

    def tearDown(self):
        settings.TRACKING_EXCLUDED_PATH_PREFIXES = self.original_prefixes

    def _get_request(self, path):
        request = self.factory.get(path)
        # Имитируем сессию и пользователя
        middleware = SessionMiddleware(lambda r: HttpResponse())
        middleware.process_request(request)
        request.session.save()
        request.user = AnonymousUser()
        return request

    def _apply_middleware(self, request):
        # Имитируем реальный ответ, у которого есть метод set_cookie
        visitor_mw = VisitorMiddleware(lambda r: HttpResponse("OK"))
        page_mw = PageVisitMiddleware(visitor_mw)
        return page_mw(request)

    def test_visitor_created(self):
        request = self._get_request('/some-page/')
        self._apply_middleware(request)
        self.assertTrue(hasattr(request, 'visitor'))
        self.assertIsNotNone(request.visitor)
        self.assertEqual(Visitor.objects.count(), 1)

    def test_api_path_excluded(self):
        # Устанавливаем исключенные пути
        settings.TRACKING_EXCLUDED_PATH_PREFIXES = ['/api/']
        request = self._get_request('/api/v1/products/')
        self._apply_middleware(request)
        # visitor не должен создаваться, т.к. middleware пропускает
        # Проверим, что PageVisit не записан
        self.assertEqual(PageVisit.objects.count(), 0)

    def test_static_files_excluded(self):
        settings.TRACKING_EXCLUDED_PATH_PREFIXES = ['/static/']
        request = self._get_request('/static/css/style.css')
        self._apply_middleware(request)
        self.assertEqual(PageVisit.objects.count(), 0)
