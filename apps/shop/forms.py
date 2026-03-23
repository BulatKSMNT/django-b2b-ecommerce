from django import forms


class AddToCartForm(forms.Form):
    quantity = forms.IntegerField(min_value=1, initial=1, label="Количество")
    next = forms.CharField(required=False, widget=forms.HiddenInput)


class UpdateCartItemForm(forms.Form):
    quantity = forms.IntegerField(min_value=0, initial=1, label="Количество")
    next = forms.CharField(required=False, widget=forms.HiddenInput)
