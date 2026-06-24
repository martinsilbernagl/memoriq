Spust konsolidaci pameti pro aktualni projekt.
Organizuje fakty do clusteru, prirazuje knowledge tiery a detekuje kontradikce.
NIKDY nic nemaze — pouze organizuje.

Kroky:
1. Spust konsolidacni skript:
   python ~/.memoriq/mcp-server/tools/consolidate.py

2. Zobraz uzivateli konsolidacni report (clustery, tiery, kontradikce).

3. Pokud byly detekovany kontradikce, vyhledej je:
   memory_search("kontradikce") a ukaz uzivateli ktere fakty mohou potrebovat revizi.

4. Aktualizuj session bridge s vysledky konsolidace.
