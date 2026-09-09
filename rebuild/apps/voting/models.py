import uuid
from django.conf import settings
from django.db import models


class Vote(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Brouillon"
        OPEN = "OPEN", "Ouvert"
        CLOSED = "CLOSED", "Clôturé"

    class Mode(models.TextChoices):
        SINGLE = "SINGLE", "Choix unique"
        MULTIPLE = "MULTIPLE", "Choix multiple"
        ELECTION = "ELECTION", "Élection"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=180)
    description = models.TextField(max_length=5000, blank=True)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.DRAFT)
    mode = models.CharField(max_length=10, choices=Mode.choices, default=Mode.SINGLE)
    opens_at = models.DateTimeField()
    closes_at = models.DateTimeField()
    min_choices = models.PositiveSmallIntegerField(default=1)
    max_choices = models.PositiveSmallIntegerField(default=1)
    blank_allowed = models.BooleanField(default=False)
    responsible = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="votes_managed")
    lions_year = models.ForeignKey("governance.LionsYear", on_delete=models.PROTECT, null=True, blank=True, related_name="votes")
    opened_at = models.DateTimeField(null=True, blank=True, help_text="Horodatage réel d'ouverture ; fige les électeurs")
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="votes_closed")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # Nom de table explicite : "voting_vote" est un nom de table legacy connu et refusé
        # par la garde anti-legacy de la commande migrate (apps/core/management/commands/migrate.py).
        db_table = "app_voting_vote"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=models.Q(closes_at__gt=models.F("opens_at")), name="vote_dates_ordered"),
            models.CheckConstraint(condition=models.Q(min_choices__gte=1) & models.Q(max_choices__gte=models.F("min_choices")), name="vote_cardinality_valid"),
            models.CheckConstraint(condition=models.Q(status__in=["DRAFT", "OPEN", "CLOSED"]), name="vote_status_valid"),
            models.CheckConstraint(condition=models.Q(mode__in=["SINGLE", "MULTIPLE", "ELECTION"]), name="vote_mode_valid"),
        ]


class VoteOption(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vote = models.ForeignKey(Vote, on_delete=models.PROTECT, related_name="options")
    label = models.CharField(max_length=180)
    presentation = models.TextField(max_length=2000, blank=True)
    order = models.PositiveSmallIntegerField()
    candidate_profile = models.ForeignKey("members.MemberProfile", on_delete=models.PROTECT, null=True, blank=True, related_name="candidacies")
    photo = models.ForeignKey("core.PublicImage", on_delete=models.PROTECT, null=True, blank=True, related_name="vote_option_photos")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order"]
        constraints = [models.UniqueConstraint(fields=["vote", "order"], name="voteoption_unique_order")]


class Elector(models.Model):
    """Population figée à l'ouverture. Aucune FK vers Ballot : voir Participation/Ballot."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vote = models.ForeignKey(Vote, on_delete=models.PROTECT, related_name="electors")
    profile = models.ForeignKey("members.MemberProfile", on_delete=models.PROTECT, related_name="vote_electorships")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["vote", "profile"], name="elector_unique_vote_profile")]


class Participation(models.Model):
    """Preuve qu'un électeur a déposé un bulletin. Aucune FK vers Ballot : ne permet pas de savoir quoi."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    elector = models.OneToOneField(Elector, on_delete=models.PROTECT, related_name="participation")
    submitted_at = models.DateTimeField(auto_now_add=True)


class Ballot(models.Model):
    """Bulletin définitif. Aucune FK vers électeur/membre, aucune IP, aucun timestamp précis."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vote = models.ForeignKey(Vote, on_delete=models.PROTECT, related_name="ballots")
    is_blank = models.BooleanField(default=False)


class BallotSelection(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ballot = models.ForeignKey(Ballot, on_delete=models.PROTECT, related_name="selections")
    option = models.ForeignKey(VoteOption, on_delete=models.PROTECT, related_name="selections")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["ballot", "option"], name="ballotselection_unique_ballot_option")]
