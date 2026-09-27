import logging
import os

import requests
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)


class BrevoAPIBackend(BaseEmailBackend):
    """Backend de email que usa la API REST de Brevo en vez de SMTP."""

    def send_messages(self, email_messages):
        api_key = os.environ.get('BREVO_API_KEY', '')
        if not api_key:
            logger.error('BREVO_API_KEY no está configurada; no se envió el correo.')
            return 0

        sent = 0
        for msg in email_messages:
            try:
                payload = {
                    'sender': {
                        'name': 'Medusa · SOS Mujer Berraca',
                        'email': os.environ.get('BREVO_SENDER_EMAIL', 'medusaingesis@gmail.com'),
                    },
                    'to': [{'email': addr} for addr in msg.to],
                    'subject': msg.subject,
                    'textContent': msg.body,
                }
                resp = requests.post(
                    'https://api.brevo.com/v3/smtp/email',
                    headers={'api-key': api_key, 'Content-Type': 'application/json'},
                    json=payload,
                    timeout=15,
                )
                if resp.status_code in (200, 201):
                    sent += 1
                else:
                    raise RuntimeError(f'Brevo respondió {resp.status_code}: {resp.text[:300]}')
            except Exception:
                logger.exception('No se pudo enviar el correo "%s" con Brevo', msg.subject)
                if not self.fail_silently:
                    raise
        return sent
