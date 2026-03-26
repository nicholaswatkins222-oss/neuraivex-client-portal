from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user

from extensions import db
from models import ApiKey
from encryption import encrypt_value

keys_bp = Blueprint('keys', __name__)


@keys_bp.route('/keys', methods=['GET', 'POST'])
@login_required
def index():
    if request.method == 'POST':
        service_name = request.form.get('service_name', '').strip()
        api_key_value = request.form.get('api_key_value', '').strip()
        note = request.form.get('note', '').strip()

        if not service_name or not api_key_value:
            flash('Service name and key are required.', 'error')
            return redirect(url_for('keys.index'))

        try:
            encrypted = encrypt_value(api_key_value)
        except ValueError as e:
            flash(f'Encryption error: {e}', 'error')
            return redirect(url_for('keys.index'))

        key = ApiKey(
            client_id=current_user.id,
            service_name=service_name,
            encrypted_value=encrypted,
            note=note or None,
        )
        db.session.add(key)
        db.session.commit()
        flash('Key submitted and encrypted successfully.', 'success')
        return redirect(url_for('keys.index'))

    keys = ApiKey.query.filter_by(client_id=current_user.id).order_by(ApiKey.created_at.desc()).all()
    return render_template('keys.html', keys=keys)


@keys_bp.route('/keys/<int:key_id>/delete', methods=['POST'])
@login_required
def delete(key_id):
    key = ApiKey.query.get_or_404(key_id)
    if key.client_id != current_user.id:
        flash('Access denied.', 'error')
        return redirect(url_for('keys.index'))
    db.session.delete(key)
    db.session.commit()
    flash('Key deleted.', 'success')
    return redirect(url_for('keys.index'))
