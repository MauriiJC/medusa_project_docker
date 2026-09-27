from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import views
from .models import Conversation, Message, OTPCode, UserProfile


_envio_otp = patch('medusa.views._send_otp_email', return_value=True)


def setUpModule():
    # Las pruebas no envían correos reales; el código se lee de la base de datos
    _envio_otp.start()


def tearDownModule():
    _envio_otp.stop()


def _ultimo_otp(user):
    return OTPCode.objects.filter(user=user, is_used=False).latest('created_at')


class RegistroTests(TestCase):
    def test_registro_exitoso_pide_codigo_otp(self):
        r = self.client.post(reverse('registro'), {
            'nombre': 'Ana',
            'email': 'ana@test.com',
            'password': 'Segura1234!',
            'password2': 'Segura1234!',
            'terminos': True,
        })
        self.assertRedirects(r, reverse('verify_otp'))
        user = User.objects.get(email='ana@test.com')
        r = self.client.post(reverse('verify_otp'), {'code': _ultimo_otp(user).code})
        self.assertRedirects(r, reverse('chat'))

    def test_registro_contrasenas_distintas(self):
        r = self.client.post(reverse('registro'), {
            'nombre': 'Ana',
            'email': 'ana2@test.com',
            'password': 'Segura1234!',
            'password2': 'Diferente99!',
            'terminos': True,
        })
        self.assertEqual(r.status_code, 200)
        self.assertFalse(User.objects.filter(email='ana2@test.com').exists())

    def test_registro_email_duplicado(self):
        User.objects.create_user('ana3', 'ana3@test.com', 'pass')
        r = self.client.post(reverse('registro'), {
            'nombre': 'Ana',
            'email': 'ana3@test.com',
            'password': 'Segura1234!',
            'password2': 'Segura1234!',
            'terminos': True,
        })
        self.assertEqual(r.status_code, 200)

    def test_registro_contrasena_corta_mensaje_en_espanol(self):
        r = self.client.post(reverse('registro'), {
            'email': 'corta@test.com', 'password': '123', 'password2': '123', 'terminos': True,
        })
        self.assertContains(r, 'La contraseña debe tener al menos 8 caracteres.')


class LoginTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('maria', 'maria@test.com', 'Segura1234!')

    def test_login_exitoso_con_otp(self):
        r = self.client.post(reverse('login'), {'email': 'maria@test.com', 'password': 'Segura1234!'})
        self.assertRedirects(r, reverse('verify_otp'))
        r = self.client.post(reverse('verify_otp'), {'code': _ultimo_otp(self.user).code})
        self.assertRedirects(r, reverse('chat'))

    def test_login_sin_otp_entra_directo(self):
        perfil = UserProfile.for_user(self.user)
        perfil.otp_enabled = False
        perfil.save()
        r = self.client.post(reverse('login'), {'email': 'MARIA@test.com', 'password': 'Segura1234!'})
        self.assertRedirects(r, reverse('chat'))

    def test_login_contrasena_incorrecta(self):
        r = self.client.post(reverse('login'), {'email': 'maria@test.com', 'password': 'MalaClave'})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Correo o contraseña incorrectos')

    def test_login_correo_inexistente_mensaje_generico(self):
        r = self.client.post(reverse('login'), {'email': 'noexiste@test.com', 'password': 'cualquiera'})
        self.assertEqual(r.status_code, 200)
        # Debe mostrar el mismo mensaje genérico, no revelar que el correo no existe
        self.assertContains(r, 'Correo o contraseña incorrectos')

    def test_bloqueo_tras_5_intentos_fallidos(self):
        for _ in range(5):
            r = self.client.post(reverse('login'), {'email': 'maria@test.com', 'password': 'MalaClave'})
        r = self.client.post(reverse('login'), {'email': 'maria@test.com', 'password': 'Segura1234!'})
        self.assertEqual(r.status_code, 429)
        self.assertContains(r, 'Acceso bloqueado temporalmente', status_code=429)

    def test_chat_requiere_login(self):
        r = self.client.get(reverse('chat'))
        self.assertRedirects(r, '/login/?next=/chat/')


class OTPVerificacionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('lina', 'lina@test.com', 'Segura1234!')
        self.client.post(reverse('login'), {'email': 'lina@test.com', 'password': 'Segura1234!'})

    def test_codigo_expirado_rechazado(self):
        otp = _ultimo_otp(self.user)
        OTPCode.objects.filter(pk=otp.pk).update(created_at=timezone.now() - timedelta(minutes=11))
        r = self.client.post(reverse('verify_otp'), {'code': otp.code})
        self.assertContains(r, 'El código expiró')

    def test_codigo_reenviado_invalida_el_anterior(self):
        anterior = _ultimo_otp(self.user).code
        self.client.get(reverse('resend_otp'))
        nuevo = _ultimo_otp(self.user).code
        if nuevo != anterior:
            r = self.client.post(reverse('verify_otp'), {'code': anterior})
            self.assertContains(r, 'Código incorrecto')

    def test_codigo_usado_no_se_reutiliza(self):
        codigo = _ultimo_otp(self.user).code
        self.client.post(reverse('verify_otp'), {'code': codigo})
        self.client.post(reverse('logout'))
        self.client.post(reverse('login'), {'email': 'lina@test.com', 'password': 'Segura1234!'})
        if _ultimo_otp(self.user).code != codigo:
            r = self.client.post(reverse('verify_otp'), {'code': codigo})
            self.assertContains(r, 'Código incorrecto')


class OTPCodeTests(TestCase):
    def test_genera_codigo_6_digitos(self):
        user = User.objects.create_user('test', 'test@test.com', 'pass')
        otp = OTPCode.generate_for(user)
        self.assertEqual(len(otp.code), 6)
        self.assertTrue(otp.code.isdigit())

    def test_invalidar_otps_anteriores(self):
        user = User.objects.create_user('test2', 'test2@test.com', 'pass')
        otp1 = OTPCode.generate_for(user)
        otp2 = OTPCode.generate_for(user)
        otp1.refresh_from_db()
        self.assertTrue(otp1.is_used)
        self.assertFalse(otp2.is_used)


class ChatAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('luisa', 'luisa@test.com', 'Segura1234!')
        self.client.force_login(self.user)

    @patch('medusa.views._clasificar_mensaje', return_value='EMOCIONAL')
    @patch('medusa.views._llamar_con_contexto', return_value='Hola, estoy aquí para escucharte.')
    def test_chat_api_crea_mensajes(self, mock_llamar, mock_clasificar):
        r = self.client.post(reverse('chat_api'), {'mensaje': '¿Cómo estás?'})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data['agente'], 'EMOCIONAL')
        self.assertEqual(Message.objects.filter(conversation_id=data['conv_id']).count(), 2)

    @patch('medusa.views._clasificar_mensaje', return_value='EMOCIONAL')
    @patch('medusa.views._llamar_con_contexto', return_value='Entiendo cómo te sientes.')
    def test_chat_api_continua_conversacion_con_memoria(self, mock_llamar, mock_clasificar):
        r1 = self.client.post(reverse('chat_api'), {'mensaje': 'Primer mensaje'})
        conv_id = r1.json()['conv_id']
        # Misma fecha exacta para ambos mensajes: el orden debe resolverse por id en cualquier sistema operativo
        Message.objects.filter(conversation_id=conv_id).update(created_at=timezone.now())
        r2 = self.client.post(reverse('chat_api'), {'mensaje': 'Segundo mensaje', 'conv_id': conv_id})
        self.assertEqual(r2.json()['conv_id'], conv_id)
        self.assertEqual(Message.objects.filter(conversation_id=conv_id).count(), 4)
        historial = mock_llamar.call_args.args[1]
        self.assertEqual([m.content for m in historial], ['Primer mensaje', 'Entiendo cómo te sientes.'])
        r = self.client.get(reverse('conversacion_mensajes_api', args=[conv_id]))
        self.assertEqual([m['role'] for m in r.json()['mensajes']], ['user', 'bot', 'user', 'bot'])

    @patch('medusa.views._clasificar_mensaje', side_effect=AssertionError('no debe consultar el modelo'))
    def test_chat_api_saludo_simple_sin_modelo(self, mock_clasificar):
        for saludo in ('hola', '¡Hola!', 'Buenos días'):
            r = self.client.post(reverse('chat_api'), {'mensaje': saludo})
            self.assertEqual(r.status_code, 200)
            self.assertIn('Hola', r.json()['respuesta'])

    @patch('medusa.views._clasificar_mensaje', return_value='OTRO')
    @patch('medusa.views._llamar_con_contexto', side_effect=AssertionError('no debe responder el tema ajeno'))
    def test_tema_ajeno_redirige(self, mock_llamar, mock_clasificar):
        r = self.client.post(reverse('chat_api'), {'mensaje': 'dame una receta de arepas'})
        self.assertEqual(r.json()['agente'], 'OTRO')
        self.assertIn('bienestar y seguridad', r.json()['respuesta'])

    @patch('medusa.views._clasificar_mensaje', side_effect=RuntimeError('sin motores'))
    def test_sin_motores_mensaje_seguro(self, mock_clasificar):
        with self.assertLogs('medusa.views', level='ERROR'):
            r = self.client.post(reverse('chat_api'), {'mensaje': 'necesito ayuda'})
        self.assertEqual(r.status_code, 200)
        self.assertIn('155', r.json()['respuesta'])
        self.assertIn('123', r.json()['respuesta'])

    def test_chat_api_mensaje_vacio(self):
        r = self.client.post(reverse('chat_api'), {'mensaje': ''})
        self.assertEqual(r.status_code, 400)

    def test_chat_api_exige_token_csrf(self):
        c = Client(enforce_csrf_checks=True)
        c.force_login(self.user)
        r = c.post(reverse('chat_api'), {'mensaje': 'hola'})
        self.assertEqual(r.status_code, 403)


class ClasificadorYRespaldoTests(TestCase):
    def test_clasificador_tolera_formato(self):
        casos = {'CRISIS.': 'CRISIS', '**Legal**': 'LEGAL', 'Categoría: otro': 'OTRO', '???': 'EMOCIONAL'}
        for salida, esperada in casos.items():
            with patch('medusa.views._llamar_ollama', return_value=salida):
                self.assertEqual(views._clasificar_mensaje('mensaje'), esperada)

    @patch('medusa.views._llamar_con_contexto', return_value=(
        'Tienes todo el derecho a vivir sin violencia.  \n\nLa Ley 1257 de 2008 te protege. '
        'Puedes ir a la Comisaría de Familia. No necesitas abogado.  \n\n'
        'Si hay niños, el ICBF puede intervenir. También puedes llamar a la línea 155.'
    ))
    def test_respuesta_limitada_en_oraciones(self, mock_llamar):
        legal = views._responder_agente('LEGAL', [], '¿Qué derechos tengo?')
        self.assertEqual(legal, 'Tienes todo el derecho a vivir sin violencia. La Ley 1257 de 2008 te protege. '
                                'Puedes ir a la Comisaría de Familia. No necesitas abogado.')
        crisis = views._responder_agente('CRISIS', [], 'me amenazó')
        self.assertEqual(crisis.count('.'), 3)

    @patch('medusa.views.GROQ_API_KEY', 'clave-invalida')
    @patch('medusa.views._llamar_ollama_directo', return_value='Respuesta desde Ollama')
    @patch('medusa.views._llamar_groq_con_contexto', side_effect=RuntimeError('401 Groq'))
    def test_groq_falla_usa_ollama(self, mock_groq, mock_ollama):
        with self.assertLogs('medusa.views', level='ERROR'):
            texto = views._llamar_con_contexto('Instrucciones', [], 'hola')
        self.assertEqual(texto, 'Respuesta desde Ollama')

    def test_endpoints_n8n_cerrados_sin_token(self):
        for nombre in ('clasificar_api', 'agente_api'):
            r = self.client.post(reverse(nombre), '{"mensaje": "hola"}', content_type='application/json')
            self.assertEqual(r.status_code, 401)


class ConversacionesAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('sofia', 'sofia@test.com', 'Segura1234!')
        self.client.force_login(self.user)

    def test_listar_conversaciones(self):
        Conversation.objects.create(user=self.user, title='Primera')
        r = self.client.get(reverse('conversaciones_api'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.json()['conversaciones']), 1)

    def test_eliminar_conversacion(self):
        conv = Conversation.objects.create(user=self.user, title='A borrar')
        r = self.client.delete(reverse('eliminar_conversacion_api', args=[conv.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Conversation.objects.filter(pk=conv.pk).exists())

    def test_conversacion_ajena_no_encontrada(self):
        otro = User.objects.create_user('otro', 'otro@test.com', 'pass')
        conv = Conversation.objects.create(user=otro, title='Ajena')
        Message.objects.create(conversation=conv, role='user', content='secreto')
        r = self.client.get(reverse('conversacion_mensajes_api', args=[conv.pk]))
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json(), {'error': 'No encontrada'})
        r = self.client.delete(reverse('eliminar_conversacion_api', args=[conv.pk]))
        self.assertEqual(r.status_code, 404)
        self.assertTrue(Conversation.objects.filter(pk=conv.pk).exists())

    def test_eliminar_historial(self):
        Conversation.objects.create(user=self.user, title='Conv 1')
        Conversation.objects.create(user=self.user, title='Conv 2')
        r = self.client.delete(reverse('eliminar_historial_api'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Conversation.objects.filter(user=self.user).count(), 0)

    def test_api_requiere_sesion(self):
        r = Client().get(reverse('conversaciones_api'))
        self.assertEqual(r.status_code, 302)
        self.assertIn('/login/', r['Location'])


class PerfilTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('paula', 'paula@test.com', 'Segura1234!', first_name='Paula')
        self.client.force_login(self.user)

    def test_editar_nombre(self):
        r = self.client.post(reverse('perfil'), {'accion': 'datos', 'nombre': 'Paula Andrea'})
        self.assertRedirects(r, reverse('perfil'))
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Paula Andrea')

    def test_correo_no_se_puede_cambiar(self):
        self.client.post(reverse('perfil'), {'accion': 'datos', 'nombre': 'Paula', 'email': 'otro@test.com'})
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'paula@test.com')

    def test_desactivar_otp_exige_contrasena(self):
        self.client.post(reverse('perfil'), {'accion': 'otp', 'current_password': 'Incorrecta1'})
        self.assertTrue(UserProfile.for_user(self.user).otp_enabled)
        self.client.post(reverse('perfil'), {'accion': 'otp', 'current_password': 'Segura1234!'})
        self.assertFalse(UserProfile.for_user(self.user).otp_enabled)
        self.client.post(reverse('perfil'), {'accion': 'otp'})
        self.assertTrue(UserProfile.for_user(self.user).otp_enabled)

    def test_cambiar_contrasena_mantiene_sesion(self):
        r = self.client.post(reverse('perfil'), {
            'accion': 'password', 'old_password': 'Segura1234!',
            'new_password1': 'NuevaClave#2026', 'new_password2': 'NuevaClave#2026',
        })
        self.assertRedirects(r, reverse('perfil'))
        self.assertEqual(self.client.get(reverse('perfil')).status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NuevaClave#2026'))


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class RecuperacionContrasenaTests(TestCase):
    def test_envia_enlace_y_no_revela_si_el_correo_existe(self):
        User.objects.create_user('rosa', 'rosa@test.com', 'Segura1234!')
        r = self.client.post(reverse('password_reset'), {'email': 'rosa@test.com'})
        self.assertRedirects(r, reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('/password-reset/', mail.outbox[0].body)

        r = self.client.post(reverse('password_reset'), {'email': 'noexiste@test.com'})
        self.assertRedirects(r, reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 1)

    def test_cuenta_creada_con_google_recibe_enlace(self):
        u = User.objects.create_user('google', 'google@test.com')
        u.set_unusable_password()
        u.save()
        self.client.post(reverse('password_reset'), {'email': 'google@test.com'})
        self.assertEqual(len(mail.outbox), 1)
