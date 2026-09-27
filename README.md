# Medusa — SOS Mujer Berraca

Sistema de IA conversacional para acompañar a mujeres víctimas de violencia de género en Colombia.
Semillero FOCUS · Universidad CESMAG.

- Producción: https://medusaprojectdocker-production.up.railway.app
- Stack: Python 3.12, Django 6, Groq (respaldo Ollama), PostgreSQL en producción, SQLite en local.

## Instalación local en Windows 10/11

Requisitos: **Python 3.12 o superior** (Django 6 no funciona con 3.11), Git y una clave gratuita de Groq
(https://console.groq.com → API Keys).

```bat
git clone https://github.com/MauriiJC/medusa_project_docker.git
cd medusa_project_docker
py -3.12 -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Abre `.env` y reemplaza `GROQ_API_KEY` por tu clave. Luego:

```bat
python manage.py migrate
python manage.py runserver
```

Abre http://127.0.0.1:8000, crea una cuenta e inicia sesión.

- **Código OTP en local:** si no configuras `BREVO_API_KEY`, el código de 6 dígitos no se envía por correo;
  aparece en la terminal donde corre el servidor (`[Medusa] Codigo OTP para ...`).
- **Recuperación de contraseña en local:** el correo con el enlace también se muestra en esa terminal.
- Toda la configuración se hace en `.env`; no es necesario modificar el código.

## Pruebas automatizadas

```bat
python manage.py test medusa
```

Cubren registro, inicio de sesión con OTP, API del chat, conversaciones (incluido el aislamiento entre
usuarias), perfil, recuperación de contraseña y el respaldo del motor de IA.

## Estructura

| Ruta | Contenido |
|---|---|
| `medusa/views.py` | Vistas, chat, clasificación y enrutamiento a los agentes |
| `medusa/prompts/` | Un archivo `.txt` por agente: `clasificador`, `medusa_base`, `agente_crisis`, `agente_legal`, `agente_emocional`. Se leen en cada mensaje, así que un cambio aplica sin reiniciar. |
| `medusa/templates/medusa/` | Páginas (inicio, login, registro, chat, perfil…) |
| `medusa/tests.py` | Pruebas automatizadas |
| `config/settings.py` | Configuración (lee las variables de entorno) |

## Cadena de respaldo del chat

1. n8n, si `N8N_WEBHOOK_URL` está configurado (espera máxima 10 s).
2. Groq, si hay `GROQ_API_KEY` (espera máxima 30 s).
3. Ollama local (`OLLAMA_URL`), si Groq no tiene clave o falla.
4. Si ninguno responde: mensaje seguro con las líneas 155 y 123.

## Despliegue en Railway

El proyecto se construye con el `Dockerfile` (imagen `python:3.12-slim`), que aplica las migraciones y
arranca Gunicorn. Railway despliega automáticamente cada push a `main`. Variables necesarias en Railway:
`DJANGO_SECRET_KEY`, `DEBUG=False`, `ALLOWED_HOSTS`, `GROQ_API_KEY`, `GROQ_MODEL`, `BREVO_API_KEY`,
`BREVO_SENDER_EMAIL`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`; `DATABASE_URL` la inyecta el servicio
PostgreSQL.

Comandos útiles en la consola de Railway:

```bash
python manage.py probar_agentes                  # clasificación, tiempo y largo de respuesta de cada agente
python manage.py test_email correo@ejemplo.com   # prueba el envío de correos con Brevo
python manage.py axes_reset                      # quita los bloqueos por intentos fallidos
```
