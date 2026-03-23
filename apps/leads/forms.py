from django import forms
from phonenumber_field.formfields import PhoneNumberField


class LeadForm(forms.Form):
    fullname = forms.CharField(
        label="ФИО",
        max_length=255,
    )
    phone_number = PhoneNumberField(
        label="Телефон",
        region="RU",
    )
    email = forms.EmailField(
        label="Email",
    )
    comment = forms.CharField(
        label="Комментарий",
        required=False,
        widget=forms.Textarea(attrs={"rows": 4}),
    )
    agree_to_policy = forms.BooleanField(
        label="Я согласен на обработку персональных данных",
        required=True,
    )
