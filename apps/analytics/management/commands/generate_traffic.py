import random
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction

from apps.catalog.models import Product
from apps.tracking.models import PageVisit, UserEvent, Visitor
from apps.leads.models import Lead, LeadItem
from apps.analytics.services import score_lead


class Command(BaseCommand):
    help = "Генерирует тестовый трафик и заявки для красивого дашборда"

    def handle(self, *args, **options):
        products = list(Product.objects.filter(is_active=True))
        if not products:
            self.stdout.write(self.style.ERROR("Сначала загрузите каталог товаров!"))
            return

        self.stdout.write("Начинаем генерацию трафика за последние 7 дней...")
        now = timezone.now()

        with transaction.atomic():
            # 1. Создаем 20 случайных посетителей
            visitors = [Visitor.objects.create() for _ in range(20)]

            # 2. Генерируем 300 случайных просмотров страниц
            paths = ["/", "/catalog/", "/about/", "/contacts/", "/delivery-payment/"]
            for _ in range(300):
                random_date = now - timedelta(days=random.randint(0, 7), hours=random.randint(0, 23),
                                              minutes=random.randint(0, 59))
                PageVisit.objects.create(
                    visitor=random.choice(visitors),
                    path=random.choice(paths),
                    status_code=200,
                    duration_ms=random.randint(100, 5000)
                ).created_at = random_date
                # (Хак: дата переопределится авто-полем, поэтому обновим через update)

            # 3. Генерируем просмотры товаров и добавления в корзину
            for _ in range(150):
                visitor = random.choice(visitors)
                product = random.choice(products)
                event_type = random.choice([UserEvent.EventType.PRODUCT_VIEW, UserEvent.EventType.CART_ADD])

                # Добавляем событие
                UserEvent.objects.create(
                    visitor=visitor,
                    product=product,
                    event_type=event_type,
                    path=f"/catalog/item/{product.slug}/"
                )

            # 4. Генерируем 15 случайных заявок (Лидов)
            for i in range(15):
                random_date = now - timedelta(days=random.randint(0, 7), hours=random.randint(0, 23))
                visitor = random.choice(visitors)

                lead = Lead.objects.create(
                    visitor=visitor,
                    source=random.choice([Lead.Source.CART, Lead.Source.PRODUCT, Lead.Source.CONTACT]),
                    status=random.choice([Lead.Status.NEW, Lead.Status.IN_PROGRESS, Lead.Status.COMPLETED]),
                    fullname=f"Тестовый Клиент {i}",
                    phone_number="+79990001122",
                    email=f"client{i}@mail.ru",
                )
                # Меняем дату создания (обход auto_now_add)
                Lead.objects.filter(pk=lead.pk).update(created_at=random_date)

                # Добавляем товары в заявку
                if lead.source in [Lead.Source.CART, Lead.Source.PRODUCT]:
                    for _ in range(random.randint(1, 4)):
                        prod = random.choice(products)
                        LeadItem.objects.create(
                            lead=lead,
                            product=prod,
                            product_name=prod.name,
                            quantity=random.randint(1, 10),
                            product_price=prod.price,
                            line_total=(prod.price or 0) * 2
                        )

                # Запускаем ML-скоринг для заявки, чтобы она попала в блок "Горячие лиды"
                score_lead(lead)

        # Хак для обновления дат у PageVisit и UserEvent (так как auto_now_add мешает при создании)
        for model in [PageVisit, UserEvent]:
            items = model.objects.all()
            for item in items:
                fake_date = now - timedelta(days=random.randint(0, 7), hours=random.randint(0, 23))
                model.objects.filter(pk=item.pk).update(created_at=fake_date)

        self.stdout.write(self.style.SUCCESS("Трафик успешно сгенерирован! Обновите дашборд."))
