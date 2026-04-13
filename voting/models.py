from django.db import models
from accounts.models import User


class Vote(models.Model):
    STATUS_CHOICES = [('DRAFT', 'Brouillon'), ('OPEN', 'Ouvert'), ('CLOSED', 'Clôturé')]
    title = models.CharField(max_length=200)
    question = models.TextField()
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_votes')
    date_start = models.DateTimeField()
    date_end = models.DateTimeField()
    show_results_live = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='DRAFT')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

    @property
    def total_votes(self):
        return self.uservotes.count()

    @property
    def results(self):
        from django.db.models import Count
        return self.uservotes.values('choice').annotate(count=Count('choice'))


class UserVote(models.Model):
    CHOICE_CHOICES = [('POUR', 'Pour'), ('CONTRE', 'Contre'), ('ABSTENTION', 'Abstention')]
    vote = models.ForeignKey(Vote, on_delete=models.CASCADE, related_name='uservotes')
    member = models.ForeignKey(User, on_delete=models.CASCADE, related_name='my_votes')
    choice = models.CharField(max_length=15, choices=CHOICE_CHOICES)
    voted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['vote', 'member']

    def __str__(self):
        return f"{self.member} → {self.vote} : {self.choice}"
