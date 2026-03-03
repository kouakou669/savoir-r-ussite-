import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def _bool_env(name: str, default: str = '0') -> bool:
    return os.getenv(name, default).strip().lower() in ('1', 'true', 'yes', 'y', 'on')


def is_smtp_configured() -> bool:
    host = os.getenv('SMTP_HOST', '').strip()
    from_email = os.getenv('SMTP_FROM_EMAIL', '').strip()
    return bool(host and from_email)


def send_email(to_email: str, subject: str, html_body: str, text_body: str = '') -> None:
    """Envoie un email via SMTP.

    Si SMTP n'est pas configuré, on affiche le message en console (mode dev).
    """
    to_email = (to_email or '').strip()
    if not to_email:
        return

    smtp_host = os.getenv('SMTP_HOST', '').strip()
    smtp_port = int(os.getenv('SMTP_PORT', '587').strip() or '587')
    smtp_user = os.getenv('SMTP_USER', '').strip()
    smtp_pass = os.getenv('SMTP_PASS', '').strip()
    use_tls = _bool_env('SMTP_USE_TLS', '1')

    from_name = os.getenv('SMTP_FROM_NAME', 'Savoir & Réussite').strip()
    from_email = os.getenv('SMTP_FROM_EMAIL', '').strip()

    if not smtp_host or not from_email:
        # Mode dev (pas d'envoi réel)
        print('\n[EMAIL DEV MODE] SMTP non configuré. Voici le contenu qui aurait été envoyé:')
        print('To:', to_email)
        print('Subject:', subject)
        print('Text:', text_body)
        print('HTML:', html_body)
        print('[FIN EMAIL]\n')
        return

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = f"{from_name} <{from_email}>" if from_name else from_email
    msg['To'] = to_email

    if text_body:
        msg.attach(MIMEText(text_body, 'plain', 'utf-8'))
    msg.attach(MIMEText(html_body, 'html', 'utf-8'))

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
            server.ehlo()
            if use_tls:
                server.starttls()
                server.ehlo()
            if smtp_user and smtp_pass:
                server.login(smtp_user, smtp_pass)
            server.sendmail(from_email, [to_email], msg.as_string())
    except Exception as ex:
        # Ne pas planter l'app si l'email échoue.
        print('[EMAIL ERROR]', ex)
