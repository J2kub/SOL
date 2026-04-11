**Zadání:**

> Stupeň `check` vytvoří prostředí, ve kterém bude možné spustit požadované nástroje pro udržení kvality kódu, a to pro obě části projektu. Vstupním bodem výsledného obrazu bude `bash`. Do kontejneru budou z hostitelského stroje připojeny (jako *bind mount*) adresáře s interpetem (do `/src/int`) i adresář s testovacím nástrojem (do `/src/tester`). V shellu pak budou v těchto adresářích spouštěny příslušné nástroje pro udržení kvality kódu, jak je uvedeno v sekci 3 (je nutné zajistit správné předávání argumentů příkazové řádky!).

Kontrola vašich projektů pomocí nástrojů na udržení kvality kódu bude v principu probíhat přibližně následujícím způsobem:

1. Sestavíme obraz kontejneru:

```sh
leo@mypc $ cd rozbaleny_projekt_xlogin0b/
leo@mypc $ docker build --target check --tag xlogin0b:check .
```

2. Vytvoříme kontejner v interaktivním režimu a na uvedené cesty připojíme složky přímo z rozbaleného projektu:

```sh
leo@mypc $ docker run --rm -it -v ./int/:/src/int/ -v ./tester/:/src/tester/ xlogin0b:check
```

3. **V shellu**, který musí být v kontejneru spuštěn (zajistí váš Containerfile direktivou `ENTRYPOINT`) spustíme příkazy definované zadáním (zde pro příklad interpret v Pythonu a testovací nástroj v TS):

```sh
root@id_kontejneru $ cd /src/int
root@id_kontejneru $ ./ruff check
root@id_kontejneru $ ./mypy .
root@id_kontejneru $ cd /src/tester
root@id_kontejneru $ ./eslint --format json src/
```

Dostupnost nástrojů pro spuštění výše uvedeným způsobem (např. pomocí `./ruff`) musíte zajistit vy! Typickou možností bude umístit do daného pracovního adresáře nějaký primitivní skript pojmenovaný (v tomto případě) `ruff`, který aktivuje prostředí pro běh `ruff` (pokud to je nutné) a spustí samotný program `ruff` s tím, že mu předá své argumenty:

```sh
#!/usr/bin/env bash
# nějaké příkazy pro aktivaci prostředí, pokud jsou nutné
/cesta/k/binárce/ruff "$@"
```

Nezapomeňte soubor nastavit jako spustitelný (`chmod +x`).