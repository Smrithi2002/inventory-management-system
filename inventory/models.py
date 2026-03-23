from django.db import models
from django.core.exceptions import ValidationError
from datetime import date
from decimal import Decimal

class Tax(models.Model):
    name = models.CharField(max_length=100)
    percentage = models.DecimalField(max_digits=5, decimal_places=2, help_text="Enter as percentage, e.g., 5.00")
    is_compound = models.BooleanField(default=False, help_text="If True, calculated on top of base amount + single taxes")
    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=1)

    def __str__(self):
        status = "" if self.is_active else " (Inactive)"
        return f"{self.name} ({self.percentage}%){status}"

    class Meta:
        ordering = ['order']

    def clean(self):
        from .models import PurchaseItem

        # Prevent modifying percentage if used in transactions
        if self.pk:
            old_tax = Tax.objects.get(pk=self.pk)
            if old_tax.percentage != self.percentage and PurchaseItem.objects.filter(product__taxes=self).exists():
                raise ValidationError(
                    "Cannot modify the percentage of a tax used in transactions. Create a new one."
                )

        # Compound tax must not be first
        if self.is_compound and self.order == 1:
            raise ValidationError(
                "Compound tax must have order greater than 1."
            )   

class Product(models.Model):
    CATEGORY_CHOICES = [
        ('general', 'General'),
        ('pharma', 'Pharmaceutical'),
        ('fmcg', 'FMCG'),
        ('electronics', 'Electronics'),
        ('raw_material', 'Raw Material'),
    ]

    name = models.CharField(max_length=100)
    sku = models.CharField(max_length=50, unique=True)
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default='general')
    cost_price = models.DecimalField(max_digits=10, decimal_places=2)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2)
    taxes = models.ManyToManyField(Tax) 
    is_lot_tracked = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.sku})"

    def can_delete(self):
        return not self.purchaseitem_set.exists()


class Supplier(models.Model):
    name = models.CharField(max_length=100)
    contact = models.CharField(max_length=100, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)

    def __str__(self):
        return self.name


class PurchaseVoucher(models.Model):
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT)
    invoice_number = models.CharField(max_length=100, unique=True)
    date = models.DateField()
    is_posted = models.BooleanField(default=False)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"PV-{self.id} | {self.invoice_number} | {self.supplier.name}"

    def calculate_totals(self):
        items = self.items.all()
        self.total_amount = sum(item.total for item in items)
        super().save(update_fields=['total_amount'])

    def save(self, *args, **kwargs):
        if self.pk:
            original = PurchaseVoucher.objects.get(pk=self.pk)
            # Immutability enforcement [cite: 25]
            if original.is_posted and not (not original.is_posted and self.is_posted):
                raise ValidationError("This voucher is posted and immutable. No updates allowed.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.is_posted:
            raise ValidationError("Cannot delete a posted voucher. It is a permanent record.")
        super().delete(*args, **kwargs)


class PurchaseItem(models.Model):
    voucher = models.ForeignKey(PurchaseVoucher, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    lot_number = models.CharField(max_length=100, null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['voucher', 'product', 'lot_number'], 
                name='unique_voucher_product_lot'
            )
        ]

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"

    def clean(self):
        if self.product and self.product.is_lot_tracked:
            if not self.lot_number:
                raise ValidationError("Each purchase entry for a lot-controlled product must include lot identification.")
            if not self.expiry_date:
                raise ValidationError("Expiry date is required for lot-tracked products.")

        if self.expiry_date and self.voucher:
            if self.expiry_date <= self.voucher.date:
                raise ValidationError("Expiry date must be after the invoice date.")
            
            # Expired items prevention [cite: 31]
            if self.expiry_date <= date.today():
                raise ValidationError(f"This item has already expired. Expired items cannot be added.")

        if self.voucher:
            if self.product and self.product.is_lot_tracked and self.lot_number:
                existing = PurchaseItem.objects.filter(
                    voucher=self.voucher, product=self.product, lot_number=self.lot_number
                ).exclude(pk=self.pk)
                if existing.exists():
                    raise ValidationError("The same product may be purchased multiple times only if lots differ.")
            
            elif self.product and not self.product.is_lot_tracked:
                existing = PurchaseItem.objects.filter(
                    voucher=self.voucher, product=self.product, lot_number__isnull=True
                ).exclude(pk=self.pk)
                if existing.exists():
                    raise ValidationError("This product is already in the voucher. Increase the quantity instead.")

    def save(self, *args, **kwargs):
        if self.voucher and self.voucher.is_posted:
            raise ValidationError("Cannot modify items in a posted voucher.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.voucher and self.voucher.is_posted:
            raise ValidationError("Cannot delete items from a posted voucher.")
        super().delete(*args, **kwargs)

    def calculate(self):
        """Calculates line totals, discounts, and compound taxes using active taxes only, in order."""
        subtotal = (self.price * Decimal(self.quantity))
        discounted_subtotal = subtotal - self.discount

        # ✅ Get active taxes associated with the product, sorted by 'order'
        active_taxes = self.product.taxes.filter(is_active=True).order_by('order')

        total_single_tax = Decimal('0')
        compound_taxes = []

        for tax in active_taxes:
            rate = tax.percentage / Decimal('100')
            if tax.is_compound:
                compound_taxes.append(rate)
            else:
                total_single_tax += discounted_subtotal * rate

        base_for_compound = discounted_subtotal + total_single_tax
        total_compound_tax = Decimal('0')
        for comp_rate in compound_taxes:
            total_compound_tax += base_for_compound * comp_rate

        self.tax_amount = (total_single_tax + total_compound_tax).quantize(Decimal('0.01'))
        self.total = discounted_subtotal + self.tax_amount


class Inventory(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    lot_number = models.CharField(max_length=100, null=True, blank=True)
    quantity = models.PositiveIntegerField(default=0)
    expiry_date = models.DateField(null=True, blank=True)

    class Meta:
        unique_together = ('product', 'lot_number')
        verbose_name_plural = "Inventory"

    def __str__(self):
        lot = f" | Lot: {self.lot_number}" if self.lot_number else ""
        return f"{self.product.name}{lot} — Qty: {self.quantity}"

    @property
    def is_expired(self):
        if self.expiry_date:
            return self.expiry_date <= date.today()
        return False

    @classmethod
    def get_usable_stock(cls):
        today = date.today()
        from django.db.models import Q
        return cls.objects.filter(
            Q(expiry_date__isnull=True) | Q(expiry_date__gt=today),
            quantity__gt=0
        ).order_by('expiry_date')