from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from datetime import datetime

from app import db
from models import Project, Phase, PhaseComment

project_bp = Blueprint('project', __name__)


@project_bp.route('/project')
@login_required
def index():
    project = Project.query.filter_by(client_id=current_user.id).first()
    phases = []
    if project:
        phases = project.phases.order_by(Phase.order_index).all()
    return render_template('project.html', project=project, phases=phases)


@project_bp.route('/project/comment', methods=['POST'])
@login_required
def comment():
    phase_id = request.form.get('phase_id', type=int)
    body = request.form.get('body', '').strip()

    if not phase_id or not body:
        flash('Comment cannot be empty.', 'error')
        return redirect(url_for('project.index'))

    phase = Phase.query.get_or_404(phase_id)
    # Verify the phase belongs to this client
    if phase.project.client_id != current_user.id:
        flash('Access denied.', 'error')
        return redirect(url_for('project.index'))

    comment = PhaseComment(phase_id=phase_id, author_id=current_user.id, body=body)
    db.session.add(comment)
    db.session.commit()
    flash('Feedback submitted — Nicholas will see this shortly.', 'success')
    return redirect(url_for('project.index'))
