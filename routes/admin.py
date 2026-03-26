from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from flask_login import login_required, current_user
from datetime import datetime, date
import bcrypt

from extensions import db
from models import User, Project, Phase, PhaseComment, ApiKey, Invoice, Lead, Message
from encryption import decrypt_value

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
    project = Project.query.filter_by(client_id=client_id).first()
    phases = []
    if project:
        phases = project.phases.order_by(Phase.order_index).all()

    invoices = Invoice.query.filter_by(client_id=client_id).order_by(Invoice.date.desc()).all()
    leads = Lead.query.filter_by(client_id=client_id).order_by(Lead.created_at.desc()).limit(10).all()
    keys = ApiKey.query.filter_by(client_id=client_id).order_by(ApiKey.created_at.desc()).all()

    unread_from_client = Message.query.filter_by(sender_id=client_id, recipient_id=current_user.id, read=False).count()

    return render_template(
        'admin/client_detail.html',
        client=client,
        project=project,
        phases=phases,
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
            new_note = request.form.get(f'note_{phase.id}', '').strip()
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
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip() or None
        phone = request.form.get('phone', '').strip() or None
        source = request.form.get('source', '').strip() or None
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


@admin_bp.route('/messages/send', methods=['POST'])
@login_required
@admin_required
def message_send():
    client_id = request.form.get('client_id', type=int)
    body = request.form.get('body', '').strip()

    if not client_id or not body:
        flash('Client and message body required.', 'error')
        return redirect(url_for('admin.message_inbox'))

    client = User.query.get_or_404(client_id)
    msg = Message(
        sender_id=current_user.id,
        recipient_id=client_id,
        body=body,
    )
    db.session.add(msg)
    db.session.commit()
    return redirect(url_for('admin.message_thread', client_id=client_id))
