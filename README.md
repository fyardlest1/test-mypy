# Pourquoi mypy refuse `pgtrigger.Q(foo_bar=42)`

Ce dépôt reprend les étapes dans l'ordre où je les ai suivies, 
y compris **la tentative d'isolation qui a échoué**, 
parce que c'est elle qui explique pourquoi le bug est si difficile à
reproduire hors de Django.

## Versions testées

|               | Python | Django | django-pgtrigger | mypy  |
| ------------- | ------ | ------ | ---------------- | ----- |
| Combinaison A | 3.14.6 | 6.1.2  | 4.17.0           | 2.3.1 |

---

## Étape 1 · Monter un environnement isolé

```powershell
mkdir test-mypy
cd test-mypy
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
```

Sous Linux ou macOS, `python -m venv .venv` puis `source .venv/bin/activate`.

```powershell
mypy --version
```

```
mypy 2.3.1 (compiled: yes)
```

---

## Étape 2 · Reproduire le symptôme

`foo.py` :

```python
import pgtrigger

pgtrigger.Q(foo_bar=42)
```

```powershell
mypy foo.py
```

Le resultat:

```powershell
foo.py:3: error: Unexpected keyword argument "foo_bar" for "Q"  [call-arg]
foo.py:3: note: "Q" defined in "pgtrigger.core"
Found 1 error in 1 file (checked 1 source file)
```

---

## Étape 3 · Demander à mypy quelle signature il applique

Première question utile : mypy se trompe-t-il sur l'argument, ou sur le constructeur tout entier ?

`foo2.py` :

```python
import pgtrigger

reveal_type(pgtrigger.Q.__init__)

pgtrigger.Q(sql="SELECT 1")
pgtrigger.Q(_negated=True)
```

```powershell
mypy foo2.py
```

```
foo2.py:3: note: Revealed type is "def (self: pgtrigger.core.Condition, sql: str | None =)"
foo2.py:6: error: Unexpected keyword argument "_negated" for "Q"  [call-arg]
foo2.py:6: note: "Q" defined in "pgtrigger.core"
Found 1 error in 1 file (checked 1 source file)
```

`reveal_type` n'existe qu'à l'analyse, jamais à l'exécution.

**Ce que ça apprend.** mypy croit que le constructeur de `pgtrigger.Q` est
celui de `pgtrigger.Condition`. Les deux appels le confirment, et leurs
résultats sont inversés par rapport à l'attendu :

| Appel               | Argument de           | Résultat    |
| ------------------- | --------------------- | ----------- |
| `Q(sql="SELECT 1")` | `pgtrigger.Condition` | **accepté** |
| `Q(_negated=True)`  | `django.db.models.Q`  | **refusé**  |

La piste n'est donc pas « mypy ne connaît pas `foo_bar` », mais « mypy regarde la mauvaise classe ».

---

## Étape 4 · Regarder la définition de `Q` dans pgtrigger

```powershell
py -c "import importlib.util as u, os; print(os.path.dirname(u.find_spec('pgtrigger').origin))"
```

`find_spec` localise le paquet **sans l'importer**, ce qui évite la cascade
psycopg de l'étape 2.

Dans `core.py` :

```python
class Q(models.Q, Condition):
    ...
```

Et une cinquantaine de lignes plus haut :

```python
class Condition:
    def __init__(self, sql: str | None = None):
        ...
```

Héritage multiple, et la seconde base porte exactement la signature que `reveal_type` a révélée. La question devient : pourquoi la première base ne l'emporte-t-elle pas ?

---

## Étape 5 · Vérifier qui déclare ses types

```powershell
py -m pip show -f django-pgtrigger | Select-String "py.typed"
py -m pip show -f django | Select-String "py.typed"
```

```
  pgtrigger/py.typed
```

La seconde commande ne renvoie rien.

**Ce que çcela m'a appris.** mypy analyse pgtrigger, qui déclare ses types. Il n'ouvre pas Django, qui ne les déclare pas. Première base invisible, seconde base visible.

---

## Étape 6 · La tentative d'isolation qui échoue

C'est l'étape la plus instructive. Reproduire la même structure hors de Django, avec une classe sans annotations :

```python
class Condition:
    def __init__(self, sql: str | None = None): ...

class models_Q:
    def __init__(self, **kwargs): ...

class Q(models_Q, Condition): ...

Q(foo_bar=42)
```

```
Success: no issues found in 1 source file
```

**Aucune erreur.** La structure est pourtant identique.

**Pourquoi.** Une classe **non annotée** n'est pas une classe **non analysée**.
mypy voit parfaitement `__init__(self, **kwargs)` : une signature sans annotations reste une signature, et le `**kwargs` accepte `foo_bar`.

Django n'est pas mal annoté, il est **invisible**. Pour reproduire, il ne faut pas une base sans annotations, 
il faut une base que mypy ne peut pas résoudre du tout.

---

## Étape 7 · L'isolation qui réussit

`demo.py` met les deux cas côte à côte :

```python
from paquet_inexistant import Q_importee  # type: ignore


class Q_collee:
    def __init__(self, **kwargs): ...


class Condition:
    def __init__(self, sql: str | None = None): ...


class A(Q_importee, Condition): ...


class B(Q_collee, Condition): ...


reveal_type(A.__init__)
reveal_type(B.__init__)

A(foo_bar=42)
B(foo_bar=42)
```

Un import irrésoluble assorti d'un `# type: ignore` produit exactement ce que produit un paquet sans `py.typed`.

> Le commentaire doit être exactement `# type: ignore`, sans rien après sur la ligne, sinon mypy répond `Invalid "type: ignore" comment`.

```powershell
mypy demo.py
```

```
demo.py:18: note: Revealed type is "def (self: demo.Condition, sql: str | None =)"
demo.py:19: note: Revealed type is "def (self: demo.Q_collee, **kwargs: Any) -> Any"
demo.py:21: error: Unexpected keyword argument "foo_bar" for "A"  [call-arg]
Found 1 error in 1 file (checked 1 source file)
```

Même structure, mêmes noms, même ordre des bases. Seule l'origine de la première base change, et seule la ligne 21 échoue. 
**Le bug est isolé, sans Django ni pgtrigger.**

---

## Étape 8 · Deux variantes pour cerner la règle

**L'ordre des bases change-t-il quelque chose ?**

```python
class Q(Condition, models_Q): ...   # Condition en premier
Q(foo_bar=42)
```

```
error: Unexpected keyword argument "foo_bar" for "Q"  [call-arg]
```

Je ne le crois pas. Ce n'est donc pas une question de position dans la MRO.

**Et avec la base irrésoluble toute seule ?**

```python
class Q(models_Q): ...   # pas de Condition
Q(foo_bar=42)
```

```
Success: no issues found in 1 source file
```

Permissif. Il faut donc **les deux à la fois** : une base non résolue et une base réelle qui définit `__init__`.

---

## Étape 9 · Chercher la règle dans le code de mypy

Pour vérifier que mypy nomme bien ce cas :

```powershell
mypy --disallow-subclassing-any g.py
```

```
g.py:4: error: Class cannot subclass "X" (has type "Any")  [misc]
```

C'est mypy qui écrit « has type Any », à propos d'une classe importée d'un module qu'il ne sait pas lire. Rien de tel n'est écrit dans le fichier.

Localiser les trois passages concernés :

```powershell
py -c "import mypy, os, re; d=os.path.dirname(mypy.__file__); print(d); [print(f'  {f}:{i}  {l.rstrip()}') for f,p in [('semanal.py',r'info\.fallback_to_any = True'),('nodes.py',r'^\s*fallback_to_any: bool'),('checkmember.py',r'if itype\.type\.fallback_to_any:')] for i,l in enumerate(open(os.path.join(d,f),encoding='utf8'),1) if re.search(p,l)]"
```

En mypy 2.3.1 : `semanal.py:2687`, `nodes.py:3751`, `checkmember.py:627`.

**`semanal.py:2680`**, branche qui traite les bases d'une classe :

```python
elif isinstance(base, AnyType):
    if self.options.disallow_subclassing_any:
        ...
    info.fallback_to_any = True
```

Remontez de quelques lignes : les bases valides font un
`base_types.append(base)`. Celle-ci ne le fait pas. Elle pose seulement un
drapeau, et **n'entre donc pas dans la MRO**.

**`nodes.py:3751`**, ce que le drapeau signifie :

```python
# If true, any unknown attributes should have type 'Any' instead
# of generating a type error.  This would be true if there is a
# base class with type 'Any', but other use cases may be
# possible.
fallback_to_any: bool
```

**`checkmember.py:627`**, où il est consommé :

```python
if itype.type.fallback_to_any:
    return AnyType(TypeOfAny.special_form)

# Could not find the member.
```

Notez la position : après toute la recherche dans la MRO, juste avant le
message d'erreur. C'est un dernier recours, pas une règle prioritaire.

**Ce qui explique les trois observations de l'étape 8 :**

| Bases                | MRO                                | `__init__` retenu      | Résultat         |
| -------------------- | ---------------------------------- | ---------------------- | ---------------- |
| non résolue seule    | `[Q, object]`                      | aucun, repli sur `Any` | permissif        |
| non résolue + réelle | `[Q, Condition, object]`           | celui de `Condition`   | **faux positif** |
| réelle + réelle      | `[Q, models.Q, Condition, object]` | celui de `models.Q`    | correct          |

---

## Étape 10 · Confirmer par django-stubs

Dernier test, par l'autre bout : rendre Django analysable.

```powershell
py -m pip install django-stubs
mypy foo.py
mypy foo2.py
```

```
Success: no issues found in 1 source file
```

```
foo2.py:3: note: Revealed type is "def (self: django.db.models.query_utils.Q, *args: Any, **kwargs: Any)"
Success: no issues found in 1 source file
```

Aucune ligne du code n'a changé. `models.Q` n'est plus `Any`, elle redevient
une base réelle, entre dans la MRO en première position, et sa signature
l'emporte sur celle de `Condition`.

```powershell
py -m pip uninstall django-stubs
```

> À faire avant de rejouer les étapes précédentes, sinon le faux positif ne se
> reproduit plus.

---

## Conclusion

Le faux positif demande la réunion de trois conditions :

1. une classe qui hérite de plusieurs bases ;
2. au moins une base que mypy ne peut pas analyser, donc vue comme `Any` ;
3. au moins une autre base qu'il analyse et qui définit `__init__`.

La deuxième est écartée du calcul de la MRO, la troisième fournit la signature, et mypy vérifie l'appel avec le mauvais constructeur. 
Avec une seule base, ou avec toutes les bases résolues, le problème disparaît.

Ce n'est un bug ni de mypy ni de pgtrigger pris isolément. C'est ce que produit l'héritage multiple quand une partie de la hiérarchie échappe à l'analyse.

**Les parades :** installer les stubs du paquet non typé, ou activer
`disallow_subclassing_any` pour que *mypy* signale la situation au lieu de la subir en silence.

## Fichiers

| Fichier            | Étape                                      |
| ------------------ | ------------------------------------------ |
| `foo.py`           | 2, le symptôme                             |
| `foo2.py`          | 3 et 10, `reveal_type` et les contre-tests |
| `demo.py`          | 7, l'isolation réussie                     |
| `g.py`             | 9, `--disallow-subclassing-any`            |
| `requirements.txt` | 1                                          |

## Licence

CC0, domaine public. Un repro a vocation à être copié dans un rapport d'issue ou une discussion, reprenez-le librement.
