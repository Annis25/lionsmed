from django.core.management.base import BaseCommand
from apps.communications.outbox import deliver_batch
class Command(BaseCommand):
    help="Traiter un lot borné d'emails publics, sans afficher leur contenu."
    def add_arguments(self,parser):parser.add_argument("--limit",type=int,default=20)
    def handle(self,*args,**options):self.stdout.write(str(deliver_batch(options["limit"])))
