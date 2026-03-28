from flask import Flask
from extensions import db, login_manager, csrf, mail
import os


def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-in-prod')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///portal.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SESSION_COOKIE_SECURE'] = os.environ.get('FLASK_ENV') == 'production'
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

    app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'mail.privateemail.com')
    app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 465))
    app.config['MAIL_USE_SSL'] = os.environ.get('MAIL_USE_SSL', 'true').lower() == 'true'
    app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'false').lower() == 'true'
    app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
    app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
    app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_FROM', os.environ.get('MAIL_USERNAME'))

    db.init_app(app)
    mail.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    login_manager.login_view = 'auth.login'

    from routes.auth import auth_bp
    from routes.dashboard import dashboard_bp
    from routes.project import project_bp
    from routes.api_keys import keys_bp
    from routes.leads import leads_bp
    from routes.invoices import invoices_bp
    from routes.messages import messages_bp
    from routes.admin import admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(project_bp)
    app.register_blueprint(keys_bp)
    app.register_blueprint(leads_bp)
    app.register_blueprint(invoices_bp)
    app.register_blueprint(messages_bp)
    app.register_blueprint(admin_bp)

    # Cross-platform date formatting filter (avoids %-d which only works on Linux)
    import re as _re
    @app.template_filter('strfdate')
    def strfdate_filter(dt, fmt):
        if dt is None:
            return ''
        safe_fmt = fmt.replace('%-', '%')
        result = dt.strftime(safe_fmt)
        result = _re.sub(r'(?<!\d)0(\d)(?!\d)', r'\1', result)
        return result

    with app.app_context():
        db.create_all()

    return app


app = create_app()

if __name__ == '__main__':
    app.run(debug=True)
