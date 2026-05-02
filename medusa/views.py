from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.shortcuts import redirect, render

from .forms import LoginForm, OTPForm, RegistrationForm
from .models import OTPCode


def landing(request):
    return render(request, 'medusa/landing.htm')


def registro_view(request):
    if request.user.is_authenticated:
        return redirect('chat')

    form = RegistrationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        cd = form.cleaned_data
        base_username = cd['email'].split('@')[0]
        username = base_username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f'{base_username}{counter}'
            counter += 1

        user = User.objects.create_user(
            username=username,
            email=cd['email'],
            password=cd['password'],
            first_name=cd.get('nombre', ''),
        )

        otp = OTPCode.generate_for(user)
        _send_otp_email(user, otp.code)

        request.session['pending_user_id'] = user.pk
        return redirect('verify_otp')

    return render(request, 'medusa/registro.htm', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('chat')

    form = LoginForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        cd = form.cleaned_data
        try:
            db_user = User.objects.get(email=cd['email'].lower())
        except User.DoesNotExist:
            form.add_error('email', 'No existe una cuenta con este correo.')
            return render(request, 'medusa/login.htm', {'form': form})

        user = authenticate(request, username=db_user.username, password=cd['password'])
        if user is None:
            form.add_error('password', 'Contraseña incorrecta.')
            return render(request, 'medusa/login.htm', {'form': form})

        otp = OTPCode.generate_for(user)
        _send_otp_email(user, otp.code)

        request.session['pending_user_id'] = user.pk
        return redirect('verify_otp')

    return render(request, 'medusa/login.htm', {'form': form})


def verify_otp_view(request):
    user_id = request.session.get('pending_user_id')
    if not user_id:
        return redirect('login')

    form = OTPForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        code = form.cleaned_data['code'].strip()
        try:
            user = User.objects.get(pk=user_id)
            otp = OTPCode.objects.filter(user=user, code=code, is_used=False).latest('created_at')
            if otp.is_valid():
                otp.is_used = True
                otp.save()
                del request.session['pending_user_id']
                login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                return redirect('chat')
            else:
                form.add_error('code', 'El código expiró. Solicita uno nuevo.')
        except (User.DoesNotExist, OTPCode.DoesNotExist):
            form.add_error('code', 'Código incorrecto.')

    return render(request, 'medusa/verify_otp.htm', {'form': form})


def resend_otp_view(request):
    user_id = request.session.get('pending_user_id')
    if not user_id:
        return redirect('login')
    try:
        user = User.objects.get(pk=user_id)
        otp = OTPCode.generate_for(user)
        _send_otp_email(user, otp.code)
        messages.success(request, 'Se envió un nuevo código a tu correo.')
    except User.DoesNotExist:
        pass
    return redirect('verify_otp')


def google_login_start(request):
    from allauth.socialaccount.models import SocialApp
    from allauth.socialaccount.providers.google.views import oauth2_login

    client_id = settings.SOCIALACCOUNT_PROVIDERS.get('google', {}).get('APP', {}).get('client_id', '')
    has_db_app = SocialApp.objects.filter(provider='google').exists()

    if not client_id and not has_db_app:
        messages.info(request, 'El inicio de sesión con Google aún no está habilitado. Por favor usa tu correo y contraseña.')
        return redirect('login')

    return oauth2_login(request)


def logout_view(request):
    logout(request)
    return redirect('landing')


@login_required
def chat(request):
    return render(request, 'medusa/chat.htm', {'user': request.user})


def _send_otp_email(user, code):
    nombre = user.first_name or 'usuaria'
    subject = 'Tu código de verificación — Medusa'
    message = (
        f'Hola {nombre},\n\n'
        f'Tu código de verificación es: {code}\n\n'
        f'Este código es válido por 10 minutos.\n'
        f'Si no fuiste tú quien inició sesión, ignora este mensaje.\n\n'
        f'— Medusa · SOS Mujer Berraca'
    )
    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=True)
