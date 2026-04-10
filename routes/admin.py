from flask import Blueprint, render_template, redirect, url_for, request, flash, abort, jsonify, current_app
from flask_login import login_required, current_user
from flask_mail import Message as MailMessage
from datetime import datetime, date
import bcrypt
import os
import stripe

from extensions import db, mail
from models import User, Project, Phase, PhaseComment, ApiKey, Invoice, Lead, Message
from encryption import decrypt_value
from sanitize import strip_html, check_length

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            abort(403)
        return f(*args, **kwargs)
    return decorated


@admin_bp.route('/')
@login_required
@admin_required
def index():
    return redirect(url_for('admin.clients'))


@admin_bp.route('/clients')
@login_required
@admin_required
def clients():
    clients = User.query.filter_by(role='client').order_by(User.created_at.desc()).all()
    return render_template('admin/clients.html', clients=clients)


@admin_bp.route('/client/<int:client_id>')
@login_required
@admin_required
def client_detail(client_id):
    client = User.query.get_or_404(client_id)
    projects_raw = Project.query.filter_by(client_id=client_id).order_by(Project.created_at).all()
    projects_with_phases = []
    for proj in projects_raw:
        phases = proj.phases.order_by(Phase.order_index).all()
        projects_with_phases.append({'project': proj, 'phases': phases})

    invoices = Invoice.query.filter_by(client_id=client_id).order_by(Invoice.date.desc()).all()
    leads = Lead.query.filter_by(client_id=client_id).order_by(Lead.created_at.desc()).limit(10).all()
    keys = ApiKey.query.filter_by(client_id=client_id).order_by(ApiKey.created_at.desc()).all()

    unread_from_client = Message.query.filter_by(sender_id=client_id, recipient_id=current_user.id, read=False).count()

    return render_template(
        'admin/client_detail.html',
        client=client,
        projects_with_phases=projects_with_phases,
        invoices=invoices,
        leads=leads,
        keys=keys,
        unread_from_client=unread_from_client,
    )


@admin_bp.route('/project/<int:project_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def project_edit(project_id):
    project = Project.query.get_or_404(project_id)
    phases = project.phases.order_by(Phase.order_index).all()

    if request.method == 'POST':
        for phase in phases:
            new_status = request.form.get(f'status_{phase.id}')
            new_note = strip_html(request.form.get(f'note_{phase.id}', '').strip())
            if new_status in ('pending', 'active', 'done'):
                if new_status == 'done' and phase.status != 'done':
                    phase.completed_at = datetime.utcnow()
                elif new_status != 'done':
                    phase.completed_at = None
                phase.status = new_status
            phase.note = new_note or None
        db.session.commit()
        flash('Project phases updated.', 'success')
        return redirect(url_for('admin.project_edit', project_id=project_id))

    return render_template('admin/project_edit.html', project=project, phases=phases)


@admin_bp.route('/keys/<int:client_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def keys_view(client_id):
    client = User.query.get_or_404(client_id)
    decrypted_keys = None
    confirmed = False

    if request.method == 'POST':
        password = request.form.get('password', '')
        if bcrypt.checkpw(password.encode(), current_user.password_hash.encode()):
            keys = ApiKey.query.filter_by(client_id=client_id).order_by(ApiKey.created_at.desc()).all()
            decrypted_keys = []
            for k in keys:
                try:
                    plain = decrypt_value(k.encrypted_value)
                except Exception:
                    plain = '[decryption error]'
                decrypted_keys.append({'key': k, 'plain': plain})
            confirmed = True
        else:
            flash('Incorrect password.', 'error')

    keys = ApiKey.query.filter_by(client_id=client_id).order_by(ApiKey.created_at.desc()).all()
    return render_template('admin/keys_view.html', client=client, keys=keys, decrypted_keys=decrypted_keys, confirmed=confirmed)


@admin_bp.route('/client/add', methods=['GET', 'POST'])
@login_required
@admin_required
def client_add():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        company = request.form.get('company', '').strip() or None
        password = request.form.get('password', '').strip()
        project_name = request.form.get('project_name', '').strip()
        project_desc = request.form.get('project_description', '').strip() or None
        phase_names = [p.strip() for p in request.form.get('phases', '').split('\n') if p.strip()]
        active_phase = request.form.get('active_phase', '1')

        # Invoice fields (optional)
        inv_description = request.form.get('inv_description', '').strip()
        inv_amount = request.form.get('inv_amount', '').strip()
        inv_status = request.form.get('inv_status', 'unpaid')
        inv_date_str = request.form.get('inv_date', '')
        inv_due_str = request.form.get('inv_due', '')

        if not all([name, email, password, project_name, phase_names]):
            flash('Name, email, password, project name, and at least one phase are required.', 'error')
            return render_template('admin/client_add.html')

        if User.query.filter_by(email=email).first():
            flash('A user with that email already exists.', 'error')
            return render_template('admin/client_add.html')

        try:
            active_idx = int(active_phase)
        except ValueError:
            active_idx = 1

        pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        client = User(email=email, password_hash=pw_hash, name=name, company=company, role='client')
        db.session.add(client)
        db.session.flush()

        project = Project(client_id=client.id, name=project_name, description=project_desc)
        db.session.add(project)
        db.session.flush()

        for i, phase_name in enumerate(phase_names, 1):
            if i < active_idx:
                status = 'done'
                completed_at = datetime.utcnow()
            elif i == active_idx:
                status = 'active'
                completed_at = None
            else:
                status = 'pending'
                completed_at = None
            db.session.add(Phase(
                project_id=project.id,
                name=phase_name,
                order_index=i,
                status=status,
                completed_at=completed_at,
            ))

        # Optional invoice
        if inv_description and inv_amount and inv_date_str and inv_due_str:
            try:
                inv = Invoice(
                    client_id=client.id,
                    invoice_number='INV-001',
                    description=inv_description,
                    amount=float(inv_amount),
                    status=inv_status,
                    date=date.fromisoformat(inv_date_str),
                    due_date=date.fromisoformat(inv_due_str),
                )
                db.session.add(inv)
            except (ValueError, TypeError):
                pass

        # Send welcome message
        msg = Message(
            sender_id=current_user.id,
            recipient_id=client.id,
            body=f"Hey {name.split()[0]}, welcome to your Neuraivex client portal! This is where we'll stay in sync throughout the project. Feel free to message me here anytime.",
        )
        db.session.add(msg)

        db.session.commit()

        # Auto-email login credentials with a password reset link (never send plaintext passwords)
        try:
            from routes.auth import _make_reset_token
            portal_url = os.environ.get('PORTAL_URL', 'https://portal.neuraivex.com')
            reset_token = _make_reset_token(client.id)
            reset_url = url_for('auth.reset_password', token=reset_token, _external=True)
            from sendgrid import SendGridAPIClient
            from sendgrid.helpers.mail import Mail as SGMail
            html_body = f"""
<div style="font-family:'Space Grotesk',Arial,sans-serif; max-width:520px; margin:0 auto; background:#060D1F; color:#e2e8f0; padding:40px 32px; border-radius:12px; border:1px solid rgba(56,196,240,0.15);">
  <div style="font-size:20px; font-weight:700; margin-bottom:4px;">NEURAIVEX</div>
  <p style="color:#8892a4; font-size:13px; margin-top:0;">Client Portal</p>
  <hr style="border:none; border-top:1px solid rgba(56,196,240,0.1); margin:20px 0;" />
  <h2 style="margin-bottom:4px;">Welcome, {name.split()[0]}!</h2>
  <p style="color:#8892a4; margin-top:4px;">Your client dashboard is ready.</p>
  <table style="margin:20px 0; border-collapse:collapse; width:100%;">
    <tr><td style="padding:8px 0; font-weight:600; width:80px; color:#8892a4;">URL</td><td><a href="{portal_url}" style="color:#38C4F0;">{portal_url}</a></td></tr>
    <tr><td style="padding:8px 0; font-weight:600; color:#8892a4;">Email</td><td>{email}</td></tr>
  </table>
  <p style="font-size:14px;">Click below to set your password and access your portal — this link expires in <strong>24 hours</strong>.</p>
  <a href="{reset_url}" style="display:inline-block; background:linear-gradient(135deg,#38C4F0,#7C5CE6); color:#fff; text-decoration:none; padding:13px 28px; border-radius:8px; font-weight:600; font-size:14px;">Set Your Password →</a>
  <p style="font-size:12px; color:#8892a4; margin-top:28px;">Reply to this email or message me in the portal if you have any questions.</p>
  <p style="margin-top:24px; font-size:13px;">— Nicholas<br><span style="color:#8892a4;">Neuraivex</span></p>
</div>"""
            sg_msg = SGMail(
                from_email='nicholas@neuraivex.com',
                to_emails=email,
                subject='Your Neuraivex Client Portal Access',
                html_content=html_body,
            )
            sg = SendGridAPIClient(os.environ.get('SENDGRID_API_KEY'))
            sg.send(sg_msg)
        except Exception as e:
            current_app.logger.warning(f'Welcome email failed for {email}: {e}')

        flash(f'Client account created for {name}. Welcome email sent.', 'success')
        return redirect(url_for('admin.client_detail', client_id=client.id))

    return render_template('admin/client_add.html')


@admin_bp.route('/invoice/add', methods=['GET', 'POST'])
@login_required
@admin_required
def invoice_add():
    clients = User.query.filter_by(role='client').order_by(User.name).all()

    if request.method == 'POST':
        client_id = request.form.get('client_id', type=int)
        invoice_number = request.form.get('invoice_number', '').strip()
        description = request.form.get('description', '').strip()
        amount = request.form.get('amount', type=float)
        status = request.form.get('status', 'unpaid')
        date_str = request.form.get('date', '')
        due_date_str = request.form.get('due_date', '')
        pdf_url = request.form.get('pdf_url', '').strip() or None

        if not all([client_id, invoice_number, description, amount, date_str, due_date_str]):
            flash('All fields except PDF URL are required.', 'error')
            return render_template('admin/invoice_add.html', clients=clients)

        try:
            inv_date = date.fromisoformat(date_str)
            inv_due = date.fromisoformat(due_date_str)
        except ValueError:
            flash('Invalid date format.', 'error')
            return render_template('admin/invoice_add.html', clients=clients)

        invoice = Invoice(
            client_id=client_id,
            invoice_number=invoice_number,
            description=description,
            amount=amount,
            status=status,
            date=inv_date,
            due_date=inv_due,
            pdf_url=pdf_url,
        )
        db.session.add(invoice)
        db.session.commit()
        flash('Invoice added.', 'success')
        return redirect(url_for('admin.client_detail', client_id=client_id))

    return render_template('admin/invoice_add.html', clients=clients)


@admin_bp.route('/lead/add', methods=['GET', 'POST'])
@login_required
@admin_required
def lead_add():
    clients = User.query.filter_by(role='client').order_by(User.name).all()

    if request.method == 'POST':
        client_id = request.form.get('client_id', type=int)
        name = strip_html(request.form.get('name', '').strip())
        email = strip_html(request.form.get('email', '').strip()) or None
        phone = strip_html(request.form.get('phone', '').strip()) or None
        source = strip_html(request.form.get('source', '').strip()) or None
        status = request.form.get('status', 'new')

        if not client_id or not name:
            flash('Client and lead name are required.', 'error')
            return render_template('admin/lead_add.html', clients=clients)

        lead = Lead(
            client_id=client_id,
            name=name,
            email=email,
            phone=phone,
            source=source,
            status=status,
        )
        db.session.add(lead)
        db.session.commit()
        flash('Lead added.', 'success')
        return redirect(url_for('admin.client_detail', client_id=client_id))

    return render_template('admin/lead_add.html', clients=clients)


@admin_bp.route('/messages')
@login_required
@admin_required
def message_inbox():
    clients = User.query.filter_by(role='client').order_by(User.name).all()
    threads = []
    for client in clients:
        last_msg = Message.query.filter(
            ((Message.sender_id == client.id) & (Message.recipient_id == current_user.id)) |
            ((Message.sender_id == current_user.id) & (Message.recipient_id == client.id))
        ).order_by(Message.created_at.desc()).first()
        unread = Message.query.filter_by(sender_id=client.id, recipient_id=current_user.id, read=False).count()
        threads.append({'client': client, 'last_msg': last_msg, 'unread': unread})

    # Sort: unread first, then by last message time
    threads.sort(key=lambda t: (-(t['unread'] > 0), -(t['last_msg'].created_at.timestamp() if t['last_msg'] else 0)))
    return render_template('admin/message_inbox.html', threads=threads)


@admin_bp.route('/messages/<int:client_id>')
@login_required
@admin_required
def message_thread(client_id):
    client = User.query.get_or_404(client_id)
    thread = Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.recipient_id == client_id)) |
        ((Message.sender_id == client_id) & (Message.recipient_id == current_user.id))
    ).order_by(Message.created_at.asc()).all()

    # Mark client messages as read
    for msg in thread:
        if msg.sender_id == client_id and not msg.read:
            msg.read = True
    db.session.commit()

    return render_template('admin/message_inbox.html', thread=thread, active_client=client, threads=_get_threads())


def _get_threads():
    admin = User.query.filter_by(role='admin').first()
    clients = User.query.filter_by(role='client').order_by(User.name).all()
    threads = []
    for client in clients:
        last_msg = Message.query.filter(
            ((Message.sender_id == client.id) & (Message.recipient_id == admin.id)) |
            ((Message.sender_id == admin.id) & (Message.recipient_id == client.id))
        ).order_by(Message.created_at.desc()).first()
        unread = Message.query.filter_by(sender_id=client.id, recipient_id=admin.id, read=False).count()
        threads.append({'client': client, 'last_msg': last_msg, 'unread': unread})
    threads.sort(key=lambda t: (-(t['unread'] > 0), -(t['last_msg'].created_at.timestamp() if t['last_msg'] else 0)))
    return threads


@admin_bp.route('/invoice/<int:invoice_id>/generate-payment-link', methods=['POST'])
@login_required
@admin_required
def generate_payment_link(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)

    stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
    if not stripe.api_key:
        return jsonify({'error': 'STRIPE_SECRET_KEY not configured'}), 500

    try:
        # Create a one-time price for this invoice amount
        price = stripe.Price.create(
            currency='usd',
            unit_amount=int(invoice.amount * 100),  # cents
            product_data={'name': f'{invoice.invoice_number} — {invoice.description}'},
        )

        portal_url = os.environ.get('PORTAL_URL', 'https://portal.neuraivex.com')
        payment_link = stripe.PaymentLink.create(
            line_items=[{'price': price.id, 'quantity': 1}],
            after_completion={'type': 'redirect', 'redirect': {'url': f'{portal_url}/invoices'}},
            metadata={'invoice_id': str(invoice.id)},
            payment_intent_data={'metadata': {'invoice_id': str(invoice.id)}},
        )

        invoice.stripe_payment_link = payment_link.url
        invoice.stripe_payment_link_id = payment_link.id
        db.session.commit()

        return jsonify({'url': payment_link.url})
    except stripe.error.StripeError as e:
        return jsonify({'error': str(e)}), 500


@admin_bp.route('/messages/send', methods=['POST'])
@login_required
@admin_required
def message_send():
    client_id = request.form.get('client_id', type=int)
    body = strip_html(request.form.get('body', '').strip())

    if not client_id or not body:
        flash('Client and message body required.', 'error')
        return redirect(url_for('admin.message_inbox'))

    ok, err = check_length(body, 5000, 'Message')
    if not ok:
        flash(err, 'error')
        return redirect(url_for('admin.message_thread', client_id=client_id))

    client = User.query.get_or_404(client_id)
    msg = Message(
        sender_id=current_user.id,
        recipient_id=client_id,
        body=body,
    )
    db.session.add(msg)
    db.session.commit()
    flash('Message sent.', 'success')
    return redirect(url_for('admin.message_thread', client_id=client_id))
