import re
import time

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
                    instrucciones = views._cargar_prompt(views.AGENTES[tipo]).split('{mensaje}')[0].strip()
                    respuesta = views._llamar_con_contexto(instrucciones, [], mensaje)
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

        if tiempos:
            rapidos = sum(t <= 10 for t in tiempos)
            self.stdout.write(
                f'Clasificación correcta: {aciertos}/{len(CASOS)} · '
                f'respuestas en ≤ 10 s: {rapidos}/{len(tiempos)} · '
                f'más lenta: {max(tiempos):.1f} s'
            )
