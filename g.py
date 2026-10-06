from paquet_inexistant import X  # type: ignore


class C(X):
    pass

# mypy g.py
# Success: no issues found in 1 source file

# mypy --disallow-subclassing-any g.py
# g.py:4: error: Class cannot subclass "X" (has type "Any")  [misc]
# Found 1 error in 1 file (checked 1 source file)

# Voilà le point : c'est mypy qui écrit « has type Any », à propos d'une classe importée depuis un module qu'il ne peut pas analyser. Vous n'avez écrit aucun Any dans ce fichier.