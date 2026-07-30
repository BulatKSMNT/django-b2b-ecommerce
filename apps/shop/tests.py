from django.test import TestCase, RequestFactory
from django.contrib.sessions.middleware import SessionMiddleware
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth import get_user_model

from .services import add_product_to_cart, get_cart_data, clear_cart, merge_session_shop_state_to_profile
from apps.catalog.models import Category, Product
from apps.accounts.models import Profile

User = get_user_model()

class CartServiceTests(TestCase):

    def setUp(self):
        self.factory = RequestFactory()
        self.category = Category.objects.create(name="Test Cat", is_active=True)
        self.product = Product.objects.create(category=self.category, name="Prod", price=100.00, is_active=True)

    def _get_request(self, user=None):
        request = self.factory.get('/')
        middleware = SessionMiddleware(lambda r: None)
        middleware.process_request(request)
        request.session.save()
        
        if user:
            request.user = user
            profile = Profile.objects.filter(user=user, is_default=True).first()
            if not profile:
                profile = Profile.objects.create(user=user, name="Default", is_default=True)
            request.profile = profile
        else:
            request.user = AnonymousUser()
            
        return request

    def test_add_to_cart_guest(self):
        request = self._get_request()
        add_product_to_cart(request, self.product, quantity=2)
        cart_data = get_cart_data(request)
        self.assertEqual(cart_data['total_quantity'], 2)
        self.assertEqual(len(cart_data['items']), 1)
        self.assertEqual(cart_data['items'][0]['quantity'], 2)

    def test_add_to_cart_authenticated(self):
        user = User.objects.create_user(username="user1", email="user1@test.com")
        request = self._get_request(user)
        add_product_to_cart(request, self.product, quantity=3)
        cart_data = get_cart_data(request)
        self.assertEqual(cart_data['total_quantity'], 3)

    def test_merge_guest_cart_to_profile(self):
        # 1. Гость собирает корзину
        guest_request = self._get_request()
        add_product_to_cart(guest_request, self.product, quantity=2)
        guest_cart = get_cart_data(guest_request)
        self.assertEqual(guest_cart['total_quantity'], 2)

        # 2. Создаем пользователя и получаем его активный запрос с профилем
        user = User.objects.create_user(username="user2", email="user2@test.com")
        request = self._get_request(user)
        profile = request.profile
        
        # 3. Мержим гостевую сессию в этот профиль
        merge_session_shop_state_to_profile(guest_request, profile)
        
        # 4. Проверяем корзину
        cart_data = get_cart_data(request)
        self.assertEqual(cart_data['total_quantity'], 2)
