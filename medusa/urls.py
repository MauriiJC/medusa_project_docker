from django.urls import path
from . import views

urlpatterns = [
    path('', views.landing, name='landing'),
    path('login/', views.login_view, name='login'),
    path('registro/', views.registro_view, name='registro'),
    path('verificar/', views.verify_otp_view, name='verify_otp'),
    path('reenviar-codigo/', views.resend_otp_view, name='resend_otp'),
    path('google-login/', views.google_login_start, name='google_login_start'),
    path('logout/', views.logout_view, name='logout'),
    path('chat/', views.chat, name='chat'),
    path('api/chat/', views.chat_api, name='chat_api'),
    path('api/agente/', views.agente_api, name='agente_api'),
    path('api/clasificar/', views.clasificar_api, name='clasificar_api'),
]
