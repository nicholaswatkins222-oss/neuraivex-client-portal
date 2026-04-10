from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from datetime import datetime

from extensions import db, limiter
from models import Message, User
from sanitize import strip_html, check_length

messages_bp = Blueprint('messages', __name__)


def _get_admin():
    return User.query.filter_by(role='admin').first()


@messages_bp.route('/messages')
@login_required
def index():
    admin_user = _get_admin()
    thread = []
    if admin_user:
        thread = Message.query.filter(
            ((Message.sender_id == current_user.id) & (Message.recipient_id == admin_user.id)) |
            ((Message.sender_id == admin_user.id) & (Message.recipient_id == current_user.id))
        ).order_by(Message.created_at.asc()).all()

        # Mark unread messages as read
        for msg in thread:
            if msg.recipient_id == current_user.id and not msg.read:
                msg.read = True
        db.session.commit()

    return render_template('messages.html', thread=thread, admin_user=admin_user)


@messages_bp.route('/messages/send', methods=['POST'])
@login_required
@limiter.limit('20 per minute')
def send():
    body = strip_html(request.form.get('body', '').strip())
    if not body:
        flash('Message cannot be empty.', 'error')
        return redirect(url_for('messages.index'))

    ok, err = check_length(body, 5000, 'Message')
    if not ok:
        flash(err, 'error')
        return redirect(url_for('messages.index'))

    admin_user = _get_admin()
    if not admin_user:
        flash('Cannot send message — no admin found.', 'error')
        return redirect(url_for('messages.index'))

    msg = Message(
        sender_id=current_user.id,
        recipient_id=admin_user.id,
        body=body,
    )
    db.session.add(msg)
    db.session.commit()
    flash('Message sent.', 'success')
    return redirect(url_for('messages.index'))
