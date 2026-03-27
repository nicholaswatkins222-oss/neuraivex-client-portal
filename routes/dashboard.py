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

    # All projects with phases
    projects_raw = Project.query.filter_by(client_id=current_user.id).order_by(Project.created_at).all()
    projects_with_phases = []
    current_phase = None
    for proj in projects_raw:
        phases = proj.phases.order_by(Phase.order_index).all()
        active = next((p for p in phases if p.status == 'active'), None)
        if current_phase is None and active:
            current_phase = active
        projects_with_phases.append({'project': proj, 'phases': phases})

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
        projects_with_phases=projects_with_phases,
        recent_messages=recent_messages,
        admin_user=admin_user,
        now=now,
    )


def _get_admin():
    from models import User
    return User.query.filter_by(role='admin').first()
