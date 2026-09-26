from unittest.mock import patch, MagicMock

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from .models import Conversation, Message, OTPCode


class RegistroTests(TestCase):
    def test_registro_exitoso(self):
        r = self.client.post(reverse('registro'), {
            'nombre': 'Ana',
            'email': 'ana@test.com',
            'password': 'Segura1234!',
            'password2': 'Segura1234!',
            'terminos': True,
        })
        self.assertRedirects(r, reverse('chat'))
        self.assertTrue(User.objects.filter(email='ana@test.com').exists())

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


class LoginTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('maria', 'maria@test.com', 'Segura1234!')

    def test_login_exitoso(self):
        r = self.client.post(reverse('login'), {
            'email': 'maria@test.com',
            'password': 'Segura1234!',
        })
        self.assertRedirects(r, reverse('chat'))

    def test_login_contrasena_incorrecta(self):
        r = self.client.post(reverse('login'), {
            'email': 'maria@test.com',
            'password': 'MalaClave',
        })
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Correo o contraseña incorrectos')

    def test_login_correo_inexistente_mensaje_generico(self):
        r = self.client.post(reverse('login'), {
            'email': 'noexiste@test.com',
            'password': 'cualquiera',
        })
        self.assertEqual(r.status_code, 200)
        # Debe mostrar el mismo mensaje genérico, no revelar que el correo no existe
        self.assertContains(r, 'Correo o contraseña incorrectos')

    def test_chat_requiere_login(self):
        r = self.client.get(reverse('chat'))
        self.assertRedirects(r, '/login/?next=/chat/')


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
        self.assertIn('respuesta', data)
        self.assertIn('conv_id', data)
        conv_id = data['conv_id']
        self.assertEqual(Message.objects.filter(conversation_id=conv_id).count(), 2)

    @patch('medusa.views._clasificar_mensaje', return_value='EMOCIONAL')
    @patch('medusa.views._llamar_con_contexto', return_value='Entiendo cómo te sientes.')
    def test_chat_api_continua_conversacion(self, mock_llamar, mock_clasificar):
        r1 = self.client.post(reverse('chat_api'), {'mensaje': 'Primer mensaje'})
        conv_id = r1.json()['conv_id']
        r2 = self.client.post(reverse('chat_api'), {'mensaje': 'Segundo mensaje', 'conv_id': conv_id})
        self.assertEqual(r2.json()['conv_id'], conv_id)
        self.assertEqual(Message.objects.filter(conversation_id=conv_id).count(), 4)

    def test_chat_api_saludo_simple(self):
        r = self.client.post(reverse('chat_api'), {'mensaje': 'hola'})
        self.assertEqual(r.status_code, 200)
        self.assertIn('respuesta', r.json())

    def test_chat_api_mensaje_vacio(self):
        r = self.client.post(reverse('chat_api'), {'mensaje': ''})
        self.assertEqual(r.status_code, 400)


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

    def test_eliminar_conversacion_ajena(self):
        otro = User.objects.create_user('otro', 'otro@test.com', 'pass')
        conv = Conversation.objects.create(user=otro, title='Ajena')
        r = self.client.delete(reverse('eliminar_conversacion_api', args=[conv.pk]))
        self.assertEqual(r.status_code, 404)

    def test_eliminar_historial(self):
        Conversation.objects.create(user=self.user, title='Conv 1')
        Conversation.objects.create(user=self.user, title='Conv 2')
        r = self.client.delete(reverse('eliminar_historial_api'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Conversation.objects.filter(user=self.user).count(), 0)


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
