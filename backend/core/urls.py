from django.urls import path
from . import views

urlpatterns = [
    path("ask/", views.ask, name="ask"),
    path("ask/stream/", views.ask_stream, name="ask_stream"),

    path("history/", views.history, name="history"),
    path("history/<int:pk>/", views.detail, name="detail"),
    path("history/<int:pk>/pin/", views.toggle_pin, name="toggle_pin"),
    path("history/<int:pk>/delete/", views.delete_question, name="delete_question"),
    path("history/clear/", views.clear_history, name="clear_history"),
]
