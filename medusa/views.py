import logging
import os
import requests as http_requests

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.views import PasswordResetView as _PasswordResetView
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm

from .forms import LoginForm, OTPForm, OTPToggleForm, ProfileForm, RegistrationForm
from .models import Conversation, Message, OTPCode, UserProfile


logger = logging.getLogger(__name__)


# ── Directorio de prompts ──────────────────────────────────────────────────────
PROMPTS_DIR = os.path.join(os.path.dirname(__file__), 'prompts')


def _cargar_prompt(nombre_archivo):
    ruta = os.path.join(PROMPTS_DIR, nombre_archivo)
    with open(ruta, encoding='utf-8') as f:
        return f.read()


# ── Configuración LLM ─────────────────────────────────────────────────────────
GROQ_API_KEY    = os.environ.get('GROQ_API_KEY', '')
GROQ_MODEL      = os.environ.get('GROQ_MODEL', 'openai/gpt-oss-20b')
OLLAMA_URL      = os.environ.get('OLLAMA_URL', 'http://ollama:11434/api/generate')
N8N_WEBHOOK_URL = os.environ.get('N8N_WEBHOOK_URL', '')
N8N_TOKEN       = os.environ.get('N8N_TOKEN', '')


# ── Llamadas al modelo ────────────────────────────────────────────────────────
def _llamar_groq(prompt):
    """Llamada simple de un solo turno (usada para clasificación)."""
    respuesta = http_requests.post(
        'https://api.groq.com/openai/v1/chat/completions',
        headers={'Authorization': f'Bearer {GROQ_API_KEY.strip()}', 'Content-Type': 'application/json'},
        json={
            'model': GROQ_MODEL,
            'messages': [{'role': 'user', 'content': prompt}],
            'temperature': 0.7,
            'max_tokens': 800,
        },
        timeout=30,
    )
    respuesta.raise_for_status()
    msg = respuesta.json()['choices'][0]['message']
    return (msg.get('content') or msg.get('reasoning') or '').strip()


def _llamar_groq_con_contexto(system_instructions, historial, nuevo_mensaje):
    """Llamada multi-turno con historial de conversación."""
    msgs = [{'role': 'system', 'content': system_instructions}]
    for m in historial:
        role = 'user' if m.role == 'user' else 'assistant'
        msgs.append({'role': role, 'content': m.content})
    msgs.append({'role': 'user', 'content': nuevo_mensaje})
    respuesta = http_requests.post(
        'https://api.groq.com/openai/v1/chat/completions',
        headers={'Authorization': f'Bearer {GROQ_API_KEY.strip()}', 'Content-Type': 'application/json'},
        json={
            'model': GROQ_MODEL,
            'messages': msgs,
            'temperature': 0.7,
            'max_tokens': 800,
        },
        timeout=30,
    )
    respuesta.raise_for_status()
    msg = respuesta.json()['choices'][0]['message']
    return (msg.get('content') or msg.get('reasoning') or '').strip()


def _llamar_ollama_directo(prompt, num_predict=400, num_ctx=2048):
    """Fallback a Ollama cuando no hay GROQ_API_KEY."""
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


def _llamar_ollama(prompt, num_predict=180, num_ctx=512):
    """Enruta a Groq si hay API key, sino a Ollama (usado para clasificación)."""
    if GROQ_API_KEY:
        return _llamar_groq(prompt)
    return _llamar_ollama_directo(prompt, num_predict, num_ctx)


def _llamar_con_contexto(system_instructions, historial, nuevo_mensaje):
    """Enruta a Groq con historial si hay API key, sino fallback a Ollama sin historial."""
    if GROQ_API_KEY:
        return _llamar_groq_con_contexto(system_instructions, historial, nuevo_mensaje)
    prompt_fallback = f"{system_instructions}\n\nLa usuaria dice: {nuevo_mensaje}"
    return _llamar_ollama_directo(prompt_fallback)


# ── Clasificador ───────────────────────────────────────────────────────────────
def _clasificar_mensaje(mensaje):
    prompt = _cargar_prompt('clasificador.txt').format(mensaje=mensaje)
    resultado = _llamar_ollama(prompt, num_predict=5, num_ctx=512)
    palabra = resultado.strip().upper().split()[0] if resultado.strip() else ''
    if palabra in ('CRISIS', 'LEGAL', 'EMOCIONAL', 'OTRO'):
        return palabra
    return 'EMOCIONAL'


RESPUESTA_OTRO = (
    'Estoy aquí para acompañarte en situaciones relacionadas con tu bienestar y seguridad. '
    'Si hay algo que estés viviendo y quieras contarme, puedes hacerlo con confianza. '
    '¿Hay algo en lo que pueda ayudarte?'
)

AGENTES = {
    'CRISIS':    'agente_crisis.txt',
    'LEGAL':     'agente_legal.txt',
    'EMOCIONAL': 'agente_emocional.txt',
}


# ── Vistas públicas ───────────────────────────────────────────────────────────
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
        # Mensaje genérico para no revelar si el correo existe
        user = None
        for db_user in User.objects.filter(email__iexact=cd['email']).order_by('date_joined'):
            if not db_user.has_usable_password():
                continue
            user = authenticate(request, username=db_user.username, password=cd['password'])
            if user is not None:
                break

        if user is None:
            messages.error(request, 'Correo o contraseña incorrectos.')
            return render(request, 'medusa/login.htm', {'form': form})

        if not UserProfile.for_user(user).otp_enabled:
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            return redirect('chat')

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


# ── Perfil ────────────────────────────────────────────────────────────────────
@login_required
def perfil_view(request):
    user = request.user
    profile = UserProfile.for_user(user)
    PwdForm = PasswordChangeForm if user.has_usable_password() else SetPasswordForm
    accion = request.POST.get('accion') if request.method == 'POST' else None

    datos_form = ProfileForm(
        request.POST if accion == 'datos' else None,
        initial={'nombre': user.first_name},
    )
    password_form = PwdForm(user, request.POST if accion == 'password' else None)
    otp_form = OTPToggleForm(
        request.POST if accion == 'otp' else None,
        user=user,
        activar=not profile.otp_enabled,
    )

    if accion == 'datos' and datos_form.is_valid():
        user.first_name = datos_form.cleaned_data['nombre']
        user.save(update_fields=['first_name'])
        messages.success(request, 'Tus datos se actualizaron correctamente.')
        return redirect('perfil')

    if accion == 'password' and password_form.is_valid():
        password_form.save()
        update_session_auth_hash(request, password_form.user)
        messages.success(request, 'Tu contraseña se cambió correctamente.')
        return redirect('perfil')

    if accion == 'otp' and otp_form.is_valid():
        profile.otp_enabled = not profile.otp_enabled
        profile.save(update_fields=['otp_enabled'])
        estado = 'activada' if profile.otp_enabled else 'desactivada'
        messages.success(request, f'La verificación en dos pasos quedó {estado}.')
        return redirect('perfil')

    return render(request, 'medusa/perfil.htm', {
        'datos_form': datos_form,
        'password_form': password_form,
        'otp_form': otp_form,
        'otp_enabled': profile.otp_enabled,
        'tiene_password': user.has_usable_password(),
    })


# ── Chat ──────────────────────────────────────────────────────────────────────
@login_required
def chat(request):
    # El chat no muestra avisos; se descartan para que no reaparezcan en otra página
    list(messages.get_messages(request))
    return render(request, 'medusa/chat.htm', {'user': request.user})


@csrf_exempt
@login_required
def chat_api(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)

    mensaje = request.POST.get('mensaje', '').strip()
    conv_id = request.POST.get('conv_id', '').strip()
    if not mensaje:
        return JsonResponse({'error': 'Mensaje vacío'}, status=400)

    # Obtener o crear conversación
    conv = None
    if conv_id:
        try:
            conv = Conversation.objects.get(pk=conv_id, user=request.user)
        except Conversation.DoesNotExist:
            pass
    if conv is None:
        conv = Conversation.objects.create(user=request.user)

    # Capturar historial ANTES de guardar el mensaje actual
    historial = list(
        conv.messages.order_by('-created_at')[:10]
    )[::-1]

    # Guardar mensaje del usuario
    Message.objects.create(conversation=conv, role='user', content=mensaje)

    # ── Filtro rápido para saludos simples ────────────────────────────────────
    saludos_simples = {'hola', 'buenas', 'ola', 'hi', 'hello', 'buenos dias', 'buenas tardes', 'buenas noches'}
    if mensaje.lower() in saludos_simples:
        respuesta = '¡Hola! Qué gusto que estés por aquí. ¿Cómo te sientes hoy o de qué te gustaría hablar?'
        agente = 'EMOCIONAL'
        Message.objects.create(conversation=conv, role='bot', content=respuesta, agente=agente)
        _actualizar_titulo(conv, mensaje)
        return JsonResponse({'respuesta': respuesta, 'agente': agente, 'conv_id': conv.pk})

    # ── Intento 1: orquestar a través de n8n (si está configurado) ─────────────
    if N8N_WEBHOOK_URL:
        try:
            res = http_requests.post(
                N8N_WEBHOOK_URL,
                json={'mensaje': mensaje},
                timeout=10,
            )
            if res.status_code == 200:
                data = res.json()
                respuesta = data.get('respuesta', 'Sin respuesta del agente.')
                agente = data.get('agente', 'EMOCIONAL')
                Message.objects.create(conversation=conv, role='bot', content=respuesta, agente=agente)
                _actualizar_titulo(conv, mensaje)
                return JsonResponse({'respuesta': respuesta, 'agente': agente, 'conv_id': conv.pk})
        except Exception:
            pass

    # ── Fallback directo con historial de conversación ────────────────────────
    try:
        tipo = _clasificar_mensaje(mensaje)
        if tipo == 'OTRO':
            Message.objects.create(conversation=conv, role='bot', content=RESPUESTA_OTRO, agente='EMOCIONAL')
            _actualizar_titulo(conv, mensaje)
            return JsonResponse({'respuesta': RESPUESTA_OTRO, 'agente': 'EMOCIONAL', 'conv_id': conv.pk})
        prompt_template = _cargar_prompt(AGENTES[tipo])
        system_instructions = prompt_template.split('{mensaje}')[0].strip()
        respuesta = _llamar_con_contexto(system_instructions, historial, mensaje)
        Message.objects.create(conversation=conv, role='bot', content=respuesta, agente=tipo)
        _actualizar_titulo(conv, mensaje)
        return JsonResponse({'respuesta': respuesta, 'agente': tipo, 'conv_id': conv.pk})
    except Exception:
        mensaje_error = (
            'En este momento no puedo conectarme. '
            'Si estás en peligro, llama al 155 o al 123 — son gratuitos y están las 24 horas. '
            'Inténtalo de nuevo en un momento.'
        )
        Message.objects.create(conversation=conv, role='bot', content=mensaje_error, agente='')
        _actualizar_titulo(conv, mensaje)
        return JsonResponse({'respuesta': mensaje_error, 'conv_id': conv.pk})


def _actualizar_titulo(conv, primer_mensaje):
    if conv.title == 'Nueva conversación':
        conv.title = primer_mensaje[:80]
        conv.save(update_fields=['title', 'updated_at'])


# ── APIs de conversaciones ────────────────────────────────────────────────────
@login_required
def conversaciones_api(request):
    convs = (
        Conversation.objects
        .filter(user=request.user)
        .values('id', 'title', 'updated_at')[:60]
    )
    return JsonResponse({'conversaciones': list(convs)})


@login_required
def conversacion_mensajes_api(request, conv_id):
    try:
        conv = Conversation.objects.get(pk=conv_id, user=request.user)
    except Conversation.DoesNotExist:
        return JsonResponse({'error': 'No encontrada'}, status=404)
    mensajes = list(conv.messages.values('role', 'content', 'agente'))
    return JsonResponse({'mensajes': mensajes, 'titulo': conv.title})


@login_required
def eliminar_conversacion_api(request, conv_id):
    if request.method != 'DELETE':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    try:
        conv = Conversation.objects.get(pk=conv_id, user=request.user)
        conv.delete()
        return JsonResponse({'ok': True})
    except Conversation.DoesNotExist:
        return JsonResponse({'error': 'No encontrada'}, status=404)


@login_required
def eliminar_historial_api(request):
    if request.method != 'DELETE':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    Conversation.objects.filter(user=request.user).delete()
    return JsonResponse({'ok': True})


# ── Endpoints internos para n8n ───────────────────────────────────────────────
def _verificar_token_n8n(request):
    """Retorna True si el token es válido (o si no está configurado)."""
    if not N8N_TOKEN:
        return True
    return request.headers.get('X-N8N-Token', '') == N8N_TOKEN


@csrf_exempt
def clasificar_api(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    if not _verificar_token_n8n(request):
        return JsonResponse({'error': 'No autorizado'}, status=401)

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
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    if not _verificar_token_n8n(request):
        return JsonResponse({'error': 'No autorizado'}, status=401)

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
        return JsonResponse({'respuesta': f'Error al conectar con el modelo: {str(e)}'}, status=500)


# ── Email OTP ─────────────────────────────────────────────────────────────────
def _send_otp_email(user, code):
    nombre = user.first_name or 'usuaria'
    brevo_key = os.environ.get('BREVO_API_KEY', '')
    if not brevo_key:
        return False
    try:
        sender_email = os.environ.get('BREVO_SENDER_EMAIL', 'medusaingesis@gmail.com')
        resp = http_requests.post(
            'https://api.brevo.com/v3/smtp/email',
            headers={'api-key': brevo_key, 'Content-Type': 'application/json'},
            json={
                'sender': {'name': 'Medusa · SOS Mujer Berraca', 'email': sender_email},
                'to': [{'email': user.email, 'name': nombre}],
                'subject': 'Tu código de verificación — Medusa',
                'textContent': (
                    f'Hola {nombre},\n\n'
                    f'Tu código de verificación es: {code}\n\n'
                    f'Este código es válido por 10 minutos.\n'
                    f'Si no fuiste tú quien inició sesión, ignora este mensaje.\n\n'
                    f'— Medusa · SOS Mujer Berraca'
                ),
            },
            timeout=15,
        )
        if resp.status_code not in (200, 201):
            logger.error('Brevo rechazó el código OTP: %s %s', resp.status_code, resp.text[:300])
            return False
        return True
    except Exception:
        logger.exception('No se pudo enviar el código OTP')
        return False


# ── Recuperación de contraseña ────────────────────────────────────────────────
class MedusaPasswordResetView(_PasswordResetView):
    """Igual que PasswordResetView pero fuerza el dominio real del request.

    Django usa el Sites framework por defecto, cuyo dominio inicial es
    'example.com'. Al pasar domain_override usamos el host real del servidor.
    """
    template_name = 'medusa/password_reset.htm'
    email_template_name = 'medusa/password_reset_email.txt'
    subject_template_name = 'medusa/password_reset_subject.txt'
    success_url = '/password-reset/enviado/'

    def form_valid(self, form):
        try:
            form.save(
                domain_override=self.request.get_host(),
                use_https=self.request.is_secure(),
                token_generator=self.token_generator,
                from_email=self.from_email,
                request=self.request,
                extra_email_context=self.extra_email_context,
            )
        except Exception:
            # No se revela a quien pide el enlace; el detalle queda en los logs
            logger.exception('Falló el envío del correo de recuperación de contraseña')
        return HttpResponseRedirect(self.success_url)
