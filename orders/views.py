import datetime
import json
from django.shortcuts import render, redirect
from django.template.loader import render_to_string
from django.core.mail import EmailMessage
from django.http import JsonResponse

from .forms import OrderForm
from .models import Order, OrderProduct, Payment
from carts.models import CartItem
from store.models import Product


def payments(request):
    body = json.loads(request.body)
    order = Order.objects.get(user=request.user,
                              is_ordered=False,
                              order_number=body["orderID"])
    payment = Payment(
        user=request.user,
        payment_id=body['transID'],
        payment_method=body["payment_method"],
        amount_paid=order.order_total,
        status=body["status"],
    )
    payment.save()

    order.payment = payment
    order.is_ordered = True
    order.save()

    # Move the cart items to OrderProduct table
    cart_items = CartItem.objects.filter(user=request.user)
    for item in cart_items:
        order_product = OrderProduct()
        order_product.order_id = order.id
        order_product.payment = payment
        order_product.user_id = request.user.id
        order_product.product_id = item.product_id
        order_product.quantity = item.quantity
        order_product.product_price = item.product.price
        order_product.is_ordered = True
        order_product.save()

        cart_item = CartItem.objects.get(id=item.id)
        product_variation = cart_item.variations.all()
        order_product = OrderProduct.objects.get(id=order_product.id)
        order_product.variations.set(product_variation)
        order_product.save()

        # Reduce the quantity of the sold products
        product = Product.objects.get(id=item.product_id)
        product.stock -= item.quantity
        product.save()

    # Clear cart
    CartItem.objects.filter(user=request.user).delete()

    # Send order recieved email to customer
    mail_subject = "Thank you for your order!"
    message = render_to_string("orders/order_recieved_email.html", {
        "user": request.user,
        "order": order,
    })
    to_email = request.user.email
    send_email = EmailMessage(mail_subject, message, to=[to_email])
    send_email.send()

    # Send order number and transaction id back to sendData method via JsonResponse
    data = {
        "order_number": order.order_number,
        "transID": payment.payment_id,

    }
    return JsonResponse(data)


def place_order(request, total=0, quantity=0):
    current_user = request.user
    cart_items = CartItem.objects.filter(user=current_user)
    cart_count = cart_items.count()

    if cart_count <= 0:
        return redirect("store")

    grand_total = 0
    tax = 0

    for cart_item in cart_items:
        total += cart_item.product.price * cart_item.quantity
        quantity += cart_item.quantity

    tax = (2 * total)/100
    grand_total = total + tax

    if request.method == "POST":
        form = OrderForm(request.POST)
        if form.is_valid():
            data = Order()
            data.user = current_user
            data.first_name = form.cleaned_data["first_name"]
            data.last_name = form.cleaned_data["last_name"]
            data.phone = form.cleaned_data["phone"]
            data.email = form.cleaned_data["email"]
            data.address_line_1 = form.cleaned_data["address_line_1"]
            data.address_line_2 = form.cleaned_data["address_line_2"]
            data.country = form.cleaned_data["country"]
            data.state = form.cleaned_data["state"]
            data.city = form.cleaned_data["city"]
            data.order_note = form.cleaned_data["order_note"]
            data.order_total = grand_total
            data.tax = tax
            data.ip = request.META.get("REMOTE_ADDR")
            data.save()

            year = int(datetime.date.today().strftime("%Y"))
            day = int(datetime.date.today().strftime("%d"))
            month = int(datetime.date.today().strftime("%m"))
            d = datetime.date(year, month, day)
            current_date = d.strftime("%Y%m%d")
            order_number = current_date + str(data.id)
            data.order_number = order_number
            data.save()

            order = Order.objects.get(user=current_user,
                                      is_ordered=False,
                                      order_number=order_number)
            context = {
                "order": order,
                "cart_items": cart_items,
                "total": total,
                "tax": tax,
                "grand_total": grand_total
            }
            return render(request, "orders/payments.html", context=context)
        else:
            return redirect("checkout")


def order_complete(request):
    order_number = request.GET.get("order_number")
    payment_id = request.GET.get("payment_id")

    try:
        order = Order.objects.get(order_number=order_number, is_ordered=True)
        order_products = OrderProduct.objects.filter(order_id=order.id)
        payment = Payment.objects.get(payment_id=payment_id)

        subtotal = 0
        for item in order_products:
            subtotal += item.product_price * item.quantity

        context = {
            "order": order,
            "order_products": order_products,
            "payment": payment,
            "subtotal": subtotal
        }
        return render(request, "orders/order_complete.html", context=context)
    except (Payment.DoesNotExist, Order.DoesNotExist):
        return redirect("home")
