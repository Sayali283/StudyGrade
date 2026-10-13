from django import forms
from django.conf import settings
from .models import Notes
from .services.document_service import validate_document_file, DocumentExtractionError


class NotesForm(forms.ModelForm):
    class Meta:
        model = Notes
        fields = ['subject', 'file']
        widgets = {
            'subject': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Biology - Chapter 4 Photosynthesis',
                'required': True,
                'maxlength': 100,
            }),
            'file': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.pdf,.docx,.txt,.md,.markdown',
                'required': True,
            }),
        }

    def clean_subject(self):
        subject = (self.cleaned_data.get('subject') or '').strip()
        if not subject:
            raise forms.ValidationError("Subject title is required.")
        if len(subject) > 100:
            raise forms.ValidationError("Subject title cannot exceed 100 characters.")
        return subject

    def clean_file(self):
        uploaded_file = self.cleaned_data.get('file')
        if not uploaded_file:
            raise forms.ValidationError("Please select a file to upload.")

        max_upload_size = getattr(settings, 'MAX_UPLOAD_SIZE_BYTES', 10 * 1024 * 1024)
        if uploaded_file.size > max_upload_size:
            max_mb = max_upload_size / (1024 * 1024)
            actual_mb = round(uploaded_file.size / (1024 * 1024), 2)
            raise forms.ValidationError(
                f"File size ({actual_mb} MB) exceeds the maximum allowed size of {max_mb:.0f} MB."
            )

        if uploaded_file.size == 0:
            raise forms.ValidationError("The uploaded document is empty (0 bytes).")

        try:
            validate_document_file(uploaded_file)
        except DocumentExtractionError as err:
            raise forms.ValidationError(str(err))

        return uploaded_file

