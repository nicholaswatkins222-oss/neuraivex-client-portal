from flask import Blueprint, render_template
from flask_login import login_required, current_user

from models import Invoice

invoices_bp = Blueprint('invoices', __name__)


@invoices_bp.route('/invoices')
@login_required
def index():
    invoices = Invoice.query.filter_by(client_id=current_user.id).order_by(Invoice.date.desc()).all()

    total_paid = sum(inv.amount for inv in invoices if inv.status == 'paid')
    total_unpaid = sum(inv.amount for inv in invoices if inv.status == 'unpaid')
    total_invoiced = sum(inv.amount for inv in invoices)

    unpaid_invoices = [inv for inv in invoices if inv.status == 'unpaid']
    next_due = min((inv.due_date for inv in unpaid_invoices), default=None)

    return render_template(
        'invoices.html',
        invoices=invoices,
        total_paid=total_paid,
        total_unpaid=total_unpaid,
        total_invoiced=total_invoiced,
        next_due=next_due,
    )
