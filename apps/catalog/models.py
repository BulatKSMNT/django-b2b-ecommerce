from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from slugify import slugify


def generate_unique_slug(instance, source_value: str, *, scope_filters: dict | None = None) -> str:
    scope_filters = scope_filters or {}
    base_slug = slugify(source_value) or "item"
    slug = base_slug
    model_class = instance.__class__

    queryset = model_class._default_manager.filter(**scope_filters)
    if instance.pk:
        queryset = queryset.exclude(pk=instance.pk)

    counter = 2
    while queryset.filter(slug=slug).exists():
        slug = f"{base_slug}-{counter}"
        counter += 1

    return slug


class Category(models.Model):
    name = models.CharField("Название", max_length=255, unique=True)
    slug = models.SlugField("Slug", max_length=255, unique=True, blank=True)
    description = models.TextField("Описание", blank=True)
    image = models.ImageField("Изображение", upload_to="categories/", blank=True, null=True)
    is_active = models.BooleanField("Активна", default=True)
    sort_order = models.PositiveIntegerField("Порядок сортировки", default=0)
    created_at = models.DateTimeField("Создана", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлена", auto_now=True)

    class Meta:
        verbose_name = "Категория"
        verbose_name_plural = "Категории"
        ordering = ("sort_order", "name")

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = generate_unique_slug(self, self.name)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("catalog:product_list", kwargs={"category_slug": self.slug})


class Product(models.Model):
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name="products",
        verbose_name="Категория",
    )
    name = models.CharField("Название", max_length=255)
    slug = models.SlugField("Slug", max_length=255, blank=True)
    description = models.TextField("Описание", blank=True)
    price = models.DecimalField(
        "Цена",
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Если цена неизвестна, можно оставить пустой",
    )
    is_active = models.BooleanField("Активен", default=True)
    sort_order = models.PositiveIntegerField("Порядок сортировки", default=0)
    created_at = models.DateTimeField("Создан", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлён", auto_now=True)

    class Meta:
        verbose_name = "Товар"
        verbose_name_plural = "Товары"
        ordering = ("sort_order", "name")
        constraints = [
            models.UniqueConstraint(
                fields=("category", "slug"),
                name="unique_product_slug_per_category",
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = generate_unique_slug(
                self,
                self.name,
                scope_filters={"category": self.category},
            )
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse(
            "catalog:product_detail",
            kwargs={
                "category_slug": self.category.slug,
                "product_slug": self.slug,
            },
        )

    def get_main_image(self):
        images = list(self.images.all())
        if not images:
            return None

        for image in images:
            if image.is_primary:
                return image
        return images[0]


class ProductImage(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="images",
        verbose_name="Товар",
    )
    image = models.ImageField("Изображение", upload_to="products/")
    alt_text = models.CharField("Alt-текст", max_length=255, blank=True)
    is_primary = models.BooleanField("Основное", default=False)
    sort_order = models.PositiveIntegerField("Порядок сортировки", default=0)
    created_at = models.DateTimeField("Создано", auto_now_add=True)

    class Meta:
        verbose_name = "Изображение товара"
        verbose_name_plural = "Изображения товаров"
        ordering = ("sort_order", "id")

    def __str__(self) -> str:
        return self.alt_text or f"Изображение товара #{self.product_id}"

    def clean(self):
        if self.is_primary and self.product_id:
            queryset = ProductImage.objects.filter(product_id=self.product_id, is_primary=True)
            if self.pk:
                queryset = queryset.exclude(pk=self.pk)
            if queryset.exists():
                raise ValidationError("У товара уже есть основное изображение.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class Attribute(models.Model):
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name="attributes",
        verbose_name="Категория",
    )
    name = models.CharField("Название характеристики", max_length=255)
    sort_order = models.PositiveIntegerField("Порядок сортировки", default=0)
    is_active = models.BooleanField("Активна", default=True)

    class Meta:
        verbose_name = "Характеристика"
        verbose_name_plural = "Характеристики"
        ordering = ("sort_order", "name")
        constraints = [
            models.UniqueConstraint(
                fields=("category", "name"),
                name="unique_attribute_name_per_category",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.category.name} — {self.name}"


class ProductAttributeValue(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="attribute_values",
        verbose_name="Товар",
    )
    attribute = models.ForeignKey(
        Attribute,
        on_delete=models.CASCADE,
        related_name="product_values",
        verbose_name="Характеристика",
    )
    value = models.CharField("Значение", max_length=255)

    class Meta:
        verbose_name = "Значение характеристики"
        verbose_name_plural = "Значения характеристик"
        constraints = [
            models.UniqueConstraint(
                fields=("product", "attribute"),
                name="unique_attribute_per_product",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.product.name}: {self.attribute.name} = {self.value}"

    def clean(self):
        if self.product_id and self.attribute_id:
            if self.product.category_id != self.attribute.category_id:
                raise ValidationError("Характеристика должна принадлежать той же категории, что и товар.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
