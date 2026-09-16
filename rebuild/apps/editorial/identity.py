# Informations institutionnelles explicitement fournies par le propriétaire.
NAME = "Lions Club Sfax-Méditerranée"
CITY = "Sfax"
COUNTRY = "Tunisie"
DISTRICT = "District 414 Tunisie"
AFFILIATION = "Lions International"
MOTTO = "Nous servons."

# Textes officiels fournis par le club (recette utilisateur) — servent de contenu
# par défaut tant qu'aucune EditorialSection validée ne les remplace (axes réels
# uniquement : DIABETE/ENVIRONNEMENT/HUMANITAIRE/JEUNESSE, voir EditorialSection.KEYS).
# AXES_INTRO/AXES_DEFAULT_BODY restent utilisés par la page "Notre Club"
# (components/public/priorities.html) — non concernée par cette refonte, conservée
# à l'identique pour ne rien y casser.
AXES_INTRO = ("Le Lions Club Sfax-Méditerranée inscrit ses actions dans les grandes causes "
    "portées par Lions Clubs International. À travers ses projets et initiatives, le club "
    "agit au service de la communauté et contribue à répondre aux enjeux sociaux, sanitaires "
    "et environnementaux.\n\nNotre club concentre particulièrement ses efforts sur quatre axes "
    "prioritaires : le diabète, l’environnement, l’action humanitaire et la jeunesse. Il "
    "contribue également, selon les projets et les besoins, à d’autres causes portées par le "
    "mouvement Lions, notamment la santé oculaire, le cancer infantile, la lutte contre la "
    "malnutrition, l’aide aux victimes de catastrophes ainsi que la santé mentale et le "
    "bien-être.")

AXES_DEFAULT_BODY = {
    "DIABETE": ("Nous contribuons à la prévention et à la sensibilisation au diabète, "
        "notamment à travers des campagnes d’information, des actions de dépistage et des "
        "initiatives encourageant l’adoption d’un mode de vie plus sain."),
    "ENVIRONNEMENT": ("Protéger notre environnement fait partie de nos engagements majeurs. "
        "Le club organise et soutient des actions écologiques, de sensibilisation, de "
        "nettoyage et de préservation de l’environnement, tout en encourageant l’engagement "
        "citoyen en faveur d’un avenir plus durable."),
    "HUMANITAIRE": ("La solidarité est au cœur de notre mission. Nous menons des actions "
        "humanitaires et sociales au profit des personnes et familles en situation de "
        "vulnérabilité, en mobilisant nos membres, bénévoles et partenaires autour des besoins "
        "de la communauté."),
    "JEUNESSE": ("Nous accordons une importance particulière aux jeunes en favorisant leur "
        "engagement, leur développement personnel, leur leadership et leur participation à la "
        "vie associative et citoyenne."),
}

# Section unifiée « Nos causes d'engagement » (page d'accueil uniquement) — recette
# utilisateur (refonte maquette) :
# fusionne les quatre axes prioritaires et quatre des cinq grandes causes internationales
# en une seule grille de 8 cartes. Seule la santé mentale et le bien-être reste traitée à
# part, dans le bandeau discret sous la grille (voir SANTE_MENTALE) — c'est elle, et elle
# seule désormais, qui porte le traitement "grande cause secondaire" du skill §7.
CAUSES_ENGAGEMENT_INTRO = ("Inspirés par les grandes causes du Lions Clubs International, "
    "nous agissons concrètement au service des communautés à Sfax et au-delà.")

CAUSES_ENGAGEMENT = [
    {"axis": None, "title": "Cancer infantile", "image": "images/cause-cancer-infantile.png",
     "alt": "Petite fille souriante portant un foulard, tenant un ours en peluche dans ses bras.",
     "body": ("Nous soutenons les enfants touchés par le cancer et leurs familles, à travers "
         "des actions de sensibilisation, d’accompagnement et d’espoir.")},
    {"axis": "DIABETE", "title": "Diabète", "image": "images/cause-diabete.png",
     "alt": "Main tenant un lecteur de glycémie affichant un résultat, après un test au doigt.",
     "body": ("Nous contribuons à la prévention, au dépistage et à la sensibilisation au "
         "diabète pour une meilleure qualité de vie.")},
    {"axis": None, "title": "Aide en cas de catastrophe", "image": "images/cause-aide-catastrophes.png",
     "alt": "Bénévole en gilet Lions International vu de dos, face à des bâtiments endommagés.",
     "body": ("Nous nous mobilisons pour apporter assistance et soutien aux populations "
         "affectées par les catastrophes naturelles ou autres situations d’urgence.")},
    {"axis": "ENVIRONNEMENT", "title": "Environnement", "image": "images/cause-environnement.png",
     "alt": "Mains plantant une jeune pousse dans la terre, en extérieur.",
     "body": ("Nous agissons pour la préservation de notre environnement à travers des "
         "actions de sensibilisation, de nettoyage et de développement durable.")},
    {"axis": "HUMANITAIRE", "title": "Humanitaire", "image": "images/cause-humanitaire.png",
     "alt": "Bénévole en tenue Lions International remettant un colis à une personne.",
     "body": ("Nous menons des actions sociales au profit des personnes et familles en "
         "situation de vulnérabilité.")},
    {"axis": None, "title": "Lutte contre la faim", "image": "images/cause-lutte-faim.png",
     "alt": "Mains tendant un bol de nourriture à une personne, entourées de bénévoles Lions.",
     "body": ("Nous soutenons les actions de solidarité alimentaire et de sensibilisation, "
         "particulièrement auprès des populations les plus vulnérables.")},
    {"axis": None, "title": "Santé oculaire", "image": "images/cause-sante-oculaire.png",
     "alt": "Jeune fille passant un test de vue à l’aide d’un phoroptère.",
     "body": ("Fidèles à l’engagement historique des Lions pour la vue, nous soutenons la "
         "prévention, le dépistage et l’accès aux soins visuels.")},
    {"axis": "JEUNESSE", "title": "Jeunesse", "image": "images/cause-jeunesse.png",
     "alt": "Groupe de jeunes se tenant par l’épaule, de dos, en tee-shirt Lions International.",
     "body": ("Nous encourageons les jeunes à s’engager dans des projets citoyens, à "
         "développer leur leadership et à construire un meilleur avenir.")},
]

# Cinquième grande cause internationale : seule à garder le traitement "bande distincte,
# volontairement plus discrète" du skill (§7) — jamais au même niveau que les 8 cartes.
SANTE_MENTALE = {"title": "Santé mentale et bien-être",
    "body": ("Nous soutenons la sensibilisation à la santé mentale, le bien-être et une "
        "meilleure compréhension des enjeux qui y sont associés, pour des communautés plus "
        "fortes et plus inclusives.")}

VALEURS = [
    ("Service", "Écouter les besoins de la communauté et apporter un changement positif."),
    ("Excellence", "Viser un service de qualité et progresser continuellement."),
    ("Diversité", "Accueillir et valoriser les différences et les expériences de chacun."),
    ("Collaboration", "Travailler ensemble avec nos membres, les collectivités et nos partenaires."),
    ("Intégrité", "Agir avec fiabilité, responsabilité et confiance."),
    ("Innovation", "Évoluer, créer et adopter de meilleures pratiques."),
]
