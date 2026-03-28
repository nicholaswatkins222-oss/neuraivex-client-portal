import os
import stripe
import requests
from flask import Blueprint, request, abort

from extensions import db
from models import Invoice

stripe_bp = Blueprint('stripe', __name__)


def _telegram_ping(text):
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        return
    try:
        requests.post(
            f'https://api.telegram.org/bot{token}/sendMessage',
            json={'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'},
            timeout=5,
        )
    except Exception:
        pass


@stripe_bp.route('/stripe/webhook', methods=['POST'])
def webhook():
    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature', '')
    webhook_secret = os.environ.get('STRIPE_WEBHOOK_SECRET', '')

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except stripe.error.SignatureVerificationError:
        abort(400)
    except Exception:
        abort(400)

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        payment_link_id = session.get('payment_link')

        if payment_link_id:
            invoice = Invoice.query.filter_by(stripe_payment_link_id=payment_link_id).first()
            if invoice and invoice.status != 'paid':
                invoice.status = 'paid'
                db.session.commit()

                client = invoice.client
                amount = '${:,.0f}'.format(invoice.amount)
                _telegram_ping(
                    f'<b>Payment received</b>\n'
                    f'Client: {client.name} ({client.company or client.email})\n'
                    f'Invoice: {invoice.invoice_number} — {invoice.description}\n'
                    f'Amount: {amount}'
                )

    return '', 200
