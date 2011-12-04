from django import forms
from django.contrib.auth.models import User
import re
from corehq.apps.domain.forms import clean_password, max_pwd, _BaseForm
from django.core.validators import validate_email
from corehq.apps.domain.models import Domain
from corehq.apps.domain.utils import new_domain_re

class NewWebUserRegistrationForm(forms.Form):
    """
    Form for a brand new user, before they've created a domain or done anything on CommCare HQ.
    """
    full_name = forms.CharField(label='Full Name', max_length=User._meta.get_field('first_name').max_length+User._meta.get_field('last_name').max_length+1)
    email = forms.EmailField(label='Email Address',
                                    max_length=User._meta.get_field('email').max_length,
                                    help_text='You will use this to log in')
    password  =  forms.CharField(label='Password', max_length=max_pwd, widget=forms.PasswordInput(render_value=False))

    def clean_full_name(self):
        data = self.cleaned_data['full_name'].split()
        return [data.pop(0)] + [' '.join(data)]

    def clean_email(self):
        data = self.cleaned_data['email'].strip()
        validate_email(data)
        if User.objects.filter(username__iexact=data).count() > 0:
            raise forms.ValidationError('Username already taken; please try another')
        return data

    def clean_password(self):
        return clean_password(self.cleaned_data.get('password'))

    def clean(self):
        for field in self.cleaned_data:
            if isinstance(self.cleaned_data[field], basestring):
                self.cleaned_data[field] = self.cleaned_data[field].strip()
        return self.cleaned_data


class FirstTimeDomainRegistrationForm(forms.Form):
    """
    Form for creating a domain for the first time
    """
    domain_name =  forms.CharField(label='Create my own domain with the name:', max_length=Domain._meta.get_field('name').max_length)
    tos_confirmed = forms.BooleanField(required=False, label="I agree to CommCare's Terms of Service") # Must be set to False to have the clean_*() routine called

    def clean_domain_name(self):
        data = self.cleaned_data['domain_name'].strip().lower()
        if not re.match("^%s$" % new_domain_re, data):
            raise forms.ValidationError('Only lowercase letters and numbers allowed. Single hyphens may be used to separate words.')
        if Domain.objects.filter(name__iexact=data).count() > 0 or Domain.objects.filter(name__iexact=data.replace('-', '.')).count():
            raise forms.ValidationError('Domain name already taken; please try another')
        return data

    def clean_tos_confirmed(self):
        data = self.cleaned_data['tos_confirmed']
        if data != True:
            raise forms.ValidationError('You must agree to our Terms Of Service in order to create your own domain')
        return data

    def clean(self):
        for field in self.cleaned_data:
            if isinstance(self.cleaned_data[field], basestring):
                self.cleaned_data[field] = self.cleaned_data[field].strip()
        return self.cleaned_data


class ResendConfirmationEmailForm(forms.Form):
    domain_name = forms.CharField(label='Requested domain name:', max_length=Domain._meta.get_field('name').max_length)

    def clean_domain_name(self):
        data = self.cleaned_data['domain_name'].strip()
        try:
            # Store domain for use in the view function
            dom = Domain.objects.get(name=data)
        except:
            raise forms.ValidationError("We have no record of a request for domain '%s'." % data)
        self.retrieved_domain = dom
        if dom.is_active:
                raise forms.ValidationError("Your domain '%s' has already been activated." % data)
        return data