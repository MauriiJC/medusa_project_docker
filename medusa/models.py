import random
import string
from datetime import timedelta

from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class OTPCode(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='otp_codes')
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def is_valid(self):
        return not self.is_used and (timezone.now() - self.created_at) < timedelta(minutes=10)

    @classmethod
    def generate_for(cls, user):
        cls.objects.filter(user=user, is_used=False).update(is_used=True)
        code = ''.join(random.choices(string.digits, k=6))
        return cls.objects.create(user=user, code=code)


class Conversation(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='conversations')
    title = models.CharField(max_length=200, default='Nueva conversación')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f'{self.user.username} — {self.title[:40]}'


class Message(models.Model):
    ROLES = [('user', 'Usuario'), ('bot', 'Medusa')]
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=10, choices=ROLES)
    content = models.TextField()
    agente = models.CharField(max_length=20, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
