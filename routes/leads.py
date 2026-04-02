from flask import Blueprint, render_template, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timedelta
from collections import defaultdict

from models import Lead

leads_bp = Blueprint('leads', __name__)


@leads_bp.route('/leads')
@login_required
def index():
    leads = Lead.query.filter_by(client_id=current_user.id).order_by(Lead.created_at.desc()).all()

    now = datetime.utcnow()
    month_start = datetime(now.year, now.month, 1)
    leads_this_month = sum(1 for l in leads if l.created_at >= month_start)
    total_leads = len(leads)
    converted = sum(1 for l in leads if l.status == 'converted')
    conversion_rate = round((converted / total_leads * 100)) if total_leads else 0

    return render_template(
        'leads.html',
        leads=leads,
        leads_this_month=leads_this_month,
        total_leads=total_leads,
        conversion_rate=conversion_rate,
    )


@leads_bp.route('/leads/chart-data')
@login_required
def chart_data():
    leads = Lead.query.filter_by(client_id=current_user.id).all()

    # Build weekly buckets for the last 8 weeks
    now = datetime.utcnow()
    labels = []
    counts = []

    for i in range(7, -1, -1):
        week_start = now - timedelta(weeks=i+1)
        week_end = now - timedelta(weeks=i)
        week_label = week_start.strftime('%b W') + str(_week_of_month(week_start))
        count = sum(1 for l in leads if week_start <= l.created_at < week_end)
        labels.append(week_label)
        counts.append(count)

    return jsonify({'labels': labels, 'data': counts})


def _week_of_month(dt):
    first_day = dt.replace(day=1)
    return (dt.day + first_day.weekday() - 1) // 7 + 1
