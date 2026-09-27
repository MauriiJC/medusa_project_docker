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

        from django.contrib.auth.models import User

        self.stdout.write(f'Backend:  {settings.EMAIL_BACKEND}')
        self.stdout.write(f'From:     {settings.DEFAULT_FROM_EMAIL}')

        cuentas = User.objects.filter(email__iexact=dest)
        if not cuentas:
            self.stdout.write(self.style.WARNING('No hay ninguna cuenta con ese correo.'))
        for u in cuentas:
            self.stdout.write(
                f'Cuenta: {u.username} | activa: {u.is_active} | '
                f'tiene contraseña: {u.has_usable_password()} (sin contraseña no llega el correo de recuperación)'
            )
        self.stdout.write(f'Enviando a {dest} ...')

        try:
            enviados = send_mail(
                subject='Prueba de email — Medusa',
                message='Si recibes este correo, el envío con Brevo está funcionando correctamente.',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[dest],
                fail_silently=False,
            )
            if enviados:
                self.stdout.write(self.style.SUCCESS('Brevo aceptó el correo.'))
            else:
                self.stdout.write(self.style.ERROR('No se envió: revisa BREVO_API_KEY.'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'ERROR al enviar: {e}'))
