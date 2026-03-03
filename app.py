import os
import secrets
from datetime import datetime
from urllib.parse import urljoin

from flask import (
    Flask, render_template, request, redirect, url_for, flash, session, abort
)
from flask_login import (
    LoginManager, login_user, login_required, logout_user, current_user, UserMixin
)
from werkzeug.security import generate_password_hash, check_password_hash

from db import get_db, close_db, init_db, query_one, query_all, execute
from email_utils import send_email


def create_app() -> Flask:
    app = Flask(__name__, instance_relative_config=True)

    # IMPORTANT: Change cette clé en production
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-change-me')
    app.config['DATABASE'] = os.getenv('DATABASE', 'savoir_reussite.sqlite')
    app.config['APP_BASE_URL'] = os.getenv('APP_BASE_URL', 'http://127.0.0.1:5000')

    # Ferme la DB après la requête
    app.teardown_appcontext(close_db)

    # Login
    login_manager = LoginManager()
    login_manager.login_view = 'login'
    login_manager.init_app(app)

    class User(UserMixin):
        def __init__(self, row):
            self.id = row['id']
            self.email = row['email']
            self.display_name = row['display_name']
            self.is_admin = bool(row['is_admin'])

        @staticmethod
        def get(user_id: int):
            row = query_one('SELECT * FROM users WHERE id = ?', (user_id,))
            return User(row) if row else None

    @login_manager.user_loader
    def load_user(user_id: str):
        try:
            uid = int(user_id)
        except ValueError:
            return None
        return User.get(uid)

    # ----------------------------
    # CSRF minimal (sans dépendances)
    # ----------------------------
    def ensure_csrf_token() -> str:
        token = session.get('_csrf_token')
        if not token:
            token = secrets.token_urlsafe(32)
            session['_csrf_token'] = token
        return token

    def verify_csrf() -> None:
        token = session.get('_csrf_token')
        form_token = request.form.get('csrf_token')
        if not token or not form_token or token != form_token:
            abort(400, description='CSRF token invalide')

    @app.context_processor
    def inject_globals():
        return {
            'csrf_token': ensure_csrf_token(),
            'app_name': 'Savoir & Réussite'
        }

    # ----------------------------
    # Commande init DB
    # ----------------------------
    @app.cli.command('initdb')
    def initdb_command():
        init_db()
        print('Base de données initialisée.')

    # ----------------------------
    # Helpers
    # ----------------------------
    def now_iso() -> str:
        return datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'

    def base_url() -> str:
        return app.config.get('APP_BASE_URL', 'http://127.0.0.1:5000').rstrip('/') + '/'

    def topic_url(topic_id: int) -> str:
        return urljoin(base_url(), url_for('topic', topic_id=topic_id).lstrip('/'))

    def get_user_settings(user_id: int):
        row = query_one('SELECT * FROM user_settings WHERE user_id = ?', (user_id,))
        if row:
            return row
        # crée réglages par défaut
        execute(
            'INSERT INTO user_settings (user_id, notify_on_my_topic_reply, notify_on_followed_topic_reply) VALUES (?, 1, 1)',
            (user_id,)
        )
        return query_one('SELECT * FROM user_settings WHERE user_id = ?', (user_id,))

    def send_new_reply_notifications(topic_id: int, reply_id: int):
        # Récupère le topic, auteur, etc.
        topic = query_one(
            'SELECT t.*, u.email as author_email, u.display_name as author_name, u.id as author_id '
            'FROM topics t JOIN users u ON u.id = t.user_id WHERE t.id = ?',
            (topic_id,)
        )
        if not topic:
            return

        reply = query_one(
            'SELECT r.*, u.display_name as replier_name, u.email as replier_email '
            'FROM replies r JOIN users u ON u.id = r.user_id WHERE r.id = ?',
            (reply_id,)
        )
        if not reply:
            return

        # 1) Email à l'auteur du topic
        if int(topic['author_id']) != int(reply['user_id']):
            settings = get_user_settings(int(topic['author_id']))
            if int(settings['notify_on_my_topic_reply']) == 1:
                subject = f"Nouvelle réponse à votre sujet : {topic['title']}"
                link = topic_url(topic_id)
                html = render_template('emails/new_reply_author.html', topic=topic, reply=reply, link=link)
                text = f"Nouvelle réponse à votre sujet '{topic['title']}'. Voir: {link}"
                send_email(topic['author_email'], subject, html, text)

        # 2) Emails aux abonnés (followers) du topic
        followers = query_all(
            'SELECT f.user_id, u.email, u.display_name '
            'FROM follows f JOIN users u ON u.id = f.user_id '
            'WHERE f.topic_id = ? AND f.user_id != ?',
            (topic_id, reply['user_id'])
        )
        link = topic_url(topic_id)
        for fu in followers:
            # Ne pas renvoyer à l'auteur si déjà notifié (mais c'est ok si doublon, on évite)
            if int(fu['user_id']) == int(topic['author_id']):
                continue
            settings = get_user_settings(int(fu['user_id']))
            if int(settings['notify_on_followed_topic_reply']) != 1:
                continue
            subject = f"Nouveau message sur un sujet que vous suivez : {topic['title']}"
            html = render_template('emails/new_reply_follower.html', topic=topic, reply=reply, link=link, follower=fu)
            text = f"Nouveau message sur '{topic['title']}'. Voir: {link}"
            send_email(fu['email'], subject, html, text)

        # 3) OPTION (désactivée par défaut) : broadcast à tous les utilisateurs
        #    ⚠️ Peut être perçu comme du spam, utilisez avec prudence.
        if os.getenv('BROADCAST_NEW_REPLIES_TO_ALL', '0').strip() == '1':
            all_users = query_all('SELECT id, email FROM users WHERE id != ?', (reply['user_id'],))
            subject = f"Nouvelle réponse sur Savoir & Réussite : {topic['title']}"
            html = render_template('emails/new_reply_broadcast.html', topic=topic, reply=reply, link=link)
            text = f"Nouvelle réponse: {topic['title']} — {link}"
            for u in all_users:
                send_email(u['email'], subject, html, text)

    # ----------------------------
    # Routes
    # ----------------------------
    @app.route('/')
    def index():
        q = (request.args.get('q') or '').strip()
        category = (request.args.get('category') or '').strip()

        params = []
        where = []
        if q:
            where.append('(t.title LIKE ? OR t.body LIKE ? OR t.tags LIKE ?)')
            like = f"%{q}%"
            params.extend([like, like, like])
        if category:
            where.append('t.category = ?')
            params.append(category)

        where_sql = ('WHERE ' + ' AND '.join(where)) if where else ''

        topics = query_all(
            f"""
            SELECT t.*, u.display_name
            FROM topics t
            JOIN users u ON u.id = t.user_id
            {where_sql}
            ORDER BY t.created_at DESC
            LIMIT 50
            """,
            tuple(params)
        )

        categories = query_all('SELECT DISTINCT category FROM topics WHERE category IS NOT NULL AND category != "" ORDER BY category')
        return render_template('index.html', topics=topics, q=q, category=category, categories=categories)

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if request.method == 'POST':
            verify_csrf()
            email = (request.form.get('email') or '').strip().lower()
            display_name = (request.form.get('display_name') or '').strip()
            password = request.form.get('password') or ''

            if not email or '@' not in email:
                flash('Email invalide.', 'danger')
                return redirect(url_for('register'))
            if not display_name:
                flash('Veuillez choisir un nom (pseudo).', 'danger')
                return redirect(url_for('register'))
            if len(password) < 8:
                flash('Mot de passe trop court (8 caractères minimum).', 'danger')
                return redirect(url_for('register'))

            existing = query_one('SELECT id FROM users WHERE email = ?', (email,))
            if existing:
                flash('Cet email est déjà utilisé. Connectez-vous.', 'warning')
                return redirect(url_for('login'))

            pwd_hash = generate_password_hash(password)
            user_id = execute(
                'INSERT INTO users (email, password_hash, display_name, created_at) VALUES (?, ?, ?, ?)',
                (email, pwd_hash, display_name, now_iso())
            )
            # Settings par défaut
            execute(
                'INSERT INTO user_settings (user_id, notify_on_my_topic_reply, notify_on_followed_topic_reply) VALUES (?, 1, 1)',
                (user_id,)
            )

            user = User.get(user_id)
            login_user(user)
            flash('Compte créé avec succès. Bienvenue !', 'success')
            return redirect(url_for('index'))

        return render_template('auth_register.html')

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            verify_csrf()
            email = (request.form.get('email') or '').strip().lower()
            password = request.form.get('password') or ''

            row = query_one('SELECT * FROM users WHERE email = ?', (email,))
            if not row or not check_password_hash(row['password_hash'], password):
                flash('Email ou mot de passe incorrect.', 'danger')
                return redirect(url_for('login'))

            login_user(User(row))
            flash('Connexion réussie.', 'success')
            return redirect(url_for('index'))

        return render_template('auth_login.html')

    @app.route('/logout', methods=['POST'])
    @login_required
    def logout():
        verify_csrf()
        logout_user()
        flash('Vous êtes déconnecté.', 'info')
        return redirect(url_for('index'))

    @app.route('/topic/new', methods=['GET', 'POST'])
    @login_required
    def new_topic():
        if request.method == 'POST':
            verify_csrf()
            title = (request.form.get('title') or '').strip()
            body = (request.form.get('body') or '').strip()
            category = (request.form.get('category') or '').strip()
            tags = (request.form.get('tags') or '').strip()

            if len(title) < 5:
                flash('Titre trop court (5 caractères minimum).', 'danger')
                return redirect(url_for('new_topic'))
            if len(body) < 10:
                flash('Contenu trop court (10 caractères minimum).', 'danger')
                return redirect(url_for('new_topic'))

            topic_id = execute(
                'INSERT INTO topics (user_id, title, body, category, tags, created_at) VALUES (?, ?, ?, ?, ?, ?)',
                (current_user.id, title, body, category, tags, now_iso())
            )
            # Auto-follow du créateur
            try:
                execute('INSERT INTO follows (user_id, topic_id, created_at) VALUES (?, ?, ?)',
                        (current_user.id, topic_id, now_iso()))
            except Exception:
                pass

            flash('Sujet publié.', 'success')
            return redirect(url_for('topic', topic_id=topic_id))

        return render_template('topic_new.html')

    @app.route('/topic/<int:topic_id>')
    def topic(topic_id: int):
        topic = query_one(
            'SELECT t.*, u.display_name, u.id as author_id '
            'FROM topics t JOIN users u ON u.id = t.user_id WHERE t.id = ?',
            (topic_id,)
        )
        if not topic:
            abort(404)

        # incrémente vues
        execute('UPDATE topics SET views = views + 1 WHERE id = ?', (topic_id,))

        replies = query_all(
            'SELECT r.*, u.display_name '
            'FROM replies r JOIN users u ON u.id = r.user_id '
            'WHERE r.topic_id = ? ORDER BY r.created_at ASC',
            (topic_id,)
        )

        # commentaires groupés par reply
        reply_ids = [r['id'] for r in replies]
        comments_by_reply = {rid: [] for rid in reply_ids}
        if reply_ids:
            placeholders = ','.join(['?'] * len(reply_ids))
            comments = query_all(
                f"SELECT c.*, u.display_name FROM comments c JOIN users u ON u.id = c.user_id WHERE c.reply_id IN ({placeholders}) ORDER BY c.created_at ASC",
                tuple(reply_ids)
            )
            for c in comments:
                comments_by_reply[c['reply_id']].append(c)

        is_following = False
        if current_user.is_authenticated:
            f = query_one('SELECT id FROM follows WHERE user_id = ? AND topic_id = ?', (current_user.id, topic_id))
            is_following = bool(f)

        return render_template(
            'topic_view.html',
            topic=topic,
            replies=replies,
            comments_by_reply=comments_by_reply,
            is_following=is_following
        )

    @app.route('/topic/<int:topic_id>/reply', methods=['POST'])
    @login_required
    def add_reply(topic_id: int):
        verify_csrf()
        body = (request.form.get('body') or '').strip()
        if len(body) < 5:
            flash('Réponse trop courte.', 'danger')
            return redirect(url_for('topic', topic_id=topic_id))

        topic = query_one('SELECT id, is_closed FROM topics WHERE id = ?', (topic_id,))
        if not topic:
            abort(404)
        if int(topic['is_closed']) == 1:
            flash('Ce sujet est fermé.', 'warning')
            return redirect(url_for('topic', topic_id=topic_id))

        reply_id = execute(
            'INSERT INTO replies (topic_id, user_id, body, created_at) VALUES (?, ?, ?, ?)',
            (topic_id, current_user.id, body, now_iso())
        )

        # Auto-follow du répondant
        try:
            execute('INSERT INTO follows (user_id, topic_id, created_at) VALUES (?, ?, ?)',
                    (current_user.id, topic_id, now_iso()))
        except Exception:
            pass

        # emails
        send_new_reply_notifications(topic_id, reply_id)

        flash('Réponse ajoutée.', 'success')
        return redirect(url_for('topic', topic_id=topic_id) + f"#reply-{reply_id}")

    @app.route('/reply/<int:reply_id>/comment', methods=['POST'])
    @login_required
    def add_comment(reply_id: int):
        verify_csrf()
        body = (request.form.get('body') or '').strip()
        if len(body) < 2:
            flash('Commentaire trop court.', 'danger')
            return redirect(request.referrer or url_for('index'))

        reply = query_one('SELECT topic_id FROM replies WHERE id = ?', (reply_id,))
        if not reply:
            abort(404)

        execute(
            'INSERT INTO comments (reply_id, user_id, body, created_at) VALUES (?, ?, ?, ?)',
            (reply_id, current_user.id, body, now_iso())
        )

        flash('Commentaire ajouté.', 'success')
        return redirect(url_for('topic', topic_id=reply['topic_id']) + f"#reply-{reply_id}")

    @app.route('/topic/<int:topic_id>/follow', methods=['POST'])
    @login_required
    def follow_topic(topic_id: int):
        verify_csrf()
        try:
            execute('INSERT INTO follows (user_id, topic_id, created_at) VALUES (?, ?, ?)',
                    (current_user.id, topic_id, now_iso()))
        except Exception:
            pass
        flash('Vous suivez maintenant ce sujet.', 'success')
        return redirect(url_for('topic', topic_id=topic_id))

    @app.route('/topic/<int:topic_id>/unfollow', methods=['POST'])
    @login_required
    def unfollow_topic(topic_id: int):
        verify_csrf()
        execute('DELETE FROM follows WHERE user_id = ? AND topic_id = ?', (current_user.id, topic_id))
        flash('Vous ne suivez plus ce sujet.', 'info')
        return redirect(url_for('topic', topic_id=topic_id))

    @app.route('/profile/<int:user_id>')
    def profile(user_id: int):
        user = query_one('SELECT id, email, display_name, created_at FROM users WHERE id = ?', (user_id,))
        if not user:
            abort(404)
        topics = query_all(
            'SELECT id, title, created_at FROM topics WHERE user_id = ? ORDER BY created_at DESC LIMIT 30',
            (user_id,)
        )
        replies = query_all(
            'SELECT r.id, r.created_at, t.id as topic_id, t.title as topic_title '
            'FROM replies r JOIN topics t ON t.id = r.topic_id '
            'WHERE r.user_id = ? ORDER BY r.created_at DESC LIMIT 30',
            (user_id,)
        )
        return render_template('profile.html', profile_user=user, topics=topics, replies=replies)

    @app.route('/settings', methods=['GET', 'POST'])
    @login_required
    def settings():
        settings = get_user_settings(current_user.id)
        if request.method == 'POST':
            verify_csrf()
            notify_my = 1 if request.form.get('notify_on_my_topic_reply') == 'on' else 0
            notify_followed = 1 if request.form.get('notify_on_followed_topic_reply') == 'on' else 0
            execute(
                'UPDATE user_settings SET notify_on_my_topic_reply = ?, notify_on_followed_topic_reply = ? WHERE user_id = ?',
                (notify_my, notify_followed, current_user.id)
            )
            flash('Réglages enregistrés.', 'success')
            return redirect(url_for('settings'))

        return render_template('settings.html', settings=settings)

    # ----------------------------
    # Pages d'erreur
    # ----------------------------
    @app.errorhandler(400)
    def bad_request(e):
        return render_template('errors/400.html', error=e), 400

    @app.errorhandler(404)
    def not_found(e):
        return render_template('errors/404.html', error=e), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template('errors/500.html', error=e), 500

    return app


app = create_app()


if __name__ == '__main__':
    # Assure que l'instance folder existe
    os.makedirs(app.instance_path, exist_ok=True)

    # Init DB auto si fichier absent (pratique en dev)
    db_file = os.path.join(app.instance_path, app.config['DATABASE'])
    if not os.path.exists(db_file):
        with app.app_context():
            init_db()
            print('DB créée automatiquement:', db_file)

    app.run(debug=True)
