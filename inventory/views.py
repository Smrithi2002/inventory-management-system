from django.shortcuts import render, redirect, get_object_or_404
from django.db import IntegrityError, transaction
from django.core.exceptions import ValidationError
from django.contrib import messages
from datetime import date
from decimal import Decimal, InvalidOperation
from django.db.models import Q
from .models import Product, Tax, Supplier, PurchaseVoucher, PurchaseItem, Inventory
from django.contrib.auth.decorators import login_required


# ═══════════════════════════════════════════════════════════════
#                     DASHBOARD
# ═══════════════════════════════════════════════════════════════

@login_required
def dashboard(request):
    """Main dashboard with summary stats."""
    context = {
        'total_products': Product.objects.filter(is_active=True).count(),
        'total_supplier': Supplier.objects.count(),
        'total_vouchers': PurchaseVoucher.objects.filter(is_posted=True).count(),
        'total_inventory_items': Inventory.objects.filter(quantity__gt=0).count(),
        'expired_lots': Inventory.objects.filter(expiry_date__lte=date.today(), quantity__gt=0).count(),
    }
    return render(request, 'dashboard.html', context)


# ═══════════════════════════════════════════════════════════════
#                     TAX MANAGEMENT
# ═══════════════════════════════════════════════════════════════

@login_required
def tax_list(request):
    taxes = Tax.objects.all().order_by('-is_active', 'name')
    return render(request, 'tax_list.html', {'taxes': taxes})


@login_required
def add_tax(request):
    if request.method == "POST":
        name = request.POST.get('name', '').strip()
        percentage = request.POST.get('percentage', '')
        is_compound = request.POST.get('is_compound') == 'on'
        order = int(request.POST.get('order', 1))
        if not name or not percentage:
            return render(request, 'tax_form.html', {
                'error': "Name and percentage are required.",
                'form_data': request.POST
            })

        try:
            percentage = Decimal(percentage)
        except ValueError:
            return render(request, 'tax_form.html', {
                'error': "Invalid percentage value.",
                'form_data': request.POST
            })

        tax = Tax(
            name=name,
            percentage=percentage,
            is_compound=is_compound,
            order=order,
        )
        tax.full_clean()
        tax.save()
        messages.success(request, f"Tax '{name}' created successfully.")
        return redirect('tax_list')

    return render(request, 'tax_form.html')


@login_required
def edit_tax(request, tax_id):
    tax = get_object_or_404(Tax, id=tax_id)

    # Check if tax is used in any transaction
    is_used = PurchaseItem.objects.filter(product__taxes=tax).exists()

    if request.method == "POST":
        name = request.POST.get('name', '').strip()
        percentage = request.POST.get('percentage', '')
        is_compound = request.POST.get('is_compound') == 'on'
        order = int(request.POST.get('order', 1))

        if not name or not percentage:
            return render(request, 'tax_form.html', {
                'error': "Name and percentage are required.",
                'tax': tax,
                'is_used': is_used,
                'form_data': request.POST
            })

        tax.name = name
        tax.percentage = percentage
        tax.is_compound = is_compound
        tax.order = order
        try:
            tax.full_clean()
            tax.save()
            messages.success(request, f"Tax '{name}' updated successfully.")
            return redirect('tax_list')
        except ValidationError as e:
            return render(request, 'tax_form.html', {
                'error': "Cannot modify percentage of a tax currently in use. Create a new one instead." if "in use" in str(e) else "Validation error.",
                'tax': tax,
                'is_used': is_used,
                'form_data': request.POST
            })

    return render(request, 'tax_form.html', {'tax': tax, 'is_used': is_used})


@login_required
def toggle_tax(request, tax_id):
    tax = get_object_or_404(Tax, id=tax_id)
    tax.is_active = not tax.is_active
    tax.save()
    status = "activated" if tax.is_active else "deactivated"
    messages.success(request, f"Tax '{tax.name}' {status}.")
    return redirect('tax_list')


# ═══════════════════════════════════════════════════════════════
#                     PRODUCT MANAGEMENT
# ═══════════════════════════════════════════════════════════════

@login_required
def product_list(request):
    products = Product.objects.prefetch_related('taxes').all().order_by('-is_active', 'name')
    return render(request, 'product_list.html', {'products': products})


@login_required
def add_product(request):
    if request.method == "POST":
        name = request.POST.get('name', '').strip()
        sku = request.POST.get('sku', '').strip()
        category = request.POST.get('category', 'general')
        cost_price = request.POST.get('cost_price')
        selling_price = request.POST.get('selling_price')
        tax_ids = request.POST.getlist('taxes')
        is_lot_tracked = request.POST.get('is_lot_tracked') == 'on'

        if not name or not sku:
            return render(request, 'product_form.html', {
                'error': "Name and SKU are required.",
                'taxes': Tax.objects.filter(is_active=True),
                'categories': Product.CATEGORY_CHOICES,
                'form_data': request.POST
            })

        if Product.objects.filter(sku=sku).exists():
            return render(request, 'product_form.html', {
                'error': "A product with this SKU already exists.",
                'taxes': Tax.objects.filter(is_active=True),
                'categories': Product.CATEGORY_CHOICES,
                'form_data': request.POST
            })
        product = Product.objects.create(
            name=name,
            sku=sku,
            category=category,
            cost_price=cost_price,
            selling_price=selling_price,
            is_lot_tracked=is_lot_tracked,
        )

        taxes_objs = Tax.objects.filter(id__in=tax_ids)
        if tax_ids and not taxes_objs.exists():
            return render(request, 'product_form.html', {
                'error': "Invalid tax selection.",
                'taxes': Tax.objects.filter(is_active=True),
                'categories': Product.CATEGORY_CHOICES,
                'form_data': request.POST
            })
        product.taxes.set(taxes_objs)

        messages.success(request, f"Product '{product.name}' created successfully. Add it to a purchase below.")
        return redirect('quick_purchase_product', product_id=product.id)

    return render(request, 'product_form.html', {
        'taxes': Tax.objects.filter(is_active=True),
        'categories': Product.CATEGORY_CHOICES,
    })


@login_required
def edit_product(request, product_id):
    product = get_object_or_404(Product, id=product_id)

    if request.method == "POST":
        name = request.POST.get('name', '').strip()
        sku = request.POST.get('sku', '').strip()
        category = request.POST.get('category', 'general')
        cost_price = request.POST.get('cost_price')
        selling_price = request.POST.get('selling_price')
        tax_ids = request.POST.getlist('taxes')
        is_lot_tracked = request.POST.get('is_lot_tracked') == 'on'

        if not name or not sku:
            return render(request, 'product_form.html', {
                'error': "Name and SKU are required.",
                'product': product,
                'taxes': Tax.objects.filter(is_active=True),
                'categories': Product.CATEGORY_CHOICES,
                'form_data': request.POST
            })

        # Check SKU uniqueness (exclude self)
        if Product.objects.filter(sku=sku).exclude(id=product_id).exists():
            return render(request, 'product_form.html', {
                'error': "A product with this SKU already exists.",
                'product': product,
                'taxes': Tax.objects.filter(is_active=True),
                'categories': Product.CATEGORY_CHOICES,
                'form_data': request.POST
            })

        product.name = name
        product.sku = sku
        product.category = category
        product.cost_price = cost_price
        product.selling_price = selling_price
        product.taxes.set(tax_ids)
        product.is_lot_tracked = is_lot_tracked
        product.save()
        messages.success(request, f"Product '{name}' updated successfully.")
        return redirect('product_list')

    return render(request, 'product_form.html', {
        'product': product,
        'taxes': Tax.objects.filter(is_active=True),
        'categories': Product.CATEGORY_CHOICES,
    })


@login_required
def toggle_product(request, product_id):
    """Activate/deactivate product without data loss."""
    product = get_object_or_404(Product, id=product_id)
    product.is_active = not product.is_active
    product.save()
    status = "activated" if product.is_active else "deactivated"
    messages.success(request, f"Product '{product.name}' {status}.")
    return redirect('product_list')


@login_required
def delete_product(request, product_id):
    """Delete product only if not referenced in transactions."""
    product = get_object_or_404(Product, id=product_id)
    if not product.can_delete():
        messages.error(request, f"Cannot delete '{product.name}' — it is referenced in purchase transactions.")
        return redirect('product_list')
    name = product.name
    product.delete()
    messages.success(request, f"Product '{name}' deleted successfully.")
    return redirect('product_list')


# ═══════════════════════════════════════════════════════════════
#                     SUPPLIER MANAGEMENT
# ═══════════════════════════════════════════════════════════════

@login_required
def supplier_list(request):
    suppliers = Supplier.objects.all().order_by('name')
    return render(request, 'supplier_list.html', {'suppliers': suppliers})


@login_required
def add_supplier(request):
    if request.method == "POST":
        name = request.POST.get('name', '').strip()
        contact = request.POST.get('contact', '').strip()
        email = request.POST.get('email', '').strip()

        if not name:
            return render(request, 'supplier_form.html', {
                'error': "Supplier name is required.",
                'form_data': request.POST
            })

        Supplier.objects.create(name=name, contact=contact, email=email)
        messages.success(request, f"Supplier '{name}' created successfully.")
        return redirect('supplier_list')

    return render(request, 'supplier_form.html')


@login_required
def edit_supplier(request, supplier_id):
    supplier = get_object_or_404(Supplier, id=supplier_id)

    if request.method == "POST":
        name = request.POST.get('name', '').strip()
        contact = request.POST.get('contact', '').strip()
        email = request.POST.get('email', '').strip()

        if not name:
            return render(request, 'supplier_form.html', {
                'error': "Supplier name is required.",
                'supplier': supplier,
                'form_data': request.POST
            })

        supplier.name = name
        supplier.contact = contact
        supplier.email = email
        supplier.save()
        messages.success(request, f"Supplier '{name}' updated successfully.")
        return redirect('supplier_list')

    return render(request, 'supplier_form.html', {'supplier': supplier})


@login_required
def api_add_supplier(request):
    """AJAX endpoint to create a new supplier on the fly with details."""
    if request.method == "POST":
        name = request.POST.get('name', '').strip()
        contact = request.POST.get('contact', '').strip()
        email = request.POST.get('email', '').strip()

        if not name:
            return JsonResponse({'success': False, 'error': "Name is required."}, status=400)
        
        supplier = Supplier.objects.create(
            name=name,
            contact=contact,
            email=email
        )
        return JsonResponse({
            'success': True,
            'id': supplier.id,
            'name': supplier.name
        })
    return JsonResponse({'success': False, 'error': "Invalid request method."}, status=405)


from django.http import JsonResponse


# ═══════════════════════════════════════════════════════════════
#                   PURCHASE VOUCHER PROCESSING
# ═══════════════════════════════════════════════════════════════

@login_required
def voucher_list(request):
    vouchers = PurchaseVoucher.objects.filter(is_posted=True).select_related('supplier').all().order_by('-date', '-id')
    return render(request, 'voucher_list.html', {'vouchers': vouchers})


@login_required
def create_voucher(request):
    if request.method == "POST":
        supplier_id = request.POST.get('supplier')
        invoice_number = request.POST.get('invoice_number', '').strip()
        voucher_date = request.POST.get('date')

        if not supplier_id or not invoice_number or not voucher_date:
            return render(request, 'voucher_form.html', {
                'error': "All fields are required.",
                'suppliers': Supplier.objects.all(),
                'form_data': request.POST
            })

        # Check duplicate invoice number
        if PurchaseVoucher.objects.filter(invoice_number=invoice_number).exists():
            return render(request, 'voucher_form.html', {
                'error': "A voucher with this invoice number already exists.",
                'suppliers': Supplier.objects.all(),
                'form_data': request.POST
            })

        supplier = get_object_or_404(Supplier, id=supplier_id)

        voucher = PurchaseVoucher.objects.create(
            supplier=supplier,
            invoice_number=invoice_number,
            date=voucher_date,
        )
        messages.success(request, f"Voucher '{invoice_number}' created. Add line items below.")
        return redirect('add_items', voucher.id)

    suppliers = Supplier.objects.all()
    return render(request, 'voucher_form.html', {'suppliers': suppliers})


@login_required
def add_items(request, voucher_id):
    """Add line items to an unposted voucher."""
    voucher = get_object_or_404(PurchaseVoucher, id=voucher_id)

    # Voucher immutability: prevent changes after posting
    if voucher.is_posted:
        messages.warning(request, "This voucher has been posted and cannot be modified.")
        return redirect('voucher_list')

    error = None

    if request.method == "POST":
        product_id = request.POST.get('product')
        quantity = request.POST.get('quantity')
        price = request.POST.get('price')
        discount = request.POST.get('discount', '0')
        lot_number = request.POST.get('lot_number', '').strip()
        expiry_date_str = request.POST.get('expiry_date', '').strip()

        try:
            product = Product.objects.get(id=product_id)
            quantity = int(quantity)
            price = Decimal(price)
            discount = Decimal(discount) if discount else Decimal('0')

            if quantity <= 0:
                raise ValidationError("Quantity must be positive.")
            if price <= 0:
                raise ValidationError("Price must be positive.")
            if discount < 0:
                raise ValidationError("Discount cannot be negative.")

            # Parse expiry date
            expiry_date = None
            if expiry_date_str:
                from datetime import datetime
                expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d').date()

            # Create purchase item
            item = PurchaseItem(
                voucher=voucher,
                product=product,
                quantity=quantity,
                price=price,
                discount=discount,
                lot_number=lot_number if lot_number else None,
                expiry_date=expiry_date,
            )

            # Calculate tax and total
            item.calculate()

            # Run model-level validation (lot/expiry rules)
            item.clean()

            item.save()

            # Recalculate voucher total
            voucher.calculate_totals()

            messages.success(request, f"Added {product.name} x {quantity}.")

        except ValidationError as e:
            error = str(e.message if hasattr(e, 'message') else e)
        except (ValueError, TypeError, InvalidOperation) as e:
            error = f"Invalid input: {e}"
        except Product.DoesNotExist:
            error = "Selected product does not exist."

    # Only show active products
    products = Product.objects.filter(is_active=True).prefetch_related('taxes')
    items = voucher.items.select_related('product').all()

    return render(request, 'add_items.html', {
        'products': products,
        'items': items,
        'voucher': voucher,
        'error': error,
    })


@login_required
def delete_item(request, item_id):
    """Remove a line item from an unposted voucher."""
    item = get_object_or_404(PurchaseItem, id=item_id)
    voucher = item.voucher

    if voucher.is_posted:
        messages.warning(request, "Cannot modify a posted voucher.")
        return redirect('voucher_list')

    item.delete()
    voucher.calculate_totals()
    messages.success(request, "Item removed.")
    return redirect('add_items', voucher.id)


@login_required
def post_voucher(request, voucher_id):
    """
    Post voucher: update inventory in a transaction-safe manner.
    - Expired items are NEVER added to inventory.
    - Uses transaction.atomic for safety (no partial updates).
    """
    voucher = get_object_or_404(PurchaseVoucher, id=voucher_id)

    if voucher.is_posted:
        messages.info(request, "This voucher is already posted.")
        return redirect('voucher_list')

    items = voucher.items.select_related('product').all()

    if not items.exists():
        messages.error(request, "Cannot post an empty voucher. Add at least one item.")
        return redirect('add_items', voucher.id)

    try:
        with transaction.atomic():
            for item in items:
                # ❌ Expired items must never be added to inventory
                if item.expiry_date and item.expiry_date <= date.today():
                    raise ValidationError(
                        f"Cannot post: {item.product.name} (Lot: {item.lot_number}) "
                        f"has expired on {item.expiry_date}. Remove it first."
                    )

                inventory, created = Inventory.objects.get_or_create(
                    product=item.product,
                    lot_number=item.lot_number,
                    defaults={
                        'quantity': 0,
                        'expiry_date': item.expiry_date
                    }
                )
                inventory.quantity += item.quantity
                if item.expiry_date:
                    inventory.expiry_date = item.expiry_date
                inventory.save()

            voucher.is_posted = True
            voucher.save()

        messages.success(request, f"Voucher '{voucher.invoice_number}' posted successfully. Inventory updated.")
    except ValidationError as e:
        messages.error(request, str(e.message if hasattr(e, 'message') else e))
        return redirect('add_items', voucher.id)

    return redirect('voucher_list')


@login_required
def voucher_detail(request, voucher_id):
    """View a posted voucher (read-only)."""
    voucher = get_object_or_404(PurchaseVoucher, id=voucher_id)
    items = voucher.items.select_related('product').all()
    return render(request, 'voucher_detail.html', {
        'voucher': voucher,
        'items': items,
    })


# ═══════════════════════════════════════════════════════════════
#                     INVENTORY
# ═══════════════════════════════════════════════════════════════

@login_required
def inventory_list(request):
    """
    Show all inventory with expired lots flagged.
    FIFO: sorted by expiry_date ascending (oldest first).
    """
    today = date.today()

    # Usable stock (not expired)
    usable_stock = Inventory.objects.filter(
        Q(expiry_date__isnull=True) | Q(expiry_date__gt=today),
        quantity__gt=0
    ).select_related('product').order_by('expiry_date')

    # Expired lots (for visibility)
    expired_stock = Inventory.objects.filter(
        expiry_date__lte=today,
        quantity__gt=0
    ).select_related('product').order_by('expiry_date')

    return render(request, 'inventory_list.html', {
        'usable_stock': usable_stock,
        'expired_stock': expired_stock,
        'today': today,
    })


# ═══════════════════════════════════════════════════════════════
#                   QUICK PURCHASE (UNIFIED)
# ═══════════════════════════════════════════════════════════════

@login_required
def quick_purchase(request, product_id=None):
    """
    Unified one-step purchase:
    Creates voucher, adds item, and posts to inventory in one click.
    """
    selected_product = None
    if product_id:
        selected_product = get_object_or_404(Product, id=product_id)

    if request.method == "POST":
        # Shared Voucher Data
        supplier_id = request.POST.get('supplier')
        invoice_no = request.POST.get('invoice_number', '').strip()
        
        # Lists of Item Data
        p_ids = request.POST.getlist('product[]')
        qtys = request.POST.getlist('quantity[]')
        prices = request.POST.getlist('price[]')
        discounts = request.POST.getlist('discount[]')
        lot_nos = request.POST.getlist('lot_number[]')
        expiry_strs = request.POST.getlist('expiry_date[]')

        # New Product Arrays (Parallel to others and filtered by 'NEW' marker in p_ids)
        new_names = request.POST.getlist('new_name[]')
        new_skus = request.POST.getlist('new_sku[]')
        new_taxes = request.POST.getlist('new_taxes[]')
        # Checkboxes only send indices that are 'on'. Template handles this with unique names or logic.
        # For simplicity, if we have multiple new items, we expect them to be provided in order.

        # Validation
        if not supplier_id or not p_ids:
            error_msg = "Please select a supplier and add at least one item."
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': error_msg})
            messages.error(request, error_msg)
            return redirect('quick_purchase')
        
        if not invoice_no:
            import time
            invoice_no = f"AUTO-{int(time.time())}"

        try:
            with transaction.atomic():
                supplier = get_object_or_404(Supplier, id=supplier_id)
                
                # 1. Create the Voucher
                voucher = PurchaseVoucher.objects.create(
                    supplier=supplier,
                    invoice_number=invoice_no,
                    date=date.today()
                )

                # 2. Process each Row
                new_prod_idx = 0
                for i in range(len(p_ids)):
                    p_id_val = p_ids[i]
                    
                    # Safe parallel list access
                    qty_str = qtys[i] if i < len(qtys) else "0"
                    price_str = prices[i] if i < len(prices) else "0"
                    discount_str = discounts[i] if i < len(discounts) else "0"
                    lot_no = lot_nos[i].strip() if i < len(lot_nos) else ""
                    expiry_str = expiry_strs[i].strip() if i < len(expiry_strs) else ""
                    
                    # Numeric Parsing
                    try:
                        qty_int = int(qty_str)
                        price_dec = Decimal(price_str.replace('₹', '').replace(',', '').strip() or '0')
                        discount_dec = Decimal(discount_str.replace('₹', '').replace(',', '').strip() or '0')
                        
                        if qty_int <= 0 or price_dec <= 0:
                            raise ValidationError(f"Invalid quantity or price at row {i+1}.")
                    except (ValueError, InvalidOperation):
                        raise ValidationError(f"Numeric formatting error at row {i+1}.")

                    # Product Resolution
                    if p_id_val == "NEW":
                        if new_prod_idx >= len(new_names):
                            raise ValidationError(f"Missing name for the new product at row {i+1}.")
                            
                        name = new_names[new_prod_idx]
                        sku = new_skus[new_prod_idx] if new_prod_idx < len(new_skus) else ""
                        
                        if not name or not sku:
                            raise ValidationError(f"Name and SKU are required for the new product at row {i+1}.")
                        
                        if Product.objects.filter(sku=sku).exists():
                            raise ValidationError(f"Row {i+1}: Product SKU '{sku}' already exists.")
                        
                        tax_ids_str = new_taxes[new_prod_idx] if new_prod_idx < len(new_taxes) else ""
                        tax_ids = [tid for tid in tax_ids_str.split(',') if tid.strip()]
                        
                        # Handle lot tracking toggle for new products
                        # We used 'new_is_lot_tracked[]' in template. 
                        # Note: This is an array of 'on' values. Hard to sync. 
                        # I'll default new products to lot tracked in quick purchase if they provide a lot number.
                        is_tracked = bool(lot_no or expiry_str)

                        product = Product.objects.create(
                            name=name,
                            sku=sku,
                            category='general',
                            cost_price=price_dec,
                            selling_price=price_dec * Decimal('1.25'),
                            is_lot_tracked=is_tracked
                        )
                        
                        if tax_ids:
                            product.taxes.set(Tax.objects.filter(id__in=tax_ids))
                            
                        new_prod_idx += 1
                    else:
                        product = get_object_or_404(Product, id=p_id_val)

                    # Date Parsing
                    expiry_dt = None
                    if expiry_str:
                        from datetime import datetime
                        try:
                            expiry_dt = datetime.strptime(expiry_str, '%Y-%m-%d').date()
                        except ValueError:
                            raise ValidationError(f"Invalid date format at row {i+1}.")

                    # 3. Create Item
                    item = PurchaseItem(
                        voucher=voucher,
                        product=product,
                        quantity=qty_int,
                        price=price_dec,
                        discount=discount_dec,
                        lot_number=lot_no if lot_no else None,
                        expiry_date=expiry_dt
                    )
                    try:
                        item.calculate()
                        item.clean()
                        item.save()
                    except ValidationError as row_e:
                        e_msg = row_e.messages[0] if hasattr(row_e, 'messages') and row_e.messages else str(row_e)
                        raise ValidationError(f"Item {i+1} ({product.name}): {e_msg}")

                    # 4. Update Inventory
                    inventory, created = Inventory.objects.get_or_create(
                        product=product,
                        lot_number=item.lot_number,
                        defaults={'quantity': 0, 'expiry_date': item.expiry_date}
                    )
                    inventory.quantity += item.quantity
                    if item.expiry_date:
                        inventory.expiry_date = item.expiry_date
                    inventory.save()

                # Finalize Voucher
                voucher.calculate_totals()
                voucher.is_posted = True
                voucher.save()

                messages.success(request, f"Purchase successful! Voucher {invoice_no} posted with {len(p_ids)} items.")
                
                if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    from django.urls import reverse
                    return JsonResponse({'success': True, 'redirect': reverse('inventory_list')})
                return redirect('inventory_list')

        except ValidationError as e:
            if hasattr(e, 'message_dict'):
                messages_list = []
                for field, errors in e.message_dict.items():
                    field_name = field.replace('_', ' ').capitalize() if field != '__all__' else ""
                    msg = errors[0] if isinstance(errors, list) and errors else str(errors)
                    messages_list.append(f"{field_name}: {msg}" if field_name else msg)
                error_msg = "; ".join(messages_list)
            elif hasattr(e, 'messages') and e.messages:
                error_msg = e.messages[0]
            else:
                error_msg = str(e)

            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': error_msg})
            messages.error(request, error_msg)
        except Exception as e:
            error_msg = str(e)
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': error_msg})
            messages.error(request, error_msg)

    return render(request, 'quick_purchase.html', {
        'products': Product.objects.filter(is_active=True),
        'suppliers': Supplier.objects.all(),
        'taxes': Tax.objects.filter(is_active=True),
        'categories': Product.CATEGORY_CHOICES,
        'selected_product': selected_product,
        'today': date.today(),
    })

