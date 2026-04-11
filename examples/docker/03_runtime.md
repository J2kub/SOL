**Zadání:**

> Stupeň `runtime` vytvoří obraz kontejneru, který přímo spouští váš interpret. Tento obraz by měl být co nejodlehčenější, neměly by se v něm nacházet závislosti pro vývoj, nástroje pro kontrolu kvality kódu atp.
>
> Speciálně v případě TS to znamená, že tento stupeň z výstupu předchozího stupně pouze zkopíruje přeložené soubory (direktiva `COPY --from=build`), tedy aby se
v obrazu kontejneru už nenecházel zdrojový kód a překladač.

Spouštění vašich interpretů pro testování funkcionality (naším testovacím nástrojem) tedy bude vypadat v principu takhle:

1. Sestavíme obraz kontejneru:

```sh
cd rozbaleny_projekt_xlogin0b/
docker build --target runtime --tag xlogin0b:runtime .
```

2. Vytvoříme kontejner (v neinteraktivním režimu), na nějakou cestu připojíme adresář s kódem a případně vstupem pro program. Výstup kontejneru zachytáváme do logu.

```sh
docker run --rm \
  -v /nejaka/slozka/s/programy:/tmp/whatever/ xlogin0b:runtime \
  --source /tmp/whatever/program.solxml \
  --input /tmp/whatever/vstup_pro_program.txt \
  >xlogin0b_stdout.log 2>xlogin0b_stderr.log
```

Je tedy nutné, aby váš Containerfile obsahoval direktivu `ENTRYPOINT`, která bude ukazovat na spustitelný soubor, který přímo spouští váš interpet (a zajistí předání argumentů příkazové řádky). Například pro PHP:

```dockerfile
FROM php:8.5-cli AS runtime

# kopírování potřebných souborů apod.

WORKDIR /muj/adresar/s/interpretem
ENTRYPOINT ["/usr/local/bin/php", "src/solint.php"]
```