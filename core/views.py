from django.conf import settings
from django.contrib import messages
from django.shortcuts import render, get_object_or_404,redirect
from django.views.generic import ListView,DetailView,View
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from . models import Item,OrderItem,Order,BillingAddress, Payment
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ObjectDoesNotExist
from .forms import CheckOutForm


import stripe
stripe.api_key = settings.STRIPE_SECRET_KEY

# `source` is obtained with Stripe.js; see https://stripe.com/docs/payments/accept-a-payment-charges#web-create-token






class HomeView(ListView):
	model = Item
	paginate_by = 10
	template_name = "home.html"

class CheckOutView(View):
	def get(self, *args, **kwargs):
		# forms
		form = CheckOutForm()
		context = {
			"form":form,
		}
		return render(self.request, "checkout.html", context)

	def post(self, *args, **kwargs):
		form = CheckOutForm(self.request.POST or None)
		try:
			order = Order.objects.get(user=self.request.user, ordered=False)
			if form.is_valid():
				street_address = form.cleaned_data.get('street_address')
				apartment_address = form.cleaned_data.get('apartment_address')
				country =  form.cleaned_data.get('country')
				# TODO
				# same_shipping_address = form.cleaned_data.get('same_shipping_address')
				# save_info = form.cleaned_data.get('save_info')
				payment_option = form.cleaned_data.get('payment_option')
				billing_address = BillingAddress(
					user=self.request.user,
					street_address=street_address,
					apartment_address=apartment_address,
					country=country,
					zip=zip,
				)
				billing_address.save()
				order.billing_address = billing_address
				order.save()

				if payment_option == 'S':
					return redirect('core:payment', payment_option='stripe')
				elif payment_option == 'P':
					return redirect('core:payment', payment_option='paypal')
				else:
					messages.warning(self.request,"Invalid Payment Option Selected")
				# ToDO add a redirect to the selected payment option
				return redirect("core:checkout")
			messages.warning(self.request,"Failed Checkout")
			return redirect("core:checkout")

		except ObjectDoesNotExist:
			messages.warning(self.request, "You do not have an active order")
			return redirect("core:order-summary")

class PaymentView(View):
	def get(self, *args, **kwargs):
		# order
		order = Order.objects.get(user=self.request.user,ordered=False)
		context ={
			'order':order,
		}
		return render(self.request, "payment.html", context)

	def post(self, *args, **kwargs):
		# order
		order = Order.objects.get(user=self.request.user,ordered=False)
		token = self.request.POST.get('stripeToken')
		amount = int(order.get_total() * 100) # * 100 because of cents

		try:
			charge = stripe.Charge.create(
				amount=amount, 
				currency="usd",
				source=token,
				description="My First Test Charge",
			)


			# create the payment

			payment = Payment()
			payment.stripe_charge_id = charge['id']
			payment.user = self.request.user
			payment.amount = order.get_total()
			payment.save()
			print(amount)

			# assign payment to order
			order.payment = True
			order.payment = payment
			order.save()
			messages.success(self.request, "Your order was successful")
			return redirect("/")

		except stripe.error.CardError as e:
			body = e.json_body
			err = body.get('error', {})

			messages.error(self.request, f"{err.get('message')}")
			return redirect("/")

		except stripe.error.RateLimitError as e:
			# Too many requests made to the API too quickly
			messages.error(self.request, "Rate RateLimitError")
			return redirect("/")
			
		except stripe.error.InvalidRequestError as e:
			# Invalid parameters were supplied to Stripe's API
			messages.error(self.request,"Invalid parameters")
			return redirect("/")
			
		except stripe.error.AuthenticationError as e:

			# Authentication with Stripe's API failed
			# (maybe you changed API keys recently)
			messages.error(self.request, "Not Authenticated")
			return redirect("/")
			
		except stripe.error.APIConnectionError as e:
			# Network communication with Stripe failed
			messages.error(self.request, "Network error")
			return redirect("/")
		
		except stripe.error.StripeError as e:
			# Display a very generic error to the user, and maybe send
			# yourself an email
			messages.error(self.request, "Something went wrong. You were not charged")
			return redirect("/")
			
		except Exception as e:
			# Send an Email
			messages.error(self.request, "Serious Error occured")
			print(e)
			return redirect("/")


class ItemDetailView(DetailView):
	model = Item
	template_name = "product.html"

class OrderSummaryView(LoginRequiredMixin, View):
	def get(self, *args, **kwargs):
		try:
			order = Order.objects.get(user=self.request.user, ordered=False)
			context = {
				'object': order
				}
			return render(self.request, 'order_summary.html', context)
		except ObjectDoesNotExist:
			messages.warning(self.request, "You do not have an active order")
			return redirect("/")
		
	

@login_required
def add_to_cart(request,slug):
	item = get_object_or_404(Item,slug=slug)
	order_item, created= OrderItem.objects.get_or_create(
		item=item,
		user=request.user,
		ordered=False)
	order_qs = Order.objects.filter(user=request.user, ordered=False)
	if order_qs.exists():
		order = order_qs[0]
		# check if order item is in the order
		if order.items.filter(item__slug=item.slug).exists():
			order_item.quantity += 1
			order_item.save()
			messages.info(request, "This item quantity was updated to cart")
			return redirect("core:order-summary")
		else:
			order.items.add(order_item)
			messages.info(request, "This item was added to your cart")
			return redirect("core:order-summary")
	else:
		ordered_date = timezone.now()
		order = Order.objects.create(user=request.user,ordered_date=ordered_date)
		order.items.add(order_item)
		messages.info(request, "This item was added to your cart")
		return redirect("core:order-summary")


@login_required
def remove_from_cart(request,slug):
	item = get_object_or_404(Item,slug=slug)
	order_qs = Order.objects.filter(user=request.user, ordered=False)
	if order_qs.exists():
		order = order_qs[0]
		# check if order item is in the order
		if order.items.filter(item__slug=item.slug).exists():
			order_item = OrderItem.objects.filter(
				item=item,
				user=request.user,
				ordered=False
			)[0]
			order.items.remove(order_item)
			order_item.delete()
			messages.info(request, "This item was removed to cart")
			return redirect("core:product",slug=slug)
		else:
			#add message saying the user does not have an order
			messages.info(request, "This item was not in your cart")
			return redirect("core:product",slug=slug)
	else:
		#add message saying the user does not have an order
		messages.info(request, "You don't have an active order")
		return redirect("core:product", slug=slug)
		
@login_required
def remove_single_item_from_cart(request,slug):
	item = get_object_or_404(Item,slug=slug)
	order_qs = Order.objects.filter(user=request.user, ordered=False)
	if order_qs.exists():
		order = order_qs[0]
		# check if order item is in the order
		if order.items.filter(item__slug=item.slug).exists():
			order_item = OrderItem.objects.filter(
				item=item,
				user=request.user,
				ordered=False
			)[0]
			if order_item.quantity > 1:
				order_item.quantity -= 1
				order_item.save()
			else:
				order.item.remove(order_item)
			messages.info(request, "This item was updated")
			return redirect("core:order-summary")
		else:
			#add message saying the user does not have an order
			messages.info(request, "This item was not in your cart")
			return redirect("core:product",slug=slug)
	else:
		#add message saying the user does not have an order
		messages.info(request, "You don't have an active order")
		return redirect("core:product",slug=slug)