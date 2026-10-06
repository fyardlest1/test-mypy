import pgtrigger

reveal_type(pgtrigger.Q.__init__)

pgtrigger.Q(sql="SELECT 1")
pgtrigger.Q(_negated=True)