from django.db import models
from datetime import date

from ecolle.settings import HEURE_DEBUT, HEURE_FIN, INTERVALLE

class NoteManager(models.Manager):
    def listeNotesApp(self,colleur):
        requete = "SELECT s.numero semaine, n.id, n.date_colle, n.heure, n.note, n.commentaire, n.matiere_id, n.classe_id, n.eleve_id, n.rattrapee\
                   FROM accueil_note n\
                   INNER JOIN accueil_semaine s\
                   ON n.semaine_id=s.id\
                   WHERE n.colleur_id= %s\
                   ORDER BY s.numero DESC, n.date_colle DESC, n.heure DESC"
        with connection.cursor() as cursor:
            cursor.execute(requete,(colleur.pk,))
            notes = dictfetchall(cursor)
            return [[note["id"], note["matiere_id"], note["classe_id"], note["note"],  note["commentaire"], note["semaine"], datetime.combine(note["date_colle"],
                time(note["heure"] // 4, 15 * (note["heure"] % 4))).replace(tzinfo=timezone.utc).timestamp(), note["eleve_id"], bool(note["rattrapee"])] for note in notes]

    def listeNotes(self,colleur,classe,matiere):
        requete = "SELECT n.id pk, s.numero semaine, p.titre, p.detail, n.date_colle, n.heure, u.first_name prenom, u.last_name nom, n.note, n.commentaire\
                   FROM accueil_note n\
                   LEFT OUTER JOIN accueil_eleve e\
                   ON n.eleve_id = e.id\
                   LEFT OUTER JOIN accueil_user u\
                   ON u.eleve_id = e.id\
                   INNER JOIN accueil_semaine s\
                   ON n.semaine_id=s.id\
                   LEFT OUTER JOIN accueil_programme p\
                   ON p.semaine_id = s.id AND p.classe_id= %s AND p.matiere_id = %s\
                   WHERE n.classe_id = %s AND n.colleur_id= %s AND n.matiere_id = %s\
                   ORDER BY s.numero DESC, n.date_colle DESC, n.heure DESC"
        with connection.cursor() as cursor:
            cursor.execute(requete,(classe.pk,matiere.pk,classe.pk,colleur.pk,matiere.pk))
            notes = dictfetchall(cursor)
        listeNotes = []
        listeDates = []
        listeHeures = []
        listeEleves = []
        nbeleves=nbheures=nbdates=0
        try:
            heure,date_colle,semaine,titre,detail = notes[0]['heure'],notes[0]['date_colle'], notes[0]['semaine'], notes[0]['titre'], notes[0]['detail']
        except Exception:
            pass
        else:
            for note in notes:
                if not (note['heure'] == heure and note['date_colle'] == date_colle):
                    nbheures += nbeleves
                    listeHeures.append((listeEleves,heure,nbeleves))
                    heure = note['heure']
                    nbeleves=1
                    listeEleves = [("Élève fictif" if not note['prenom'] else "{} {}".format(note['prenom'].title(),note['nom'].upper()),note['note'],note['commentaire'],note['pk'])]
                    if note['date_colle'] != date_colle:
                        nbdates+=nbheures
                        listeDates.append((listeHeures,date_colle,nbheures))
                        date_colle = note['date_colle']
                        nbheures=0
                        listeHeures=[]
                        if note['semaine'] != semaine:
                            listeNotes.append((listeDates,semaine,titre,detail,nbdates))
                            semaine,titre,detail = note['semaine'],note['titre'],note['detail']
                            nbdates=0
                            listeDates=[]
                elif note['prenom']:
                    listeEleves.append(("{} {}".format(note['prenom'].title(),note['nom'].upper()),note['note'],note['commentaire'],note['pk']))
                    nbeleves+=1
                else:
                    listeEleves.append(("Élève fictif",note['note'],note['commentaire'],note['pk']))
                    nbeleves+=1
            listeHeures.append((listeEleves,heure,nbeleves))
            nbheures += nbeleves
            listeDates.append((listeHeures,date_colle,nbheures))
            nbdates+=nbheures    
            listeNotes.append((listeDates,semaine,titre,detail,nbdates))
        return listeNotes

    def classe2resultat(self,matiere,classe,semin,semax):
        semaines = Semaine.objects.filter(semainenote__classe=classe,semainenote__matiere=matiere,lundi__range=(semin.lundi,semax.lundi)).distinct().order_by('lundi')
        yield semaines
        listeEleves = list(Eleve.objects.filter(classe=classe).select_related('user'))
        elevesdict = {eleve.pk:[eleve.user.first_name.title(),eleve.user.last_name.upper(),"",""] for eleve in listeEleves}
        moyennes = list(Note.objects.exclude(note__gt=20).filter(matiere=matiere,classe=classe).filter(semaine__lundi__range=[semin.lundi,semax.lundi]).values('eleve__id','eleve__user__first_name','eleve__user__last_name').annotate(Avg('note')).order_by('eleve__user__last_name','eleve__user__first_name'))
        moyennes.sort(key=lambda x:x['note__avg'],reverse=True)
        for i,x in enumerate(moyennes):
            x['rang']=i+1
        for i in range(len(moyennes)-1):
            if moyennes[i]['note__avg']-moyennes[i+1]['note__avg']<1e-6:
                moyennes[i+1]['rang']=moyennes[i]['rang']
        for moyenne in moyennes:
            elevesdict[moyenne['eleve__id']][2:]=[moyenne['note__avg'],moyenne['rang']]
        eleves = [elevesdict[eleve.pk] for eleve in listeEleves] 
        for elevemoy,eleve in zip(eleves,listeEleves):
            note=dict()
            note['eleve']=eleve
            note['moyenne']=elevemoy[2]
            note['rang']=elevemoy[3]
            note['semaine']=list()
            for semaine in semaines:
                note['semaine'].append(Note.objects.filter(eleve=eleve,matiere=matiere,semaine=semaine).values('note','colleur__user__first_name','colleur__user__last_name','commentaire'))
            yield note

    def noteEleve(self,eleve,matiere=None):
        requete = "SELECT m.nom nom_matiere, m.couleur couleur, n.date_colle date_colle, u.first_name prenom, u.last_name nom, p.titre titre, p.detail programme, n.note note, n.commentaire commentaire\
                   FROM accueil_note n\
                   INNER JOIN accueil_matiere m\
                   ON n.matiere_id=m.id\
                   INNER JOIN accueil_colleur c\
                   ON n.colleur_id=c.id\
                   INNER JOIN accueil_user u\
                   ON u.colleur_id=c.id\
                   INNER JOIN accueil_semaine s\
                   ON n.semaine_id = s.id\
                   LEFT OUTER JOIN accueil_programme p\
                   ON p.semaine_id = s.id AND p.classe_id = n.classe_id AND p.matiere_id=m.id\
                   WHERE n.eleve_id = %s "
        if matiere:
            requete+="AND m.id = %s "
        requete+="ORDER BY date_colle DESC"
        with connection.cursor() as cursor:
            cursor.execute(requete,[eleve.pk] + ([matiere.pk] if matiere else []))
            notes = dictfetchall(cursor)
        return notes

    def bilanEleve(self,eleve,semin,semax):
        matieres = self.filter(eleve=eleve).exclude(note__gt=20)
        if semin:
            matieres=matieres.filter(semaine__lundi__range=(semin.lundi,semax.lundi))
        matieres=matieres.values_list('matiere__pk').order_by('matiere__nom').distinct()
        moyenne = self.filter(eleve=eleve,matiere__pk__in=matieres).exclude(note__gt=20)
        moyenne_classe = self.filter(matiere__pk__in=matieres,classe=eleve.classe,eleve__isnull=False).exclude(note__gt=20) 
        if semin:
            moyenne=moyenne.filter(semaine__lundi__range=[semin.lundi,semax.lundi])
            moyenne_classe = moyenne_classe.filter(semaine__lundi__range=[semin.lundi,semax.lundi])
        moyenne = list(moyenne.values('matiere__nom','matiere__couleur').annotate(Avg('note'),Min('note'),Max('note'),Count('note'),StdDev('note')).order_by('matiere__nom'))
        moyenne_classe = moyenne_classe.values('matiere__pk').annotate(Avg('note')).order_by('matiere__nom')
        rangs=[]
        for i,matiere in enumerate(matieres):
            rang=self.exclude(note__gt=20).filter(classe=eleve.classe,eleve__isnull=False,matiere__pk=matiere[0])
            if semin:
                rang=rang.filter(semaine__lundi__range=[semin.lundi,semax.lundi])
            if moyenne[i]['note__avg']:
                rang=rang.values('eleve').annotate(Avg('note')).filter(note__avg__gt=moyenne[i]['note__avg']+0.0001).count()+1
            else:
                rang=0
            rangs.append(rang)
        return [{"note__max": x["note__max"], "matiere__couleur": x["matiere__couleur"], "note__stddev": x["note__stddev"], "note__min": x["note__min"], 
        "matiere__nom": x["matiere__nom"], "note__count": x["note__count"], "note__avg": x["note__avg"], "noteclasse__avg":y["note__avg"],"rang":z} for x,y,z in zip(moyenne,moyenne_classe,rangs)]

class Note(models.Model):
    LISTE_JOUR=enumerate(["lundi","mardi","mercredi","jeudi","vendredi","samedi"])
    LISTE_HEURE=[(i,"{}h{:02d}".format(i//60,(i%60))) for i in range(HEURE_DEBUT,HEURE_FIN,INTERVALLE)] 
    LISTE_NOTE=[(21,"n.n"),(22,"Abs")]
    LISTE_NOTE.extend(zip(range(21),range(21)))
    colleur = models.ForeignKey("Colleur",on_delete=models.PROTECT)
    matiere = models.ForeignKey("Matiere",on_delete=models.PROTECT)
    date_enreg = models.DateField(auto_now_add = True)
    semaine = models.ForeignKey("Semaine",related_name="semainenote",on_delete=models.PROTECT,blank=False)
    date_colle = models.DateField(verbose_name = 'date de rattrapage',default=date.today)
    rattrapee = models.BooleanField(verbose_name="rattrapée")
    jour = models.PositiveSmallIntegerField(choices=LISTE_JOUR,default=0)
    note = models.PositiveSmallIntegerField(choices=LISTE_NOTE,default=22)
    eleve = models.ForeignKey("Eleve",null=True,on_delete=models.PROTECT)
    classe = models.ForeignKey("Classe",on_delete=models.PROTECT)
    heure = models.PositiveSmallIntegerField(choices=LISTE_HEURE,default=14)
    commentaire = models.TextField(max_length=2000,verbose_name="Commentaire(facultatif)",null = True, blank=True)
    objects = NoteManager()

    def update(self):
        if not self.rattrapee: # si la colle n'est pas rattrapée, on calcule la date de colle à partir de la semaine et du jour de la semaine
            self.date_colle=self.semaine.lundi+timedelta(days=int(self.jour))

    def __str__(self):
        return "{} {} {} {}".format(self.eleve.user.last_name.upper(),self.matiere.nom,self.semaine.numero,self.note)
