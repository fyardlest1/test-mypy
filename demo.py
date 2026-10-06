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


'''
mypy demo.py
demo.py:18: note: Revealed type is "def (self: demo.Condition, sql: str | None =)"
demo.py:19: note: Revealed type is "def (self: demo.Q_collee, **kwargs: Any) -> Any"
demo.py:21: error: Unexpected keyword argument "foo_bar" for "A"  [call-arg]
Found 1 error in 1 file (checked 1 source file)

# Lisez les trois lignes dans l'ordre. 
A hérite d'une base importée, et mypy lui attribue le constructeur de Condition. 
B hérite d'une base écrite sur place, et mypy lui attribue le bon constructeur. Seule la ligne 21 échoue, pas la 22.

reveal_type n'existe pas à l'exécution, c'est une fonction que seul mypy comprend. Vous pouvez la laisser pendant vos tests et la retirer ensuite.
'''

# pour lire le code source de mypy: py -c "import mypy, os; print(os.path.dirname(mypy.__file__))"
# Puis le dossier dans mon éditeur: code (py -c "import mypy, os; print(os.path.dirname(mypy.__file__))")
