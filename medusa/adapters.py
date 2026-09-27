from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.providers.base import AuthError
from django.contrib import messages
from django.shortcuts import redirect


class MedusaSocialAccountAdapter(DefaultSocialAccountAdapter):
    def on_authentication_error(self, request, provider, error=None, exception=None, extra_context=None):
        if error == AuthError.CANCELLED:
            messages.info(request, 'Cancelaste el inicio de sesión con Google.')
        else:
            messages.error(request, 'No se pudo iniciar sesión con Google. Intenta de nuevo o usa tu correo.')
        raise ImmediateHttpResponse(redirect('login'))
