from django.contrib import admin
from .models import Album, Photo


class PhotoInline(admin.TabularInline):
    model = Photo
    extra = 3


@admin.register(Album)
class AlbumAdmin(admin.ModelAdmin):
    list_display = ['title', 'date', 'created_by', 'is_public']
    list_editable = ['is_public']
    inlines = [PhotoInline]
