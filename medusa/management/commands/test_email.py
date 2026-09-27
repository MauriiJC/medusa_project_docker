import os
from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.conf import settings


class Command(BaseCommand):
    help = 'Envía un correo de prueba para verificar la configuración SMTP'

    def add_arguments(self, parser):
        parser.add_argument('destinatario', help='Correo donde enviar la prueba')

    def handle(self, *args, **options):
        dest = options['destinatario']

        self.stdout.write(f'Backend:  {settings.EMAIL_BACKEND}')
        self.stdout.write(f'Host:     {getattr(settings, "EMAIL_HOST", "N/A")}')
        self.stdout.write(f'Puerto:   {getattr(settings, "EMAIL_PORT", "N/A")}')
        self.stdout.write(f'Usuario:  {getattr(settings, "EMAIL_HOST_USER", "N/A")}')
        self.stdout.write(f'From:     {settings.DEFAULT_FROM_EMAIL}')
        self.stdout.write(f'Enviando a {dest} ...')

        try:
            send_mail(
                subject='Prueba de email — Medusa',
                message='Si recibes este correo, el SMTP de Brevo está funcionando correctamente.',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[dest],
                fail_silently=False,
            )
            self.stdout.write(self.style.SUCCESS('Correo enviado exitosamente.'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'ERROR al enviar: {e}'))
