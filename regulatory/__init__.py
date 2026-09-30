"""regulatory — camada de inteligência regulatória acionável (produto B2B).

Princípio central: **coleta de dados não é o produto**. O produto é converter
informação regulatória em decisão empresarial. Cada evento publicado responde a
onze perguntas: o que mudou, por que importa, quem é afetado, setores, tipos de
empresa, função interna, obrigação/risco/oportunidade, prazo, ação concreta,
evidência oficial e prioridade.

Regras não negociáveis (aplicadas pelo motor e verificadas por
`scripts/validate_intelligence.py`):

1. Sem fonte oficial verificável, o evento não é publicado — nunca.
2. Sem separação explícita entre FATO OFICIAL, ANÁLISE, INTERPRETAÇÃO e
   RECOMENDAÇÃO, o evento não é publicado.
3. Abaixo de `taxonomy.CONFIDENCE_FLOOR` (0,60) nada é publicado
   automaticamente; fica em fila de curadoria.
4. Empresas nunca são declaradas "enquadradas" na norma: usa-se linguagem
   condicional ("potencialmente afetada", "exposição provável", "requer
   avaliação jurídica específica").
5. Nenhuma jurisprudência, prazo ou obrigação é inventada: ou vem da fonte
   oficial capturada, ou não é publicada.

Versão: 1.0.0
"""

__all__ = ["taxonomy", "engine", "product"]
__version__ = "1.0.0"
