**Zadání:**

> Stupeň `test` bude vycházet z předchozího stupně (direktiva FROM runtime), přičemž ale bude spouštět váš nástroj pro integrační testování (ten bude v případě TS opět pouze zkopírován ze stupně `build-test`).

Spouštění vašich testovacích nástrojů pro testování jejich funkcionality tedy bude vypadat v principu takhle:

1. Sestavíme obraz kontejneru:

```sh
cd rozbaleny_projekt_xlogin0b/
docker build --target test --tag xlogin0b:test .
```

2. Vytvoříme kontejner (v neinteraktivním režimu), na nějakou cestu připojíme adresář s testy a případně adresář pro výstupní soubor. Výstup kontejneru zachytáváme do logu.

```sh
docker run --rm \
  -v /nejaka/slozka/s/testy:/tmp/whatever/ \
  -v /nejaka/slozka/pro/vystup:/tmp/out/ \ 
  xlogin0b:test \
  [nějaké parametry pro testovací nástroj] \
  /tmp/whatever
  >xlogin0b_test_stdout.log 2>xlogin0b_test_stderr.log
```

Je tedy nutné, aby váš Containerfile obsahoval direktivu `ENTRYPOINT`, která bude ukazovat na spustitelný soubor, který přímo spouští váš testovací nástroj (a zajistí předání argumentů příkazové řádky). Například pro PHP:

```dockerfile
FROM php:8.5-cli AS runtime

# kopírování potřebných souborů apod.

WORKDIR /muj/adresar/s/testovacim/nastrojem
ENTRYPOINT ["/usr/local/bin/php", "src/tester.php"]
```

### Závislost hodnocení testovacího nástroje na implementaci interpetu

Testovací nástroj se spouští ve vámi dodaném kontejneru a zadání záměrně nespecifikuje, jakým způsobem se ty nástroje (sol2xml, interpret, testovací nástroj) provazují. Není tedy možné testovací nástroj hodnotit *zcela* nezávisle na interpretu. 

Testovací nástroj musí být minimálně schopen ten interpret spustit. Interpret by měl zvládnout správně provést nějaký minimální program (alespoň úplně prázdný program, ve kterém je pouze třída `Main` s prázdnou metodou `run`). Protože je použití šablony povinné, interpret by měl i bez vašeho zásahu správně reagovat např. na parametr `--help` (což už šablona zajišťuje).

Tyto skutečnosti však pro vyzkoušení testovacího nástroje stačí, a tak se nemusíte obávat, že by špatně fungující interpret měl podstatný vliv na hodnocení testovacího nástroje.
