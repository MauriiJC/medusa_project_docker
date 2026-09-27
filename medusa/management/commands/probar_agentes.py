import re
import time
from types import SimpleNamespace

from django.core.management.base import BaseCommand

from medusa import views

CASOS = [
    ('CRISIS', 'Él está afuera de mi casa ahora mismo y me amenazó con matarme'),
    ('CRISIS', 'Me acaba de golpear y tengo miedo de que vuelva esta noche'),
    ('LEGAL', '¿Cómo denuncio a mi pareja?'),
    ('LEGAL', '¿Qué derechos tengo si mi pareja me agrede?'),
    ('EMOCIONAL', 'Me siento muy triste y sola últimamente'),
    ('EMOCIONAL', 'Me siento culpable por lo que pasó'),
    ('OTRO', 'Dame una receta de arepas'),
    ('OTRO', '¿Quién ganó el último mundial?'),
]
LIMITE = {'CRISIS': 3, 'LEGAL': 4, 'EMOCIONAL': 4}


def _oraciones(texto):
    return len([o for o in re.split(r'(?<=[.!?])\s+', texto.strip()) if o])


class Command(BaseCommand):
    help = 'Envía mensajes de ejemplo a los agentes y muestra clasificación, tiempo y número de oraciones'

    def _probar_memoria(self):
        """RF-13: el agente debe recordar lo que la usuaria contó antes en la misma conversación."""
        primero = 'Me llamo Laura y vivo con mi pareja, que me grita todos los días'
        pregunta = '¿Recuerdas con quién vivo?'
        try:
            tipo1 = views._clasificar_mensaje(primero)
            resp1 = views._responder_agente(tipo1 if tipo1 in views.AGENTES else 'EMOCIONAL', [], primero)
            historial = [SimpleNamespace(role='user', content=primero), SimpleNamespace(role='bot', content=resp1)]
            con_memoria = views._responder_agente('EMOCIONAL', historial, pregunta)
            sin_memoria = views._responder_agente('EMOCIONAL', [], pregunta)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'[MEMORIA ERROR] {e}\n'))
            return
        recuerda = 'pareja' in con_memoria.lower()
        estilo = self.style.SUCCESS if recuerda else self.style.WARNING
        self.stdout.write(estilo(f'[MEMORIA {"OK" if recuerda else "no menciona a la pareja"}]'))
        self.stdout.write(f'  Usuaria: {primero}\n  Usuaria: {pregunta}\n  Medusa:  {con_memoria}')
        self.stdout.write(f'  Conversación nueva, misma pregunta:\n  Medusa:  {sin_memoria}\n')

    def handle(self, *args, **options):
        self.stdout.write(f'Modelo: {views.GROQ_MODEL} | Groq configurado: {bool(views.GROQ_API_KEY)}\n')
        aciertos, tiempos = 0, []
        for esperada, mensaje in CASOS:
            inicio = time.time()
            try:
                tipo = views._clasificar_mensaje(mensaje)
                if tipo == 'OTRO':
                    respuesta = views.RESPUESTA_OTRO
                else:
                    respuesta = views._responder_agente(tipo, [], mensaje)
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'[ERROR] {mensaje}\n  {e}\n'))
                continue
            segundos = time.time() - inicio
            tiempos.append(segundos)
            ok = tipo == esperada
            aciertos += ok
            n = _oraciones(respuesta)
            limite = LIMITE.get(tipo)
            largo = f'{n} oraciones' + ('' if limite is None or n <= limite else f' (supera {limite})')
            estilo = self.style.SUCCESS if ok else self.style.WARNING
            self.stdout.write(estilo(f'[{tipo} {"OK" if ok else "esperaba " + esperada}] {segundos:.1f} s · {largo}'))
            self.stdout.write(f'  Usuaria: {mensaje}\n  Medusa:  {respuesta}\n')

        self._probar_memoria()

        if tiempos:
            rapidos = sum(t <= 10 for t in tiempos)
            self.stdout.write(
                f'Clasificación correcta: {aciertos}/{len(CASOS)} · '
                f'respuestas en ≤ 10 s: {rapidos}/{len(tiempos)} · '
                f'más lenta: {max(tiempos):.1f} s'
            )
