from django.urls import path, include
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # Auth & Default to Login
    path('', auth_views.LoginView.as_view(), name='login'),

    path('dashboard', views.dashboard, name='dashboard'),

    # Tax Management
    path('taxes/', views.tax_list, name='tax_list'),
    path('taxes/add/', views.add_tax, name='add_tax'),
    path('taxes/<int:tax_id>/edit/', views.edit_tax, name='edit_tax'),
    path('taxes/<int:tax_id>/toggle/', views.toggle_tax, name='toggle_tax'),

    # Product Management
    path('products/', views.product_list, name='product_list'),
    path('products/add/', views.add_product, name='add_product'),
    path('products/<int:product_id>/edit/', views.edit_product, name='edit_product'),
    path('products/<int:product_id>/toggle/', views.toggle_product, name='toggle_product'),
    path('products/<int:product_id>/delete/', views.delete_product, name='delete_product'),

    # Supplier Management
    path('suppliers/', views.supplier_list, name='supplier_list'),
    path('suppliers/add/', views.add_supplier, name='add_supplier'),
    path('api/suppliers/add/', views.api_add_supplier, name='api_add_supplier'),
    path('suppliers/<int:supplier_id>/edit/', views.edit_supplier, name='edit_supplier'),

    # Purchase Voucher Processing
    path('vouchers/', views.voucher_list, name='voucher_list'),
    path('vouchers/create/', views.create_voucher, name='create_voucher'),
    path('vouchers/<int:voucher_id>/items/', views.add_items, name='add_items'),
    path('vouchers/<int:voucher_id>/post/', views.post_voucher, name='post_voucher'),
    path('vouchers/<int:voucher_id>/detail/', views.voucher_detail, name='voucher_detail'),
    path('items/<int:item_id>/delete/', views.delete_item, name='delete_item'),

    # Inventory
    path('inventory/', views.inventory_list, name='inventory_list'),

    # Quick Purchase (Unified Action)
    path('quick-purchase/', views.quick_purchase, name='quick_purchase'),
    path('quick-purchase/<int:product_id>/', views.quick_purchase, name='quick_purchase_product'),
]