from django.contrib import admin
from .models import Question, ModelResponse, Judgment

admin.site.register(Question)
admin.site.register(ModelResponse)
admin.site.register(Judgment)
