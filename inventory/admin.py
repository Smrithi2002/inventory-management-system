from django.contrib import admin
from .models import Product, Tax, Supplier, PurchaseVoucher, PurchaseItem, Inventory


@admin.register(Tax)
class TaxAdmin(admin.ModelAdmin):
    list_display = ('name', 'percentage', 'is_compound', 'is_active')
    list_filter = ('is_active', 'is_compound')


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'sku', 'category', 'cost_price', 'selling_price', 'get_taxes', 'is_lot_tracked', 'is_active')
    list_filter = ('is_active', 'category', 'is_lot_tracked')
    search_fields = ('name', 'sku')
    filter_horizontal = ('taxes',)

    def get_taxes(self, obj):
        return ", ".join([t.name for t in obj.taxes.all()]) or "-"
    
    get_taxes.short_description = "Taxes"


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('name', 'contact', 'email')
    search_fields = ('name',)


class PurchaseItemInline(admin.TabularInline):
    model = PurchaseItem
    extra = 0
    readonly_fields = ('tax_amount', 'total')


@admin.register(PurchaseVoucher)
class PurchaseVoucherAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'supplier', 'date', 'total_amount', 'is_posted')
    list_filter = ('is_posted',)
    search_fields = ('invoice_number',)
    inlines = [PurchaseItemInline]


@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = ('product', 'lot_number', 'quantity', 'expiry_date', 'expired_status')
    list_filter = ('product',)

    def expired_status(self, obj):
        return obj.is_expired

    expired_status.boolean = True
    expired_status.short_description = "Expired"    