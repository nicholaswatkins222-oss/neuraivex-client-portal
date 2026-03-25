"""
Seed script — creates admin user, demo client, and sample data.
Run with: python seed.py
"""

import os
import sys
from datetime import datetime, date, timedelta
import bcrypt

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Ensure FERNET_KEY is set for encryption
if not os.environ.get('FERNET_KEY'):
    from cryptography.fernet import Fernet
    generated = Fernet.generate_key().decode()
    print(f"[seed] No FERNET_KEY found. Generated one for this session: {generated}")
    print(f"[seed] Add this to your .env:  FERNET_KEY={generated}")
    os.environ['FERNET_KEY'] = generated

from app import create_app, db
from models import User, Project, Phase, PhaseComment, ApiKey, Invoice, Lead, Message
from encryption import encrypt_value

app = create_app()

with app.app_context():
    print("[seed] Dropping and recreating all tables...")
    db.drop_all()
    db.create_all()

    # ── Admin user ──────────────────────────────────────────────────
    admin_pw = bcrypt.hashpw('admin123'.encode(), bcrypt.gensalt()).decode()
    admin = User(
        email='admin@neuraivex.com',
        password_hash=admin_pw,
        name='Nicholas',
        company='Neuraivex',
        role='admin',
        created_at=datetime(2026, 1, 15),
    )
    db.session.add(admin)

    # ── Demo client ─────────────────────────────────────────────────
    client_pw = bcrypt.hashpw('demo123'.encode(), bcrypt.gensalt()).decode()
    jordan = User(
        email='jordan@apexmarketing.co',
        password_hash=client_pw,
        name='Jordan Rivera',
        company='Apex Marketing Co.',
        role='client',
        created_at=datetime(2026, 2, 1),
        last_login=datetime(2026, 3, 24, 14, 32),
    )
    db.session.add(jordan)
    db.session.flush()  # get IDs

    # ── Project ─────────────────────────────────────────────────────
    project = Project(
        client_id=jordan.id,
        name='Website Redesign + Lead Gen Automation',
        description='Full website rebuild and automated lead capture pipeline with HubSpot integration.',
        created_at=datetime(2026, 2, 3),
    )
    db.session.add(project)
    db.session.flush()

    # ── Phases ──────────────────────────────────────────────────────
    phases_data = [
        ('Discovery', 1, 'done', 'Intake call completed. Business goals, ICP, and technical requirements documented. Competitor audit done. Sitemap approved.', datetime(2026, 3, 3)),
        ('Design', 2, 'done', 'Homepage, services, and contact page mockups delivered. Design system finalized (colors, fonts, components). Client approved all mockups with minor copy tweaks.', datetime(2026, 3, 14)),
        ('Build', 3, 'active', 'Building out all pages based on approved designs. Wiring up the lead gen automation (HubSpot → Slack alert + CRM entry). Contact form with instant notification in progress.', None),
        ('Review', 4, 'pending', 'Full site walkthrough, QA testing, and client approval before going live.', None),
        ('Live', 5, 'pending', 'Domain pointing, final deployment, and handoff documentation delivered.', None),
    ]

    phase_objs = []
    for name, order, status, note, completed_at in phases_data:
        p = Phase(
            project_id=project.id,
            name=name,
            order_index=order,
            status=status,
            note=note,
            completed_at=completed_at,
        )
        db.session.add(p)
        phase_objs.append(p)
    db.session.flush()

    # ── Phase Comments ───────────────────────────────────────────────
    comment1 = PhaseComment(
        phase_id=phase_objs[1].id,  # Design phase
        author_id=jordan.id,
        body='Love the dark theme. Can we make the headline slightly bigger on mobile?',
        created_at=datetime(2026, 3, 14, 17, 47),
    )
    comment2 = PhaseComment(
        phase_id=phase_objs[2].id,  # Build phase
        author_id=jordan.id,
        body='Looking great so far. Will the contact form integrate with our existing HubSpot pipeline?',
        created_at=datetime(2026, 3, 20, 11, 5),
    )
    db.session.add(comment1)
    db.session.add(comment2)

    # ── API Key ──────────────────────────────────────────────────────
    try:
        enc_openai = encrypt_value('sk-proj-test1234567890abcdefghijklmnopqrstuvwxyz')
    except Exception:
        enc_openai = 'ENCRYPTION_FAILED'

    api_key = ApiKey(
        client_id=jordan.id,
        service_name='OpenAI',
        encrypted_value=enc_openai,
        note='Production account',
        created_at=datetime(2026, 3, 10, 9, 30),
    )
    db.session.add(api_key)

    # ── Invoices ─────────────────────────────────────────────────────
    invoices_data = [
        ('INV-001', 'Discovery & Strategy Session', 1500.0, 'paid', date(2026, 2, 15), date(2026, 2, 22)),
        ('INV-002', 'Design Phase — Mockups & System', 2000.0, 'paid', date(2026, 3, 1), date(2026, 3, 8)),
        ('INV-003', 'Build Phase — Website + Automation', 1800.0, 'unpaid', date(2026, 3, 15), date(2026, 4, 1)),
    ]
    for inv_num, desc, amount, status, inv_date, due_date in invoices_data:
        inv = Invoice(
            client_id=jordan.id,
            invoice_number=inv_num,
            description=desc,
            amount=amount,
            status=status,
            date=inv_date,
            due_date=due_date,
        )
        db.session.add(inv)

    # ── Leads ────────────────────────────────────────────────────────
    leads_data = [
        ('Marcus Webb', 'marcus@webbco.com', '(702) 555-0182', 'Contact Form', 'converted', datetime(2026, 3, 24)),
        ('Priya Nair', 'priya@nairdesign.io', '(415) 555-0347', 'Contact Form', 'contacted', datetime(2026, 3, 23)),
        ('Derek Osei', 'derek@oseiconsult.com', '(312) 555-0219', 'Contact Form', 'contacted', datetime(2026, 3, 22)),
        ('Samantha Cruz', 'sam@cruzventures.co', '(213) 555-0094', 'Contact Form', 'no_response', datetime(2026, 3, 21)),
        ('Tyler Huang', 'tyler@huangbiz.com', '(619) 555-0461', 'Contact Form', 'converted', datetime(2026, 3, 20)),
        ('Aisha Kamara', 'aisha@kamaraco.net', '(404) 555-0783', 'Contact Form', 'no_response', datetime(2026, 3, 19)),
        ('Ryan Belfort', 'ryan@belfortmedia.com', '(503) 555-0126', 'Contact Form', 'converted', datetime(2026, 3, 18)),
        ('Yuki Tanaka', 'yuki@tanakastudios.co', '(206) 555-0357', 'Contact Form', 'contacted', datetime(2026, 3, 17)),
    ]
    for name, email, phone, source, status, created_at in leads_data:
        lead = Lead(
            client_id=jordan.id,
            name=name,
            email=email,
            phone=phone,
            source=source,
            status=status,
            created_at=created_at,
        )
        db.session.add(lead)

    # ── Messages ─────────────────────────────────────────────────────
    db.session.flush()  # ensure admin.id and jordan.id are available

    messages_data = [
        (admin.id, jordan.id, "Hey Jordan, welcome to your client portal! This is where we'll stay in sync throughout the project. Feel free to message me here anytime.", datetime(2026, 2, 15, 10, 2), True),
        (jordan.id, admin.id, "This looks awesome. Really clean. Looking forward to seeing the designs!", datetime(2026, 2, 15, 10, 18), True),
        (admin.id, jordan.id, "Design phase is complete — I've attached the mockups for your review. Let me know if you want any changes before we start building. I kept the dark theme you mentioned liking.", datetime(2026, 3, 14, 16, 32), True),
        (jordan.id, admin.id, "Love it! Only one thing — can we make the hero headline a bit bigger on mobile? Otherwise looks great, let's go ahead.", datetime(2026, 3, 14, 17, 47), True),
        (admin.id, jordan.id, "Done — headline is now 10% larger on mobile. Build phase is underway. The automation is about 80% done. Just need your HubSpot API key to finish wiring it up. Can you submit that in the API Keys section?", datetime(2026, 3, 25, 9, 14), False),
    ]
    for sender_id, recipient_id, body, created_at, read in messages_data:
        msg = Message(
            sender_id=sender_id,
            recipient_id=recipient_id,
            body=body,
            read=read,
            created_at=created_at,
        )
        db.session.add(msg)

    db.session.commit()
    print("[seed] Done! Database seeded with:")
    print("  Admin:  admin@neuraivex.com / admin123")
    print("  Client: jordan@apexmarketing.co / demo123")
    print("  Project: Website Redesign + Lead Gen Automation (5 phases)")
    print("  Invoices: 3  |  Leads: 8  |  Messages: 5  |  API Keys: 1")
