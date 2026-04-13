from django.db import models
from accounts.models import User


class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    color = models.CharField(max_length=7, default='#c9a84c')

    def __str__(self):
        return self.name


class Article(models.Model):
    STATUS_CHOICES = [('DRAFT', 'Brouillon'), ('PUBLISHED', 'Publié')]
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    content = models.TextField()
    excerpt = models.TextField(max_length=300, blank=True)
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='articles')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    image = models.ImageField(upload_to='news/', blank=True, null=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='DRAFT')
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    reading_time = models.PositiveIntegerField(default=3)

    class Meta:
        ordering = ['-published_at']

    def __str__(self):
        return self.title
