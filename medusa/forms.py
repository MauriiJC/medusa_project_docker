from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError


class RegistrationForm(forms.Form):
    nombre = forms.CharField(max_length=150, required=False)
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput, min_length=8)
    password2 = forms.CharField(widget=forms.PasswordInput)
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
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)


class ProfileForm(forms.Form):
    nombre = forms.CharField(max_length=150, required=False)
    email = forms.EmailField()
    current_password = forms.CharField(widget=forms.PasswordInput, required=False)

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        if User.objects.filter(email=email).exclude(pk=self.user.pk).exists():
            raise ValidationError('Este correo ya está registrado.')
        return email

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get('email')
        if email and email != (self.user.email or '').lower() and self.user.has_usable_password():
            if not self.user.check_password(cleaned_data.get('current_password') or ''):
                self.add_error('current_password', 'Para cambiar tu correo ingresa tu contraseña actual.')
        return cleaned_data


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
