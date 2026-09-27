from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    # ── Páginas ───────────────────────────────────────────────────────────────
    path('', views.landing, name='landing'),
    path('login/', views.login_view, name='login'),
    path('registro/', views.registro_view, name='registro'),
    path('verificar/', views.verify_otp_view, name='verify_otp'),
    path('reenviar-codigo/', views.resend_otp_view, name='resend_otp'),
    path('google-login/', views.google_login_start, name='google_login_start'),
    path('logout/', views.logout_view, name='logout'),
    path('chat/', views.chat, name='chat'),

    # ── Recuperación de contraseña ────────────────────────────────────────────
    path('password-reset/',
         views.MedusaPasswordResetView.as_view(),
         name='password_reset'),
    path('password-reset/enviado/',
         auth_views.PasswordResetDoneView.as_view(template_name='medusa/password_reset_done.htm'),
         name='password_reset_done'),
    path('password-reset/<uidb64>/<token>/',
         auth_views.PasswordResetConfirmView.as_view(template_name='medusa/password_reset_confirm.htm'),
         name='password_reset_confirm'),
    path('password-reset/completado/',
         auth_views.PasswordResetCompleteView.as_view(template_name='medusa/password_reset_complete.htm'),
         name='password_reset_complete'),

    # ── API de chat ───────────────────────────────────────────────────────────
    path('api/chat/', views.chat_api, name='chat_api'),
    path('api/agente/', views.agente_api, name='agente_api'),
    path('api/clasificar/', views.clasificar_api, name='clasificar_api'),

    # ── API de conversaciones ─────────────────────────────────────────────────
    path('api/conversaciones/', views.conversaciones_api, name='conversaciones_api'),
    path('api/conversaciones/<int:conv_id>/', views.conversacion_mensajes_api, name='conversacion_mensajes_api'),
    path('api/conversaciones/<int:conv_id>/eliminar/', views.eliminar_conversacion_api, name='eliminar_conversacion_api'),
    path('api/historial/eliminar/', views.eliminar_historial_api, name='eliminar_historial_api'),
]
