import uuid
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction, IntegrityError
from django.utils import timezone
from apps.core.permissions import can, effective_role, MEMBERS
from apps.core.models import AuditEvent
from apps.members.models import MemberProfile
from .models import Vote, VoteOption, Elector, Participation, Ballot, BallotSelection


def require(actor, capability, obj=None):
    if not can(actor, capability, obj):
        raise PermissionDenied


def audit(actor, action, obj):
    # Jamais de choix, note ou commentaire dans l'audit : uniquement type/identifiant d'objet.
    AuditEvent.objects.create(actor=actor, action=action, object_type=obj._meta.object_name, object_id=str(obj.pk))


@transaction.atomic
def add_option(*, actor, vote, label, presentation="", candidate_profile=None, photo=None):
    require(actor, "vote.manage")
    vote = Vote.objects.select_for_update().get(pk=vote.pk)
    if vote.status != Vote.Status.DRAFT:
        raise ValidationError("Les choix ne sont modifiables qu'en brouillon.")
    from django.db.models import Max
    order = (vote.options.aggregate(m=Max("order"))["m"] or 0) + 1
    option = VoteOption(vote=vote, label=label[:180], presentation=presentation[:2000], order=order,
        candidate_profile=candidate_profile, photo=photo)
    option.full_clean()
    option.save()
    audit(actor, "vote.option_added", option)
    return option


@transaction.atomic
def remove_option(*, actor, option):
    require(actor, "vote.manage")
    vote = Vote.objects.select_for_update().get(pk=option.vote_id)
    if vote.status != Vote.Status.DRAFT:
        raise ValidationError("Les choix ne sont modifiables qu'en brouillon.")
    option.delete()
    audit(actor, "vote.option_removed", vote)


@transaction.atomic
def open_vote(*, actor, vote):
    """Fige les électeurs à l'instant de l'ouverture. INVITE exclu, comptes inactifs exclus."""
    require(actor, "vote.manage")
    vote = Vote.objects.select_for_update().get(pk=vote.pk)
    if vote.status != Vote.Status.DRAFT:
        raise ValidationError("Seul un scrutin en brouillon peut être ouvert.")
    if vote.options.count() < 1:
        raise ValidationError("Au moins un choix est requis avant ouverture.")
    now = timezone.now()
    eligible = MemberProfile.objects.filter(status=MemberProfile.Status.ACTIVE, user__is_active=True)
    electors = []
    for profile in eligible.select_related("user"):
        if effective_role(profile.user) in MEMBERS:
            electors.append(Elector(vote=vote, profile=profile))
    Elector.objects.bulk_create(electors)
    vote.status = Vote.Status.OPEN
    vote.opened_at = now
    vote.full_clean()
    vote.save()
    audit(actor, "vote.opened", vote)
    return vote


@transaction.atomic
def close_vote(*, actor, vote):
    """Idempotent : clôturer un scrutin déjà clos ne fait rien de plus."""
    require(actor, "vote.manage")
    vote = Vote.objects.select_for_update().get(pk=vote.pk)
    if vote.status == Vote.Status.CLOSED:
        return vote
    if vote.status != Vote.Status.OPEN:
        raise ValidationError("Seul un scrutin ouvert peut être clôturé.")
    vote.status = Vote.Status.CLOSED
    vote.closed_at = timezone.now()
    vote.closed_by = actor
    vote.full_clean()
    vote.save()
    audit(actor, "vote.closed", vote)
    return vote


@transaction.atomic
def cast_vote(*, actor, vote, option_ids, is_blank=False):
    """Service unique de dépôt. Verrouille Vote puis Elector, ordre identique pour tous les chemins."""
    require(actor, "vote.cast", vote)
    # Verrou déterministe : Vote d'abord.
    vote = Vote.objects.select_for_update().get(pk=vote.pk)
    now = timezone.now()
    if vote.status != Vote.Status.OPEN or not (vote.opens_at <= now < vote.closes_at):
        raise ValidationError("Ce scrutin n'est pas ouvert.")
    try:
        profile = actor.member_profile
        elector = Elector.objects.select_for_update().get(vote=vote, profile=profile)
    except Elector.DoesNotExist:
        raise PermissionDenied("Vous n'êtes pas habilité pour ce scrutin.")
    if Participation.objects.filter(elector=elector).exists():
        raise ValidationError("Votre bulletin a déjà été enregistré.")
    option_ids = list(dict.fromkeys(option_ids or []))
    if is_blank:
        if not vote.blank_allowed:
            raise ValidationError("Le vote blanc n'est pas autorisé pour ce scrutin.")
        if option_ids:
            raise ValidationError("Le vote blanc exclut tout choix.")
    else:
        if not (vote.min_choices <= len(option_ids) <= vote.max_choices):
            raise ValidationError("Nombre de choix invalide pour ce scrutin.")
        valid_ids = set(vote.options.values_list("id", flat=True))
        if not set(option_ids) <= valid_ids:
            raise ValidationError("Un choix sélectionné n'appartient pas à ce scrutin.")
    ballot = Ballot(vote=vote, is_blank=is_blank)
    ballot.full_clean()
    ballot.save()
    try:
        BallotSelection.objects.bulk_create([BallotSelection(ballot=ballot, option_id=option_id) for option_id in option_ids])
        Participation.objects.create(elector=elector)
    except IntegrityError:
        raise ValidationError("Votre bulletin a déjà été enregistré.")
    # Reçu sans choix, hors transaction email : intention seulement.
    from apps.communications.services import notify
    notify(recipient=actor, category="VOTE", title=f"Bulletin enregistré — {vote.title}",
        excerpt="Votre bulletin a bien été pris en compte.", event_key=f"vote_receipt:{vote.pk}:{actor.pk}",
        target_kind="", target_id="", email=False)
    return ballot
