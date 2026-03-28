from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime
import bcrypt
import os

from extensions import db
from models import User

auth_bp = Blueprint('auth', __name__)


def _make_reset_token(user_id):
    from itsdangerous import URLSafeTimedSerializer
    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    return s.dumps(user_id, salt='pw-reset')


def _verify_reset_token(token, max_age=3600):
    from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        user_id = s.loads(token, salt='pw-reset', max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None
    return User.query.get(user_id)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if current_user.role == 'admin':
            return redirect(url_for('admin.clients'))
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        user = User.query.filter_by(email=email).first()
        if user and bcrypt.checkpw(password.encode(), user.password_hash.encode()):
            user.last_login = datetime.utcnow()
            db.session.commit()
            login_user(user)
            if user.role == 'admin':
                return redirect(url_for('admin.clients'))
            return redirect(url_for('dashboard.index'))
        else:
            flash('Invalid email or password.', 'error')

    return render_template('login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user = User.query.filter_by(email=email).first()

        # Always show the same message to prevent email enumeration
        if user:
            token = _make_reset_token(user.id)
            reset_url = url_for('auth.reset_password', token=token, _external=True)
            try:
                from sendgrid import SendGridAPIClient
                from sendgrid.helpers.mail import Mail as SGMail
                html_body = f'''
<div style="font-family:'Space Grotesk',Arial,sans-serif; max-width:480px; margin:0 auto; background:#060D1F; color:#e2e8f0; padding:40px 32px; border-radius:12px; border:1px solid rgba(56,196,240,0.15);">
  <div style="font-size:20px; font-weight:700; margin-bottom:4px;">NEURAIVEX</div>
  <p style="color:#8892a4; font-size:13px; margin-top:0;">Client Portal</p>
  <hr style="border:none; border-top:1px solid rgba(56,196,240,0.1); margin:20px 0;" />
  <p style="font-size:15px; margin-bottom:24px;">Hi {user.name},<br><br>We received a request to reset your password. Click the button below — this link expires in <strong>1 hour</strong>.</p>
  <a href="{reset_url}" style="display:inline-block; background:linear-gradient(135deg,#38C4F0,#7C5CE6); color:#fff; text-decoration:none; padding:13px 28px; border-radius:8px; font-weight:600; font-size:14px;">Reset Password →</a>
  <p style="font-size:12px; color:#8892a4; margin-top:28px;">If you didn't request this, you can safely ignore this email. Your password won't change.</p>
</div>'''
                msg = SGMail(
                    from_email='nicholas@neuraivex.com',
                    to_emails=user.email,
                    subject='Reset your Neuraivex portal password',
                    html_content=html_body
                )
                sg = SendGridAPIClient(os.environ.get('SENDGRID_API_KEY'))
                response = sg.send(msg)
                current_app.logger.info(f'SendGrid response: {response.status_code} {response.body}')
            except Exception as e:
                current_app.logger.error(f'Password reset email failed: {e}')
                import traceback
                current_app.logger.error(traceback.format_exc())

        flash('If that email is registered, you\'ll receive a reset link shortly.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('forgot_password.html')


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    user = _verify_reset_token(token)
    if not user:
        flash('That reset link is invalid or has expired.', 'error')
        return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')

        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'error')
            return render_template('reset_password.html', token=token)

        if password != confirm:
            flash('Passwords do not match.', 'error')
            return render_template('reset_password.html', token=token)

        user.password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        db.session.commit()
        flash('Password updated. You can now sign in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('reset_password.html', token=token)
