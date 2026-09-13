import os
import requests as http_requests

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt

from .forms import LoginForm, OTPForm, RegistrationForm
from .models import OTPCode


# ── Directorio de prompts ──────────────────────────────────────────────────────
PROMPTS_DIR = os.path.join(os.path.dirname(__file__), 'prompts')


def _cargar_prompt(nombre_archivo):
    """Carga un prompt desde el archivo .txt correspondiente."""
    ruta = os.path.join(PROMPTS_DIR, nombre_archivo)
    with open(ruta, encoding='utf-8') as f:
        return f.read()


# ── Llamada base a Ollama ──────────────────────────────────────────────────────
OLLAMA_URL = os.environ.get('OLLAMA_URL', 'http://ollama:11434/api/generate')


def _llamar_ollama(prompt, num_predict=180, num_ctx=2048):
    """Envía un prompt a Ollama y devuelve el texto de la respuesta."""
    respuesta = http_requests.post(
        OLLAMA_URL,
        json={
            'model': 'mistral',
            'prompt': prompt,
            'stream': False,
            'options': {
                'num_predict': num_predict,
                'num_ctx': num_ctx,
                'num_gpu': 99,
                'temperature': 0.7,
                'top_k': 40,
                'top_p': 0.9,
            },
        },
        timeout=120,
    )
    return respuesta.json().get('response', '').strip()


# ── Clasificador ───────────────────────────────────────────────────────────────
def _clasificar_mensaje(mensaje):
    """
    Llama al agente clasificador y devuelve 'CRISIS', 'LEGAL' o 'EMOCIONAL'.
    Usa contexto mínimo para ser rápido — solo necesita responder una palabra.
    """
    prompt = _cargar_prompt('clasificador.txt').format(mensaje=mensaje)
    resultado = _llamar_ollama(prompt, num_predict=5, num_ctx=512)
    # Normalizar — tomar solo la primera palabra en mayúsculas
    palabra = resultado.strip().upper().split()[0] if resultado.strip() else ''
    if palabra in ('CRISIS', 'LEGAL', 'EMOCIONAL'):
        return palabra
    return 'EMOCIONAL'  # fallback seguro


# ── Mapa de agentes ────────────────────────────────────────────────────────────
AGENTES = {
    'CRISIS':    'agente_crisis.txt',
    'LEGAL':     'agente_legal.txt',
    'EMOCIONAL': 'agente_emocional.txt',
}


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


@csrf_exempt
@login_required
def chat_api(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)

    mensaje = request.POST.get('mensaje', '').strip()
    if not mensaje:
        return JsonResponse({'error': 'Mensaje vacío'}, status=400)

    # ── Filtro rápido para saludos simples ────────────────────────────────────
    saludos_simples = {'hola', 'buenas', 'ola', 'hi', 'hello', 'buenos dias', 'buenas tardes', 'buenas noches'}
    if mensaje.lower() in saludos_simples:
        return JsonResponse({
            'respuesta': '¡Hola! Qué gusto que estés por aquí. ¿Cómo te sientes hoy o de qué te gustaría hablar?',
            'agente': 'EMOCIONAL'
        })

    # ── Intento 1: orquestar a través de n8n ──────────────────────────────────
    try:
        res = http_requests.post(
            'http://localhost:5678/webhook/medusa',
            json={'mensaje': mensaje},
            timeout=120,
        )
        if res.status_code == 200:
            data = res.json()
            return JsonResponse({
                'respuesta': data.get('respuesta', 'Sin respuesta del agente.'),
                'agente':    data.get('agente', 'EMOCIONAL'),
            })
    except Exception:
        pass  # n8n no disponible → fallback directo a Ollama

    # ── Fallback: llamada directa a Ollama (si n8n no está corriendo) ─────────
    try:
        tipo   = _clasificar_mensaje(mensaje)
        prompt = _cargar_prompt(AGENTES[tipo]).format(mensaje=mensaje)
        texto  = _llamar_ollama(prompt)
        return JsonResponse({'respuesta': texto, 'agente': tipo})
    except Exception as e:
        return JsonResponse({'respuesta': f'Error al conectar con el modelo: {str(e)}'})

@csrf_exempt
def clasificar_api(request):
    """
    Endpoint interno llamado por n8n para clasificar el mensaje.
    Recibe JSON: { "mensaje": "..." }
    Devuelve JSON: { "tipo": "CRISIS|LEGAL|EMOCIONAL" }
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)

    import json as _json
    try:
        body = _json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'JSON inválido'}, status=400)

    mensaje = body.get('mensaje', '').strip()
    if not mensaje:
        return JsonResponse({'error': 'Mensaje vacío'}, status=400)

    try:
        tipo = _clasificar_mensaje(mensaje)
        return JsonResponse({'tipo': tipo})
    except Exception as e:
        return JsonResponse({'tipo': 'EMOCIONAL', 'error': str(e)})


@csrf_exempt
def agente_api(request):
    """
    Endpoint interno llamado por n8n.
    Recibe JSON: { "mensaje": "...", "tipo": "CRISIS|LEGAL|EMOCIONAL" }
    Lee el prompt .txt del proyecto Django y llama a Ollama.
    No requiere login porque solo es accesible desde localhost (n8n).
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)

    import json as _json
    try:
        body = _json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'JSON inválido'}, status=400)

    mensaje = body.get('mensaje', '').strip()
    tipo    = body.get('tipo', 'EMOCIONAL').strip().upper()

    if not mensaje:
        return JsonResponse({'error': 'Mensaje vacío'}, status=400)

    if tipo not in AGENTES:
        tipo = 'EMOCIONAL'

    try:
        prompt = _cargar_prompt(AGENTES[tipo]).format(mensaje=mensaje)
        texto  = _llamar_ollama(prompt)
        return JsonResponse({'respuesta': texto, 'agente': tipo})
    except Exception as e:
        return JsonResponse(
            {'respuesta': f'Error al conectar con el modelo: {str(e)}'},
            status=500,
        )


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
