import os
import json
import requests
from flask import Blueprint, request, abort, current_app

import stripe

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
    except Exception as e:
        current_app.logger.error(f'Stripe webhook signature error: {e}')
        abort(400)

    try:
        # Support both dict-style (stripe <5) and attribute-style (stripe 5+) access
        event_type = event.get('type') if hasattr(event, 'get') else event.type
        if event_type == 'checkout.session.completed':
            data_obj = event.get('data', {}).get('object', {}) if hasattr(event, 'get') else event.data.object

            # payment_link field — try dict access then attribute access
            if hasattr(data_obj, 'get'):
                payment_link_id = data_obj.get('payment_link')
            else:
                payment_link_id = getattr(data_obj, 'payment_link', None)

            if payment_link_id:
                invoice = Invoice.query.filter_by(stripe_payment_link_id=str(payment_link_id)).first()
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
    except Exception as e:
        current_app.logger.error(f'Stripe webhook handler error: {e}')
        # Still return 200 so Stripe stops retrying — error is logged for debugging
        return '', 200

    return '', 200
