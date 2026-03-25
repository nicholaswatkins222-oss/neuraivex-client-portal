from flask import Blueprint, render_template
from flask_login import login_required, current_user
from datetime import datetime, date

from models import Project, Phase, Invoice, Message, Lead

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
@login_required
def index():
    if current_user.role == 'admin':
        from flask import redirect, url_for
        return redirect(url_for('admin.clients'))

    # Stats
    now = datetime.utcnow()
    leads_this_month = Lead.query.filter(
        Lead.client_id == current_user.id,
        Lead.created_at >= datetime(now.year, now.month, 1)
    ).count()

    # Current active phase
    project = Project.query.filter_by(client_id=current_user.id).first()
    current_phase = None
    all_phases = []
    if project:
        all_phases = project.phases.order_by(Phase.order_index).all()
        current_phase = next((p for p in all_phases if p.status == 'active'), None)
        if not current_phase:
            current_phase = next((p for p in all_phases if p.status == 'pending'), None)

    # Open invoice total
    open_invoices = Invoice.query.filter_by(client_id=current_user.id, status='unpaid').all()
    open_total = sum(inv.amount for inv in open_invoices)
    next_due = min((inv.due_date for inv in open_invoices), default=None)

    # Unread messages (messages sent to current user that are unread)
    unread_count = Message.query.filter_by(recipient_id=current_user.id, read=False).count()

    # Recent messages
    admin_user = _get_admin()
    recent_messages = []
    if admin_user:
        recent_messages = Message.query.filter(
            ((Message.sender_id == current_user.id) & (Message.recipient_id == admin_user.id)) |
            ((Message.sender_id == admin_user.id) & (Message.recipient_id == current_user.id))
        ).order_by(Message.created_at.desc()).limit(3).all()
        recent_messages = list(reversed(recent_messages))

    return render_template(
        'dashboard.html',
        leads_this_month=leads_this_month,
        current_phase=current_phase,
        open_total=open_total,
        next_due=next_due,
        unread_count=unread_count,
        project=project,
        all_phases=all_phases,
        recent_messages=recent_messages,
        admin_user=admin_user,
        now=now,
    )


def _get_admin():
    from models import User
    return User.query.filter_by(role='admin').first()
