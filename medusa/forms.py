from django import forms
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError


class RegistrationForm(forms.Form):
    nombre = forms.CharField(max_length=150, required=False)
    email = forms.EmailField(error_messages={
        'required': 'Ingresa tu correo electrónico.',
        'invalid': 'Ingresa un correo electrónico válido.',
    })
    password = forms.CharField(widget=forms.PasswordInput, min_length=8, error_messages={
        'required': 'Ingresa una contraseña.',
        'min_length': 'La contraseña debe tener al menos 8 caracteres.',
    })
    password2 = forms.CharField(widget=forms.PasswordInput, error_messages={
        'required': 'Confirma tu contraseña.',
    })
    terminos = forms.BooleanField(error_messages={'required': 'Debes aceptar los términos para continuar.'})

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        if User.objects.filter(email=email).exists():
            raise ValidationError('Este correo ya está registrado.')
        return email

    def clean_password(self):
        password = self.cleaned_data.get('password')
        if password:
            try:
                validate_password(password)
            except ValidationError as e:
                raise ValidationError(list(e.messages))
        return password

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('password')
        p2 = cleaned_data.get('password2')
        if p1 and p2 and p1 != p2:
            self.add_error('password2', 'Las contraseñas no coinciden.')
        return cleaned_data


class LoginForm(forms.Form):
    email = forms.EmailField(error_messages={
        'required': 'Ingresa tu correo electrónico.',
        'invalid': 'Ingresa un correo electrónico válido.',
    })
    password = forms.CharField(widget=forms.PasswordInput, error_messages={
        'required': 'Ingresa tu contraseña.',
    })


class MedusaPasswordResetForm(PasswordResetForm):
    """Incluye cuentas creadas con Google (sin contraseña) para que puedan crear una."""

    def get_users(self, email):
        email_field = User.get_email_field_name()
        for user in User._default_manager.filter(**{f'{email_field}__iexact': email, 'is_active': True}):
            if email.casefold() == (getattr(user, email_field) or '').casefold():
                yield user


class ProfileForm(forms.Form):
    nombre = forms.CharField(max_length=150, required=False)


class OTPToggleForm(forms.Form):
    current_password = forms.CharField(widget=forms.PasswordInput, required=False)

    def __init__(self, *args, user, activar, **kwargs):
        self.user = user
        self.activar = activar
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        if (not self.activar and self.user.has_usable_password()
                and not self.user.check_password(cleaned_data.get('current_password') or '')):
            self.add_error('current_password', 'Contraseña incorrecta.')
        return cleaned_data


class OTPForm(forms.Form):
    code = forms.CharField(
        max_length=6,
        min_length=6,
        error_messages={
            'min_length': 'El código debe tener 6 dígitos.',
            'max_length': 'El código debe tener 6 dígitos.',
        }
    )
