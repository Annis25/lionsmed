from django.contrib import admin
from .models import Vote, UserVote


@admin.register(Vote)
class VoteAdmin(admin.ModelAdmin):
    list_display = ['title', 'created_by', 'status', 'date_start', 'date_end', 'show_results_live', 'total_votes']
    list_filter = ['status', 'show_results_live']
    list_editable = ['status']


@admin.register(UserVote)
class UserVoteAdmin(admin.ModelAdmin):
    list_display = ['member', 'vote', 'choice', 'voted_at']
    list_filter = ['choice']
